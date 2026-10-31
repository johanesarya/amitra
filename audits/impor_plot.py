"""Plot massal audit dari Excel (FR-15).

Satu baris = satu audit baru. Setiap baris divalidasi dengan aturan yang sama
dengan formulir (`layanan.periksa_tim`), lalu semua baris disimpan dalam satu
transaksi.
"""

import re
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from masterdata.excel import BarisImpor, GalatImpor, HasilImpor, baca_tabel
from masterdata.excel import buat_template as _buat_template
from masterdata.models import LingkupBidang, Unit

from .layanan import periksa_tim, simpan_audit

KOLOM = [
    ("kode_unit", "Kode Unit"),
    ("lingkup", "Lingkup Bidang"),
    ("auditee", "Email Auditee"),
    ("auditor", "Email Auditor"),
    ("ketua", "Email Ketua"),
    ("jadwal", "Jadwal Audit Lapangan"),
]
__all__ = ["GalatImpor", "baca_berkas", "buat_template", "simpan", "validasi"]

KOLOM_WAJIB = ["kode_unit", "lingkup", "auditee", "auditor", "ketua"]
NAMA_SHEET = "Plot Audit"
FORMAT_JADWAL = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M"]


def baca_berkas(berkas):
    return baca_tabel(berkas, KOLOM, NAMA_SHEET)


def _pisah(teks):
    return [x.strip() for x in re.split(r"[,;\n]", teks or "") if x.strip()]


def _jadwal(teks):
    for fmt in FORMAT_JADWAL:
        try:
            return timezone.make_aware(datetime.strptime(teks, fmt))
        except ValueError:
            continue
    return None


def _uraikan(data, unit_map, lingkup_map, user_map):
    """Ubah satu baris teks menjadi objek; kembalikan (nilai, galat)."""
    galat = []
    label = dict(KOLOM)
    for k in KOLOM_WAJIB:
        if not data.get(k):
            galat.append(f"{label[k]} wajib diisi.")

    unit = unit_map.get(data["kode_unit"].lower()) if data["kode_unit"] else None
    if data["kode_unit"] and unit is None:
        galat.append(f"Unit dengan kode \"{data['kode_unit']}\" tidak ditemukan atau tidak aktif.")

    lingkup = []
    for nama in _pisah(data["lingkup"]):
        l = lingkup_map.get(nama.lower())
        if l is None:
            galat.append(f"Lingkup bidang \"{nama}\" tidak dikenal.")
        else:
            lingkup.append(l)

    def cari(email):
        u = user_map.get(email.lower())
        if u is None:
            galat.append(f"Pengguna dengan email {email} belum terdaftar.")
        return u

    auditee = cari(data["auditee"]) if data["auditee"] else None
    auditor = [u for u in (cari(e) for e in _pisah(data["auditor"])) if u is not None]
    ketua = cari(data["ketua"]) if data["ketua"] else None

    jadwal = None
    if data["jadwal"]:
        jadwal = _jadwal(data["jadwal"])
        if jadwal is None:
            galat.append("Jadwal Audit Lapangan harus berformat TTTT-BB-HH JJ:MM, mis. 2026-02-20 09:00.")

    nilai = {"unit": unit, "lingkup": lingkup, "auditee": auditee, "auditor": auditor, "ketua": ketua, "jadwal": jadwal}
    return nilai, galat


def _peta():
    unit_map = {u.kode.lower(): u for u in Unit.objects.filter(aktif=True).select_related("tipe")}
    lingkup_map = {l.nama.lower(): l for l in LingkupBidang.objects.all()}
    user_map = {u.email: u for u in User.objects.select_related("homebase").prefetch_related("unit_jabatan")}
    return unit_map, lingkup_map, user_map


def validasi(baris_mentah, periode):
    peta = _peta()
    hasil = []
    unit_pertama = {}
    for nomor, data in baris_mentah:
        data = {k: (data.get(k) or "").strip() for k, _ in KOLOM}
        b = BarisImpor(nomor=nomor, data=data, status="baru")
        hasil.append(b)
        nilai, galat_isian = _uraikan(data, *peta)
        b.galat = list(galat_isian)
        unit = nilai["unit"]
        if unit is not None:
            if unit.pk in unit_pertama:
                b.galat.append(f"{unit} sudah ada di baris {unit_pertama[unit.pk]}.")
            else:
                unit_pertama[unit.pk] = nomor
        if not galat_isian:
            # Tampilkan semua masalah tim sekaligus, termasuk saat unitnya ganda.
            b.galat += periksa_tim(
                periode=periode, unit=unit, lingkup=nilai["lingkup"], auditee=nilai["auditee"],
                auditor=nilai["auditor"], ketua=nilai["ketua"],
            )
    return HasilImpor(baris=hasil)


@transaction.atomic
def simpan(hasil, periode, oleh):
    if hasil.ada_galat:
        raise ValueError("Hasil impor masih memiliki galat.")
    peta = _peta()
    jumlah = 0
    for b in hasil.baris:
        nilai, galat = _uraikan(b.data, *peta)
        if galat:
            raise ValidationError(galat)
        simpan_audit(
            periode=periode, unit=nilai["unit"], lingkup=nilai["lingkup"], auditee=nilai["auditee"],
            auditor=nilai["auditor"], ketua=nilai["ketua"], jadwal_audit_lapangan=nilai["jadwal"], oleh=oleh,
        )
        jumlah += 1
    return jumlah


def buat_template():
    return _buat_template(
        NAMA_SHEET,
        KOLOM,
        kolom_teks=["kode_unit", "jadwal"],
        lebar={"lingkup": 30, "auditee": 30, "auditor": 60, "ketua": 30, "jadwal": 22},
        petunjuk=[
            ("Kolom", "Keterangan"),
            ("Kode Unit", "Wajib. Kode unit seperti di menu Unit. Satu baris = satu audit baru."),
            ("Lingkup Bidang", "Wajib. Satu atau beberapa nama lingkup, dipisah koma."),
            ("Email Auditee", "Wajib. Email pengguna yang sudah terdaftar dan sudah memiliki peran."),
            ("Email Auditor", "Wajib. Beberapa email dipisah koma; jumlahnya ganjil, minimal sesuai Pengaturan periode."),
            ("Email Ketua", "Wajib. Salah satu dari email auditor."),
            ("Jadwal Audit Lapangan", "Opsional, format TTTT-BB-HH JJ:MM, mis. 2026-02-20 09:00."),
            ("", ""),
            ("Catatan", "Auditor tidak boleh ber-homebase atau menjabat di unit yang diaudit. Unit yang sudah "
                        "memiliki audit di periode tujuan ditolak; ubah timnya lewat halaman audit."),
        ],
    )
