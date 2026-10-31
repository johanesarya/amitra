"""Data rapor, grafik per butir, dan tren (FR-48 s.d. FR-50).

Keputusan 31 Okt 2026: hanya audit Final (Final, Tindak Lanjut PTK, Ditutup) yang dipakai,
agar Viewer dan auditee tidak melihat angka sementara. Tidak ada rumus baru: angka dari
HasilPerhitungan dan kategori final, skor dari skala Pengaturan periode.
"""

from collections import Counter, defaultdict
from decimal import Decimal
from fractions import Fraction

from django.db.models import Prefetch, Q

from findings.models import PTK, Temuan
from masterdata.models import Periode, TipeUnit, Unit
from scoring.rumus import bulatkan

from .models import Audit, HasilPerhitungan, KategoriFinal, Penugasan
from .penilaian import STATUS_SETELAH_FINAL

KATEGORI = ["KTS", "OB", "SESUAI", "PELAMPAUAN"]


# --- Hak akses (Bab 4) ------------------------------------------------------------------

def unit_terlihat(user):
    """None = semua unit (Admin, Master Admin, Viewer); selain itu set id unit tempat ia auditee."""
    if user.has_perm("audits.lihat_analitik"):
        return None
    return set(
        Penugasan.objects.filter(pengguna=user, peran=Penugasan.Peran.AUDITEE).values_list("audit__unit_id", flat=True)
    )


def boleh_analitik(user):
    terlihat = unit_terlihat(user)
    return terlihat is None or bool(terlihat)


# --- Kueri dasar -------------------------------------------------------------------------------

def audit_final(periode=None, *, unit_ids=None, fakultas=None, tipe=None, unit=None):
    qs = Audit.objects.filter(status__in=STATUS_SETELAH_FINAL).select_related("unit__tipe", "unit__induk", "periode")
    if periode is not None:
        qs = qs.filter(periode=periode)
    if unit_ids is not None:
        qs = qs.filter(unit_id__in=unit_ids)
    if fakultas is not None:
        qs = qs.filter(Q(unit=fakultas) | Q(unit__induk=fakultas))
    if tipe is not None:
        qs = qs.filter(unit__tipe=tipe)
    if unit is not None:
        qs = qs.filter(unit=unit)
    return qs


def periode_dengan_hasil(unit_ids=None):
    qs = Periode.objects.filter(audit__status__in=STATUS_SETELAH_FINAL)
    if unit_ids is not None:
        qs = qs.filter(audit__unit_id__in=unit_ids)
    return qs.distinct().order_by("-tahun_akademik", "-id")


def _hasil_final(audit):
    hasil = {h.tahap: h for h in audit.hasil.all()}
    return hasil.get(HasilPerhitungan.Tahap.FINAL)


# --- Grafik per butir (FR-49) -----------------------------------------------------------------

def per_butir(audits, periode):
    """Rata-rata skor kategori final dan sebarannya per butir, terurut seperti daftar standar."""
    params = periode.parameter()
    kategori = (
        KategoriFinal.objects.filter(audit__in=audits)
        .exclude(cara=KategoriFinal.Cara.TIDAK_BERLAKU)
        .exclude(kategori="")
        .select_related("pernyataan__standar")
    )
    kelompok = defaultdict(list)
    butir = {}
    for k in kategori:
        kelompok[k.pernyataan_id].append(k.kategori)
        butir[k.pernyataan_id] = k.pernyataan
    hasil = []
    for pid, daftar in kelompok.items():
        p = butir[pid]
        jumlah = Counter(daftar)
        rata = sum((Fraction(params.skor(x)) for x in daftar), Fraction(0)) / len(daftar)
        hasil.append({
            "butir": p,
            "jumlah": {k: jumlah.get(k, 0) for k in KATEGORI},
            "n": len(daftar),
            "rata": bulatkan(rata),
        })
    hasil.sort(key=lambda r: (r["butir"].standar.urutan, r["butir"].standar.kode, r["butir"].urutan, r["butir"].kode))
    return {"baris": hasil, "skor_maks": params.skor_maks, "skor_sesuai": params.skor("SESUAI")}


