"""Layanan SER auditee (FR-18 s.d. FR-23, NFR-05, NFR-06, NFR-09)."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Prefetch
from django.utils import timezone

from . import status
from .sinyal import batas_ser_diperpanjang
from .models import Audit, Bukti, JawabanSER, Kategori

DOMAIN_TAUTAN = frozenset({"drive.google.com", "docs.google.com"})
UKURAN_BERKAS_MAKS = 20 * 1024 * 1024  # NFR-06

# Ekstensi → tanda awal isi berkas, agar ekstensi palsu ditolak (NFR-09).
_ZIP = (b"PK\x03\x04",)
_OLE = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)
TIPE_BERKAS = {
    ".pdf": (b"%PDF",),
    ".doc": _OLE,
    ".xls": _OLE,
    ".ppt": _OLE,
    ".docx": _ZIP,
    ".xlsx": _ZIP,
    ".pptx": _ZIP,
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}


class SERTerkunci(Exception):
    pass


class KonflikVersi(Exception):
    """Butir sudah diubah di tempat lain (NFR-05)."""

    def __init__(self, jawaban):
        super().__init__("Butir ini sudah diubah di tab atau perangkat lain.")
        self.jawaban = jawaban


def _pastikan_terbuka(audit):
    if not audit.ser_bisa_diisi():
        if audit.status not in Audit.STATUS_SER_TERBUKA:
            raise SERTerkunci("SER sudah dikirim dan terkunci.")
        raise SERTerkunci("Batas pengisian SER sudah lewat. Hubungi Master Admin LPM.")


def butir_ser(audit):
    """FR-18: pernyataan berlaku beserta jawabannya (atau None), terurut."""
    jawaban = {
        j.pernyataan_id: j
        for j in audit.jawaban_ser.prefetch_related(Prefetch("bukti", queryset=Bukti.objects.order_by("diunggah_pada")))
    }
    return [(p, jawaban.get(p.pk)) for p in audit.pernyataan_berlaku()]


def pastikan_jawaban(audit):
    """Buat baris jawaban kosong untuk semua butir agar setiap isian punya versi awal."""
    ada = set(audit.jawaban_ser.values_list("pernyataan_id", flat=True))
    JawabanSER.objects.bulk_create(
        [JawabanSER(audit=audit, pernyataan=p) for p in audit.pernyataan_berlaku() if p.pk not in ada],
        ignore_conflicts=True,
    )


def _mulai_pengisian(audit, oleh):
    if audit.status == Audit.Status.BELUM_MULAI:
        status.ubah_status(audit, Audit.Status.PENGISIAN_SER, oleh)


def _jawaban_berlaku(audit, pernyataan_id):
    try:
        return audit.jawaban_ser.select_related("pernyataan").get(pernyataan_id=pernyataan_id)
    except JawabanSER.DoesNotExist:
        if not audit.pernyataan_berlaku().filter(pk=pernyataan_id).exists():
            raise ValidationError("Butir ini tidak termasuk SER audit ini.") from None
        jawaban, _ = JawabanSER.objects.get_or_create(audit=audit, pernyataan_id=pernyataan_id)
        return jawaban


@transaction.atomic
def simpan_isian(audit, pernyataan_id, penjelasan, versi, oleh, kategori=""):
    """Simpan kategori dan penjelasan satu butir bila versi masih sama; lempar KonflikVersi bila tidak (NFR-05)."""
    _pastikan_terbuka(audit)
    if kategori and kategori not in Kategori.values:
        raise ValidationError("Kategori tidak dikenal.")
    jawaban = _jawaban_berlaku(audit, pernyataan_id)
    diubah = JawabanSER.objects.filter(pk=jawaban.pk, versi=versi).update(
        kategori=kategori, penjelasan=penjelasan, versi=F("versi") + 1, diubah_oleh=oleh, diubah_pada=timezone.now()
    )
    jawaban.refresh_from_db()
    if not diubah:
        raise KonflikVersi(jawaban)
    _mulai_pengisian(audit, oleh)
    return jawaban


def periksa_tautan(url):
    url = (url or "").strip()
    bagian = urlsplit(url)
    if bagian.scheme != "https" or (bagian.hostname or "").lower() not in DOMAIN_TAUTAN:
        raise ValidationError("Tautan harus diawali https://drive.google.com/ atau https://docs.google.com/.")
    if len(url) > 1000:
        raise ValidationError("Tautan terlalu panjang.")
    return url


def periksa_berkas(berkas):
    ext = Path(berkas.name).suffix.lower()
    if ext not in TIPE_BERKAS:
        raise ValidationError("Tipe berkas tidak diizinkan. Gunakan PDF, Word, Excel, PowerPoint, JPG, atau PNG.")
    if berkas.size == 0:
        raise ValidationError("Berkas kosong.")
    if berkas.size > UKURAN_BERKAS_MAKS:
        raise ValidationError("Ukuran berkas maksimal 20 MB. Simpan di Google Drive lalu tempel tautannya.")
    awal = berkas.read(16)
    berkas.seek(0)
    if not any(awal.startswith(tanda) for tanda in TIPE_BERKAS[ext]):
        raise ValidationError(f"Isi berkas tidak sesuai dengan ekstensi {ext}.")


@transaction.atomic
def tambah_tautan(audit, pernyataan_id, url, oleh, nama=""):
    _pastikan_terbuka(audit)
    url = periksa_tautan(url)
    jawaban = _jawaban_berlaku(audit, pernyataan_id)
    bukti = Bukti.objects.create(
        jawaban=jawaban, jenis=Bukti.Jenis.TAUTAN, url=url, nama=(nama or "").strip()[:255] or url[:255],
        diunggah_oleh=oleh,
    )
    _mulai_pengisian(audit, oleh)
    return bukti


@transaction.atomic
def tambah_berkas(audit, pernyataan_id, berkas, oleh):
    _pastikan_terbuka(audit)
    periksa_berkas(berkas)
    jawaban = _jawaban_berlaku(audit, pernyataan_id)
    bukti = Bukti(
        jawaban=jawaban, jenis=Bukti.Jenis.BERKAS, nama=Path(berkas.name).name[:255], ukuran=berkas.size,
        diunggah_oleh=oleh,
    )
    bukti.berkas.save(berkas.name, berkas, save=False)
    bukti.save()
    _mulai_pengisian(audit, oleh)
    return bukti


def hapus_bukti(audit, bukti):
    _pastikan_terbuka(audit)
    if bukti.berkas:
        bukti.berkas.delete(save=False)
    bukti.delete()


@dataclass
class RingkasanSER:
    total: int
    lengkap: int
    belum_lengkap: list  # [(pernyataan, ["kategori", "penjelasan", "bukti"])]

    @property
    def siap_dikirim(self):
        return self.total > 0 and not self.belum_lengkap


def ringkasan(audit):
    belum = []
    for p, j in butir_ser(audit):
        kurang = []
        if j is None or not j.kategori:
            kurang.append("kategori")
        if j is None or not j.penjelasan.strip():
            kurang.append("penjelasan")
        if j is None or not j.bukti.all():
            kurang.append("bukti")
        if kurang:
            belum.append((p, kurang))
    total = audit.pernyataan_berlaku().count()
    return RingkasanSER(total=total, lengkap=total - len(belum), belum_lengkap=belum)


@transaction.atomic
def kirim(audit, oleh):
    """FR-22, FR-23: kirim SER lengkap; setelah itu terkunci."""
    _pastikan_terbuka(audit)
    r = ringkasan(audit)
    if not r.siap_dikirim:
        raise ValidationError(f"Masih ada {len(r.belum_lengkap)} butir yang belum lengkap.")
    if audit.status == Audit.Status.BELUM_MULAI:
        status.ubah_status(audit, Audit.Status.PENGISIAN_SER, oleh)
    status.ubah_status(audit, Audit.Status.PENILAIAN_AUDITOR, oleh, alasan="SER dikirim auditee.")
    audit.ser_dikirim_pada = timezone.now()
    audit.save(update_fields=["ser_dikirim_pada", "diubah_pada"])
    return audit


@transaction.atomic
def buka_kunci(audit, oleh, alasan, batas_baru=None):
    """FR-23 / Bab 4: Master Admin membuka kunci SER atau memperpanjang batas, alasan wajib."""
    alasan = (alasan or "").strip()
    if not alasan:
        raise ValidationError("Alasan wajib diisi.")
    hari_ini = timezone.localdate()
    if batas_baru is not None and batas_baru < hari_ini:
        raise ValidationError("Batas baru tidak boleh sebelum hari ini.")
    batas_efektif = batas_baru or audit.batas_ser
    if batas_efektif is not None and batas_efektif < hari_ini:
        raise ValidationError("Batas pengisian SER sudah lewat. Tetapkan batas baru.")

    if audit.status == Audit.Status.PENILAIAN_AUDITOR:
        from .penilaian import reset_kunci_semua

        status.ubah_status(audit, Audit.Status.PENGISIAN_SER, oleh, alasan=f"Buka kunci SER: {alasan}")
        # Isian auditee akan berubah, jadi auditor menilai ulang; draf penilaian tetap tersimpan.
        reset_kunci_semua(audit, oleh, "SER dibuka kembali.")
    elif audit.status in Audit.STATUS_SER_TERBUKA:
        status.catat(audit, oleh, f"Perpanjangan batas SER: {alasan}")
        transaction.on_commit(lambda: batas_ser_diperpanjang.send(sender=Audit, audit=audit, alasan=alasan))
    else:
        raise ValidationError(f"SER tidak dapat dibuka kembali pada status {audit.get_status_display()}.")
    if batas_baru is not None:
        audit.batas_ser_khusus = batas_baru
        audit.save(update_fields=["batas_ser_khusus", "diubah_pada"])
    return audit
