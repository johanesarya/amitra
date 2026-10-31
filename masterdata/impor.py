"""Impor massal standar dan pernyataan standar dari Excel (FR-09).

Alur: `baca_berkas()` → `validasi()` (pratinjau dengan galat per baris) →
`simpan()` dalam satu transaksi. Baris mentah berupa dict string agar bisa
disimpan di sesi di antara pratinjau dan konfirmasi, lalu divalidasi ulang.
"""

import re
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .excel import BARIS_MAKS, UKURAN_MAKS, BarisImpor, GalatImpor, HasilImpor, baca_tabel
from .excel import buat_template as _buat_template
from .models import LingkupBidang, PernyataanStandar, Standar, TipeUnit

__all__ = ["BARIS_MAKS", "UKURAN_MAKS", "GalatImpor", "HasilImpor", "baca_berkas", "buat_template", "simpan", "validasi"]

KOLOM = [
    ("kode_standar", "Kode Standar"),
    ("nama_standar", "Nama Standar"),
    ("lingkup", "Lingkup Bidang"),
    ("bobot", "Bobot"),
    ("urutan_standar", "Urutan Standar"),
    ("kode_pernyataan", "Kode Pernyataan"),
    ("pernyataan", "Pernyataan Standar"),
    ("pertanyaan_panduan", "Pertanyaan Panduan"),
    ("tipe_unit", "Berlaku untuk Tipe Unit"),
    ("urutan_pernyataan", "Urutan Pernyataan"),
]
KOLOM_WAJIB = ["kode_standar", "nama_standar", "lingkup", "kode_pernyataan", "pernyataan", "tipe_unit"]
KOLOM_TEKS = ["kode_standar", "kode_pernyataan"]
NAMA_SHEET = "Standar"


def baca_berkas(berkas) -> list[tuple[int, dict]]:
    """Baca berkas .xlsx menjadi daftar (nomor baris Excel, dict kolom → teks)."""
    return baca_tabel(berkas, KOLOM, NAMA_SHEET)


def _desimal(teks):
    try:
        return Decimal(teks.replace(",", "."))
    except InvalidOperation:
        return None


def _bulat(teks):
    return int(teks) if teks.isdigit() else None


def validasi(baris_mentah, periode) -> HasilImpor:
    lingkup = {l.nama.lower(): l for l in LingkupBidang.objects.all()}
    tipe = {}
    for t in TipeUnit.objects.all():
        tipe[t.kode.lower()] = t.kode
        tipe[t.nama.lower()] = t.kode
    standar_ada = {s.kode: s for s in Standar.objects.filter(periode=periode)}
    pernyataan_ada = set(
        PernyataanStandar.objects.filter(standar__periode=periode).values_list("standar__kode", "kode")
    )

    hasil = []
    standar_pertama = {}  # kode → (nomor baris, atribut standar)
    pasangan = {}  # (kode standar, kode pernyataan) → nomor baris
    for nomor, data in baris_mentah:
        data = {k: (data.get(k) or "").strip() for k, _ in KOLOM}
        b = BarisImpor(nomor=nomor, data=data)
        hasil.append(b)

        for kunci in KOLOM_WAJIB:
            if not data.get(kunci):
                b.galat.append(f"{dict(KOLOM)[kunci]} wajib diisi.")

        if data["lingkup"] and data["lingkup"].lower() not in lingkup:
            b.galat.append(f"Lingkup bidang \"{data['lingkup']}\" tidak dikenal. Tambahkan dulu di menu Lingkup Bidang.")

        if data["tipe_unit"]:
            for bagian in filter(None, (x.strip() for x in re.split(r"[,;]", data["tipe_unit"]))):
                if bagian.lower() not in tipe:
                    b.galat.append(f"Tipe unit \"{bagian}\" tidak dikenal.")

        if data["bobot"] and _desimal(data["bobot"]) is None:
            b.galat.append("Bobot harus berupa angka.")
        for kunci in ("urutan_standar", "urutan_pernyataan"):
            if data[kunci] and _bulat(data[kunci]) is None:
                b.galat.append(f"{dict(KOLOM)[kunci]} harus bilangan bulat ≥ 0.")

        kode_s, kode_p = data["kode_standar"], data["kode_pernyataan"]
        if kode_s:
            atribut = (data["nama_standar"], data["lingkup"].lower(), data["bobot"], data["urutan_standar"])
            if kode_s not in standar_pertama:
                standar_pertama[kode_s] = (nomor, atribut)
            elif standar_pertama[kode_s][1] != atribut:
                b.galat.append(
                    f"Nama, lingkup, bobot, atau urutan standar {kode_s} berbeda dengan baris {standar_pertama[kode_s][0]}."
                )
            ada = standar_ada.get(kode_s)
            if ada is not None and ada.sumber != Standar.Sumber.LPM:
                b.galat.append(f"Kode {kode_s} sudah dipakai standar turunan di periode ini.")

        if kode_s and kode_p:
            if (kode_s, kode_p) in pasangan:
                b.galat.append(f"Pernyataan {kode_p} pada standar {kode_s} sudah ada di baris {pasangan[(kode_s, kode_p)]}.")
            else:
                pasangan[(kode_s, kode_p)] = nomor
            b.status = "diperbarui" if (kode_s, kode_p) in pernyataan_ada else "baru"

    return HasilImpor(baris=hasil)