# --- Tren per unit (FR-50) ---------------------------------------------------------------

def tren_unit(unit):
    audits = audit_final(unit=unit).prefetch_related("hasil", "temuan").order_by("periode__tahun_akademik", "periode_id")
    baris = []
    for a in audits:
        h = _hasil_final(a)
        if h is None:
            continue
        jenis = Counter(t.jenis for t in a.temuan.all())
        baris.append({
            "periode": a.periode,
            "audit": a,
            "ne": h.ne,
            "memenuhi_kkm": h.memenuhi_kkm,
            "kkm": Decimal(h.parameter.get("kkm", "75")),
            "kelebihan": jenis.get(Temuan.Jenis.KELEBIHAN, 0),
            "kts": jenis.get(Temuan.Jenis.KTS, 0),
            "ob": jenis.get(Temuan.Jenis.OB, 0),
            "peluang": jenis.get(Temuan.Jenis.PELUANG, 0),
        })
    return baris


# --- Rapor (FR-48, BRD 8.2) -------------------------------------------------------------------

def baris_rapor(audits):
    audits = audits.prefetch_related(
        "hasil",
        "temuan",
        "ptk",
        Prefetch("penugasan", queryset=Penugasan.objects.select_related("pengguna").order_by("-ketua", "pengguna__nama")),
    ).order_by("unit__induk__nama", "unit__tipe__urutan", "unit__nama")
    baris = []
    for a in audits:
        hasil = {h.tahap: h for h in a.hasil.all()}
        final = hasil.get(HasilPerhitungan.Tahap.FINAL)
        awal = hasil.get(HasilPerhitungan.Tahap.AWAL)
        auditor = [p for p in a.penugasan.all() if p.peran == Penugasan.Peran.AUDITOR]
        jenis = Counter(t.jenis for t in a.temuan.all())
        ptk = list(a.ptk.all())
        baris.append({
            "audit": a,
            "unit": a.unit,
            "fakultas": a.unit.induk if a.unit.induk_id else (a.unit if a.unit.tipe_id == TipeUnit.FAKULTAS else None),
            "auditor": [(p.pengguna, (final.nilai_auditor.get(str(p.pengguna_id)) if final else None)) for p in auditor],
            "deviasi": final.deviasi if final else None,
            "ne_awal": awal.ne if awal else None,
            "ne": final.ne if final else None,
            "memenuhi_kkm": final.memenuhi_kkm if final else None,
            "nk": final.nk if final else None,
            "hasil_akhir": final.hasil_akhir if final else None,
            "kelebihan": jenis.get(Temuan.Jenis.KELEBIHAN, 0),
            "kts": jenis.get(Temuan.Jenis.KTS, 0),
            "ob": jenis.get(Temuan.Jenis.OB, 0),
            "peluang": jenis.get(Temuan.Jenis.PELUANG, 0),
            "ptk_total": len(ptk),
            "ptk_direncanakan": sum(1 for p in ptk if p.status != PTK.Status.TERBUKA),
        })
    return baris


def cakupan_rapor(parameter):
    """Terjemahkan parameter rapor menjadi (judul cakupan, queryset audit Final)."""
    periode = Periode.objects.get(pk=parameter["periode"])
    if parameter.get("fakultas"):
        f = Unit.objects.get(pk=parameter["fakultas"])
        return f"{f} — {periode}", audit_final(periode, fakultas=f)
    if parameter.get("tipe"):
        t = TipeUnit.objects.get(pk=parameter["tipe"])
        return f"Semua {t} — {periode}", audit_final(periode, tipe=t)
    if parameter.get("unit"):
        u = Unit.objects.get(pk=parameter["unit"])
        return f"{u} — {periode}", audit_final(periode, unit=u)
    return f"Seluruh unit — {periode}", audit_final(periode)
