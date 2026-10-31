import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from masterdata.impor import KOLOM
from masterdata.models import LingkupBidang, PengaturanPeriode, Periode, TipeUnit, Unit


@pytest.fixture
def periode(db):
    p = Periode.objects.create(nama="AMI 2025/2026", tahun_akademik="2025/2026")
    PengaturanPeriode.pastikan_ada(p)
    return p


@pytest.fixture
def lingkup(db):
    return LingkupBidang.objects.create(nama="Pendidikan", urutan=1)


@pytest.fixture
def fakultas(db):
    return Unit.objects.create(nama="Fakultas Teknik", kode="FT", tipe_id=TipeUnit.FAKULTAS)


@pytest.fixture
def prodi(fakultas):
    return Unit.objects.create(nama="Teknik Elektro", kode="TE", tipe_id=TipeUnit.PRODI_S1, induk=fakultas)


def baris_excel(**isi):
    """Satu baris impor lengkap; kolom yang tidak disebut diisi nilai contoh."""
    data = {
        "kode_standar": "1",
        "nama_standar": "Standar Kompetensi Lulusan",
        "lingkup": "Pendidikan",
        "bobot": "",
        "urutan_standar": "1",
        "kode_pernyataan": "1.1",
        "pernyataan": "Prodi memiliki profil lulusan.",
        "pertanyaan_panduan": "Apakah profil lulusan terdokumentasi?",
        "tipe_unit": "PRODI_S1",
        "urutan_pernyataan": "1",
    }
    data.update(isi)
    return data


def berkas_excel(daftar_baris, header=None, nama="impor.xlsx"):
    wb = Workbook()
    ws = wb.active
    ws.title = "Standar"
    ws.append(header or [label for _, label in KOLOM])
    for b in daftar_baris:
        ws.append([b.get(k, "") for k, _ in KOLOM])
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(nama, buf.getvalue())
