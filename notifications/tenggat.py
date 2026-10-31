"""Tenggat tugas per pengguna untuk banner dan pengingat H-3 sampai H (FR-46).

Dihitung langsung dari data, sehingga banner hilang begitu tugasnya selesai.
"""

from dataclasses import dataclass
from datetime import date

from django.urls import reverse
from django.utils import timezone

from audits.models import Audit, Penugasan
from masterdata.models import TahapanPeriode

S = Audit.Status
HARI_PENGINGAT = range(0, 4)  # H-3, H-2, H-1, H


@dataclass(frozen=True)
class Tenggat:
    audit: Audit
    jenis: str  # SER, PENILAIAN, PTK
    batas: date
    sisa: int  # hari menuju batas; 0 = hari ini
    tautan: str

    @property
    def label(self):
        return {"SER": "Pengisian SER", "PENILAIAN": "Penilaian auditor", "PTK": "Rencana tindak lanjut PTK"}[self.jenis]

    @property
    def keterangan_sisa(self):
        return "hari ini" if self.sisa == 0 else f"{self.sisa} hari lagi"


def _batas_tahap(periode, jenis):
    for t in periode.tahapan.all():
        if t.jenis == jenis:
            return t.tanggal_selesai
    return None


def _tenggat_penugasan(p, hari_ini):
    """Tenggat yang masih terbuka untuk satu penugasan, atau None."""
    a = p.audit
    if p.peran == Penugasan.Peran.AUDITEE and a.status in Audit.STATUS_SER_TERBUKA:
        batas, jenis, tautan = a.batas_ser, "SER", reverse("audits:ser", args=[a.pk])
    elif p.peran == Penugasan.Peran.AUDITOR and a.status == S.PENILAIAN_AUDITOR and p.dikunci_pada is None:
        batas, jenis = _batas_tahap(a.periode, TahapanPeriode.Jenis.REVIEW_AUDITOR), "PENILAIAN"
        tautan = reverse("audits:penilaian", args=[a.pk])
    elif p.peran == Penugasan.Peran.AUDITEE and a.status in (S.FINAL, S.TINDAK_LANJUT_PTK) and any(
        not ptk.rencana_lengkap for ptk in a.ptk.all()
    ):
        batas, jenis = _batas_tahap(a.periode, TahapanPeriode.Jenis.TINDAK_LANJUT_PTK), "PTK"
        tautan = reverse("findings:ptk", args=[a.pk])
    else:
        return None
    if batas is None:
        return None
    return Tenggat(audit=a, jenis=jenis, batas=batas, sisa=(batas - hari_ini).days, tautan=tautan)


def _penugasan(qs):
    return qs.exclude(audit__status=S.DITUTUP).select_related("audit__unit", "audit__periode", "pengguna").prefetch_related(
        "audit__periode__tahapan", "audit__ptk"
    )


def tenggat_pengguna(user, hari_ini=None):
    """Semua tenggat terbuka milik pengguna, terdekat lebih dulu."""
    hari_ini = hari_ini or timezone.localdate()
    hasil = [t for p in _penugasan(Penugasan.objects.filter(pengguna=user)) if (t := _tenggat_penugasan(p, hari_ini))]
    return sorted(hasil, key=lambda t: t.batas)


def perlu_diingatkan(hari_ini=None):
    """[(pengguna, Tenggat)] yang jatuh pada H-3 sampai H."""
    hari_ini = hari_ini or timezone.localdate()
    hasil = []
    for p in _penugasan(Penugasan.objects.filter(pengguna__is_active=True)):
        t = _tenggat_penugasan(p, hari_ini)
        if t is not None and t.sisa in HARI_PENGINGAT:
            hasil.append((p.pengguna, t))
    return hasil
