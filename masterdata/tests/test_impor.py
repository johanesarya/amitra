"""Impor standar dari Excel (FR-09)."""

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import load_workbook

from masterdata import impor
from masterdata.models import PernyataanStandar, Standar, TipeUnit

from .conftest import baris_excel, berkas_excel

pytestmark = pytest.mark.django_db

TEMPLATE = Path(__file__).resolve().parents[1] / "static" / "masterdata" / "template_impor_standar.xlsx"


def test_template_statis_sesuai_kolom_impor():
    ws = load_workbook(TEMPLATE)["Standar"]
    assert [c.value for c in ws[1]] == [label for _, label in impor.KOLOM]


def test_template_bisa_dibaca_ulang_tanpa_baris_data():
    with TEMPLATE.open("rb") as f:
        berkas = SimpleUploadedFile("template.xlsx", f.read())
    with pytest.raises(impor.GalatImpor, match="Tidak ada baris data"):
        impor.baca_berkas(berkas)


def test_baca_berkas_mengembalikan_nomor_baris_excel():
    berkas = berkas_excel([baris_excel(), {}, baris_excel(kode_pernyataan="1.2")])
    baris = impor.baca_berkas(berkas)
    assert [n for n, _ in baris] == [2, 4]  # baris kosong dilewati, nomor tetap
    assert baris[0][1]["kode_pernyataan"] == "1.1"


def test_angka_bulat_dari_excel_menjadi_teks_tanpa_desimal():
    berkas = berkas_excel([baris_excel(kode_standar=2, urutan_standar=3)])
    data = impor.baca_berkas(berkas)[0][1]
    assert data["kode_standar"] == "2" and data["urutan_standar"] == "3"


def test_berkas_bukan_xlsx_ditolak():
    with pytest.raises(impor.GalatImpor, match=".xlsx"):
        impor.baca_berkas(SimpleUploadedFile("data.csv", b"a,b"))


def test_berkas_rusak_ditolak():
    with pytest.raises(impor.GalatImpor, match="tidak valid|bukan Excel"):
        impor.baca_berkas(SimpleUploadedFile("rusak.xlsx", b"bukan zip"))


def test_berkas_terlalu_besar_ditolak():
    berkas = SimpleUploadedFile("besar.xlsx", b"0" * (impor.UKURAN_MAKS + 1))
    with pytest.raises(impor.GalatImpor, match="2 MB"):
        impor.baca_berkas(berkas)


def test_kolom_judul_hilang_dilaporkan():
    header = [label for _, label in impor.KOLOM if label != "Pernyataan Standar"]
    with pytest.raises(impor.GalatImpor, match="Pernyataan Standar"):
        impor.baca_berkas(berkas_excel([baris_excel()], header=header))


def test_validasi_galat_per_baris(periode, lingkup):
    baris = [
        (2, baris_excel()),
        (3, baris_excel(kode_pernyataan="1.2", pernyataan="")),
        (4, baris_excel(kode_pernyataan="1.3", lingkup="Tidak Ada")),
        (5, baris_excel(kode_pernyataan="1.4", tipe_unit="PRODI_S1, Koperasi")),
        (6, baris_excel(kode_pernyataan="1.1")),  # duplikat baris 2
        (7, baris_excel(kode_pernyataan="1.5", nama_standar="Nama lain")),  # tidak konsisten
        (8, baris_excel(kode_pernyataan="1.6", bobot="abc", urutan_pernyataan="-1")),
    ]
    hasil = impor.validasi(baris, periode)
    galat = {b.nomor: " ".join(b.galat) for b in hasil.baris}
    assert galat[2] == ""
    assert "Pernyataan Standar wajib diisi" in galat[3]
    assert "Tidak Ada" in galat[4]
    assert "Koperasi" in galat[5]
    assert "baris 2" in galat[6]
    assert "berbeda dengan baris 2" in galat[7]
    assert "Bobot" in galat[8] and "Urutan Pernyataan" in galat[8]
    assert hasil.ada_galat and hasil.jumlah_galat == 6


def test_simpan_ditolak_bila_ada_galat(periode, lingkup):
    hasil = impor.validasi([(2, baris_excel(pernyataan=""))], periode)
    with pytest.raises(ValueError):
        impor.simpan(hasil, periode)
    assert not Standar.objects.exists()


def test_simpan_membuat_standar_dan_pernyataan(periode, lingkup):
    baris = [
        (2, baris_excel(bobot="2,5")),
        (3, baris_excel(kode_pernyataan="1.2", bobot="2,5", tipe_unit="Prodi S1; prodi s2", urutan_pernyataan="2")),
    ]
    hasil = impor.validasi(baris, periode)
    assert [b.status for b in hasil.baris] == ["baru", "baru"]
    ringkasan = impor.simpan(hasil, periode)
    assert ringkasan == {"standar_baru": 1, "standar_diperbarui": 0, "pernyataan_baru": 2, "pernyataan_diperbarui": 0}

    s = Standar.objects.get(periode=periode, kode="1")
    assert s.lingkup == lingkup and str(s.bobot) == "2.50" and s.sumber == Standar.Sumber.LPM
    p = PernyataanStandar.objects.get(standar=s, kode="1.2")
    assert set(p.tipe_unit.values_list("kode", flat=True)) == {TipeUnit.PRODI_S1, TipeUnit.PRODI_S2}


def test_impor_ulang_memperbarui_bukan_menduplikasi(periode, lingkup):
    impor.simpan(impor.validasi([(2, baris_excel())], periode), periode)
    hasil = impor.validasi([(2, baris_excel(pernyataan="Teks baru", tipe_unit="FAKULTAS"))], periode)
    assert hasil.baris[0].status == "diperbarui"
    ringkasan = impor.simpan(hasil, periode)
    assert ringkasan["pernyataan_diperbarui"] == 1
    p = PernyataanStandar.objects.get()
    assert p.pernyataan == "Teks baru"
    assert list(p.tipe_unit.values_list("kode", flat=True)) == [TipeUnit.FAKULTAS]


def test_kode_standar_turunan_tidak_boleh_ditimpa_impor(periode, lingkup, prodi):
    Standar.objects.create(
        periode=periode, kode="1", nama="Turunan", lingkup=lingkup,
        sumber=Standar.Sumber.TURUNAN, unit_pengusul=prodi,
    )
    hasil = impor.validasi([(2, baris_excel())], periode)
    assert "standar turunan" in hasil.baris[0].galat[0]