@transaction.atomic
def simpan(hasil: HasilImpor, periode) -> dict:
    """Simpan hasil validasi tanpa galat. Kode yang sudah ada diperbarui."""
    if hasil.ada_galat:
        raise ValueError("Hasil impor masih memiliki galat.")
    lingkup = {l.nama.lower(): l for l in LingkupBidang.objects.all()}
    tipe = {}
    for t in TipeUnit.objects.all():
        tipe[t.kode.lower()] = t.kode
        tipe[t.nama.lower()] = t.kode

    ringkasan = {"standar_baru": 0, "standar_diperbarui": 0, "pernyataan_baru": 0, "pernyataan_diperbarui": 0}
    standar = {}
    for b in hasil.baris:
        d = b.data
        kode_s = d["kode_standar"]
        if kode_s not in standar:
            standar[kode_s], dibuat = Standar.objects.update_or_create(
                periode=periode,
                kode=kode_s,
                defaults={
                    "nama": d["nama_standar"],
                    "lingkup": lingkup[d["lingkup"].lower()],
                    "bobot": _desimal(d["bobot"]) if d["bobot"] else None,
                    "urutan": _bulat(d["urutan_standar"]) or 0,
                    "sumber": Standar.Sumber.LPM,
                    "status": Standar.Status.DISETUJUI,
                },
            )
            ringkasan["standar_baru" if dibuat else "standar_diperbarui"] += 1

        pernyataan, dibuat = PernyataanStandar.objects.update_or_create(
            standar=standar[kode_s],
            kode=d["kode_pernyataan"],
            defaults={
                "pernyataan": d["pernyataan"],
                "pertanyaan_panduan": d["pertanyaan_panduan"],
                "urutan": _bulat(d["urutan_pernyataan"]) or 0,
            },
        )
        kode_tipe = {tipe[x.strip().lower()] for x in re.split(r"[,;]", d["tipe_unit"]) if x.strip()}
        pernyataan.tipe_unit.set(kode_tipe)
        ringkasan["pernyataan_baru" if dibuat else "pernyataan_diperbarui"] += 1
    return ringkasan


def buat_template():
    """Template impor kosong beserta sheet petunjuk."""
    return _buat_template(
        NAMA_SHEET,
        KOLOM,
        kolom_teks=KOLOM_TEKS,
        lebar={"nama_standar": 40, "pernyataan": 60, "pertanyaan_panduan": 60, "tipe_unit": 30},
        baris_tebal=(1, 13),
        petunjuk=[
            ("Kolom", "Keterangan"),
            ("Kode Standar", "Wajib. Satu standar boleh muncul di banyak baris (satu baris per pernyataan)."),
            ("Nama Standar", "Wajib. Harus sama di semua baris dengan kode standar yang sama."),
            ("Lingkup Bidang", "Wajib. Harus sama dengan nama di menu Lingkup Bidang."),
            ("Bobot", "Opsional, angka. Hanya disimpan; tidak dipakai dalam perhitungan nilai."),
            ("Urutan Standar", "Opsional, bilangan bulat."),
            ("Kode Pernyataan", "Wajib, mis. 2.4*. Unik dalam satu standar."),
            ("Pernyataan Standar", "Wajib."),
            ("Pertanyaan Panduan", "Opsional."),
            ("Berlaku untuk Tipe Unit", "Wajib. Satu atau beberapa tipe dipisah koma, kode atau nama."),
            ("Urutan Pernyataan", "Opsional, bilangan bulat."),
            ("", ""),
            ("Kode tipe unit", "Nama"),
            ("FAKULTAS", "Fakultas"),
            ("PRODI_S1", "Prodi S1"),
            ("PRODI_S2", "Prodi S2"),
            ("PRODI_S3", "Prodi S3"),
            ("PRODI_PROFESI", "Prodi Profesi"),
            ("LEMBAGA", "Lembaga"),
            ("BIRO", "Biro"),
            ("UPT", "UPT"),
            ("", ""),
            ("Catatan", "Kode standar/pernyataan yang sudah ada di periode tujuan akan diperbarui, bukan diduplikasi."),
        ],
    )
