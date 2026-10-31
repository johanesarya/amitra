"""Tindak lanjut PTK lintas periode (FR-21, FR-36, FR-37, BR-17, Bab 6.6).

Keputusan 31 Okt 2026 (sementara):
- Final tanpa PTK langsung Ditutup; dengan PTK, auditee mengirim rencana → Tindak Lanjut PTK.
- PTK diverifikasi tim auditor (ketua atau anggota) yang diplot Admin untuk audit unit yang sama di
  periode berikutnya; audit lama Ditutup saat semua PTK-nya terverifikasi (efektif maupun belum).
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from audits import status
from audits.models import Audit, Bukti, Penugasan
from audits.penilaian import STATUS_SETELAH_FINAL
from audits.ser import periksa_berkas, periksa_tautan

from .models import PTK
from .sinyal import ptk_diperbarui, ptk_diverifikasi

S = Audit.Status
STATUS_BOLEH_VERIFIKASI = frozenset({S.PENILAIAN_AUDITOR, S.REKONSILIASI, S.PERLU_AUDIT_LAPANGAN, S.PERUMUSAN_TEMUAN})


def _pastikan_auditee(penugasan):
    if penugasan is None or penugasan.peran != Penugasan.Peran.AUDITEE:
        raise PermissionError("Hanya auditee yang dapat melakukan tindakan ini.")


# --- Rencana dan realisasi oleh auditee ---------------------------------------------------

@transaction.atomic
def kirim_rencana(audit, penugasan):
    """Bab 6.6: semua rencana PTK lengkap → Tindak Lanjut PTK; rencana terkunci."""
    _pastikan_auditee(penugasan)
    if audit.status != S.FINAL:
        raise ValidationError("Rencana PTK dikirim saat hasil audit Final.")
    daftar = list(audit.ptk.all())
    belum = [p.kode for p in daftar if not p.rencana_lengkap]
    if belum:
        raise ValidationError(f"Lengkapi rencana {', '.join(belum)} terlebih dahulu.")
    sekarang = timezone.now()
    audit.ptk.update(rencana_dikirim_pada=sekarang)
    status.ubah_status(audit, S.TINDAK_LANJUT_PTK, penugasan.pengguna, alasan="Rencana tindak lanjut PTK dikirim auditee.")


def _pastikan_realisasi_terbuka(audit, ptk):
    if audit.status != S.TINDAK_LANJUT_PTK:
        raise ValidationError("Realisasi diisi setelah rencana PTK dikirim.")
    if ptk.sudah_diverifikasi:
        raise ValidationError(f"{ptk.kode} sudah diverifikasi.")


def simpan_realisasi(audit, penugasan, ptk, realisasi):
    _pastikan_auditee(penugasan)
    _pastikan_realisasi_terbuka(audit, ptk)
    ptk.realisasi = (realisasi or "").strip()
    ptk.diubah_oleh = penugasan.pengguna
    ptk.save(update_fields=["realisasi", "diubah_oleh", "diubah_pada"])
    ptk_diperbarui.send(sender=PTK, ptk=ptk)
    return ptk


def tambah_bukti(audit, penugasan, ptk, *, url=None, nama="", berkas=None):
    """Bukti tindak lanjut: tautan Google Drive atau berkas, aturan sama dengan bukti SER."""
    _pastikan_auditee(penugasan)
    _pastikan_realisasi_terbuka(audit, ptk)
    if berkas is not None:
        periksa_berkas(berkas)
        b = Bukti(ptk=ptk, jenis=Bukti.Jenis.BERKAS, nama=berkas.name[:255], ukuran=berkas.size, diunggah_oleh=penugasan.pengguna)
        b.berkas.save(berkas.name, berkas, save=False)
        b.save()
        return b
    url = periksa_tautan(url)
    return Bukti.objects.create(
        ptk=ptk, jenis=Bukti.Jenis.TAUTAN, url=url, nama=(nama or "").strip()[:255] or url[:255], diunggah_oleh=penugasan.pengguna
    )


def hapus_bukti(audit, penugasan, bukti):
    _pastikan_auditee(penugasan)
    _pastikan_realisasi_terbuka(audit, bukti.ptk)
    if bukti.berkas:
        bukti.berkas.delete(save=False)
    bukti.delete()


# --- Audit periode lalu dan padanan butir (FR-21, BR-17) ------------------------------------

def audit_periode_lalu(audit):
    """Audit unit yang sama di periode sebelumnya yang sudah Final (atau sesudahnya)."""
    return (
        Audit.objects.filter(
            unit=audit.unit, status__in=STATUS_SETELAH_FINAL, periode__tahun_akademik__lt=audit.periode.tahun_akademik
        )
        .select_related("periode")
        .order_by("-periode__tahun_akademik", "-id")
        .first()
    )


def ptk_periode_lalu(audit):
    lalu = audit_periode_lalu(audit)
    if lalu is None:
        return []
    return list(
        lalu.ptk.select_related("temuan__pernyataan__standar", "diverifikasi_oleh", "audit__periode").prefetch_related("bukti")
    )


def padanan_butir(audit, ptk_lalu):
    """{id butir audit ini: [PTK lalu]} lewat `asal` (salin standar), atau kode standar + kode butir."""
    butir = list(audit.pernyataan_berlaku())
    per_asal = {b.asal_id: b for b in butir if b.asal_id}
    per_kode = {(b.standar.kode, b.kode): b for b in butir}
    hasil = {}
    for p in ptk_lalu:
        lama = p.temuan.pernyataan
        if lama is None:
            continue
        baru = per_asal.get(lama.pk) or per_kode.get((lama.standar.kode, lama.kode))
        if baru is not None:
            hasil.setdefault(baru.pk, []).append(p)
    return hasil


def ringkasan_verifikasi(audit):
    daftar = ptk_periode_lalu(audit)
    return {
        "audit_lalu": daftar[0].audit if daftar else audit_periode_lalu(audit),
        "total": len(daftar),
        "efektif": sum(1 for p in daftar if p.status == PTK.Status.EFEKTIF),
        "belum_efektif": sum(1 for p in daftar if p.status == PTK.Status.TIDAK_EFEKTIF),
        "belum_diverifikasi": sum(1 for p in daftar if not p.sudah_diverifikasi),
    }


# --- Verifikasi oleh tim audit periode berikutnya (FR-37) ---------------------------------------

def boleh_verifikasi(audit, penugasan):
    return (
        penugasan is not None
        and penugasan.peran == Penugasan.Peran.AUDITOR
        and audit.status in STATUS_BOLEH_VERIFIKASI
    )


@transaction.atomic
def verifikasi(audit, penugasan, ptk, hasil, catatan):
    """Tim auditor audit baru (diplot Admin) menilai efektivitas PTK periode lalu."""
    if penugasan is None or penugasan.peran != Penugasan.Peran.AUDITOR:
        raise PermissionError("Verifikasi dilakukan oleh auditor yang ditugaskan di audit ini.")
    if audit.status not in STATUS_BOLEH_VERIFIKASI:
        raise ValidationError("Verifikasi PTK periode lalu dilakukan selama penilaian sampai perumusan temuan.")
    lalu = audit_periode_lalu(audit)
    if lalu is None or ptk.audit_id != lalu.pk:
        raise ValidationError("PTK ini bukan milik audit periode lalu unit ini.")
    if hasil not in (PTK.Status.EFEKTIF, PTK.Status.TIDAK_EFEKTIF):
        raise ValidationError("Pilih hasil verifikasi.")
    catatan = (catatan or "").strip()
    if not catatan:
        raise ValidationError("Catatan verifikasi wajib diisi.")
    ptk.status, ptk.catatan_verifikasi = hasil, catatan
    ptk.diverifikasi_di, ptk.diverifikasi_oleh, ptk.diverifikasi_pada = audit, penugasan.pengguna, timezone.now()
    ptk.save(update_fields=["status", "catatan_verifikasi", "diverifikasi_di", "diverifikasi_oleh", "diverifikasi_pada", "diubah_pada"])

    lalu = Audit.objects.get(pk=lalu.pk)
    if lalu.status in (S.FINAL, S.TINDAK_LANJUT_PTK) and all(p.sudah_diverifikasi for p in lalu.ptk.all()):
        status.ubah_status(lalu, S.DITUTUP, penugasan.pengguna, alasan=f"Semua PTK telah diverifikasi pada audit {audit.periode}.")
    ptk_diverifikasi.send(sender=PTK, ptk=ptk, audit_baru=audit)
    ptk_diperbarui.send(sender=PTK, ptk=ptk)
    return ptk


# --- Penutupan ------------------------------------------------------------------------------

def tutup_bila_tanpa_ptk(audit, oleh):
    """Bab 6.6 (keputusan sementara): audit Final tanpa PTK langsung Ditutup."""
    if audit.status == S.FINAL and not audit.ptk.exists():
        status.ubah_status(audit, S.DITUTUP, oleh, alasan="Tidak ada temuan KTS/OB sehingga tidak ada PTK.")


@transaction.atomic
def arsipkan_periode(periode, oleh, alasan):
    """Bab 6.6: periode diarsipkan → semua audit Final/Tindak Lanjut PTK ditutup, alasan tercatat."""
    alasan = (alasan or "").strip()
    if not alasan:
        raise ValidationError("Alasan pengarsipan wajib diisi.")
    jumlah = 0
    for a in Audit.objects.filter(periode=periode, status__in=(S.FINAL, S.TINDAK_LANJUT_PTK)):
        status.ubah_status(a, S.DITUTUP, oleh, alasan=f"Periode diarsipkan: {alasan}")
        jumlah += 1
    return jumlah
