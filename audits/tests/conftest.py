import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from accounts.peran import Peran
from masterdata.models import (
    LingkupBidang,
    PengaturanPeriode,
    Periode,
    PernyataanStandar,
    Standar,
    TipeUnit,
    Unit,
)

User = get_user_model()


@pytest.fixture
def periode(db):
    p = Periode.objects.create(nama="AMI 2025/2026", tahun_akademik="2025/2026", aktif=True)
    PengaturanPeriode.pastikan_ada(p)
    return p


@pytest.fixture
def lingkup(db):
    return LingkupBidang.objects.create(nama="Pendidikan")


@pytest.fixture
def fakultas(db):
    return Unit.objects.create(nama="Fakultas Teknik", kode="FT", tipe_id=TipeUnit.FAKULTAS)


@pytest.fixture
def prodi(fakultas):
    return Unit.objects.create(nama="Teknik Elektro", kode="TE", tipe_id=TipeUnit.PRODI_S1, induk=fakultas)


@pytest.fixture
def prodi_lain(fakultas):
    return Unit.objects.create(nama="Teknik Sipil", kode="TS", tipe_id=TipeUnit.PRODI_S1, induk=fakultas)


@pytest.fixture
def standar(periode, lingkup):
    s = Standar.objects.create(periode=periode, kode="1", nama="Kompetensi Lulusan", lingkup=lingkup)
    p = PernyataanStandar.objects.create(standar=s, kode="1.1", pernyataan="Prodi memiliki profil lulusan.")
    p.tipe_unit.set([TipeUnit.PRODI_S1])
    return s


def buat_pengguna(nama, peran=Peran.PENGGUNA, **extra):
    return User.objects.create_user(f"{nama.lower()}@unika.ac.id", nama=nama, peran=peran, **extra)


@pytest.fixture
def auditee(db, prodi):
    return buat_pengguna("Kaprodi", homebase=prodi)


@pytest.fixture
def auditor(db):
    return [buat_pengguna(n) for n in ["Ani", "Budi", "Citra", "Dedi", "Eka"]]


@pytest.fixture
def admin_lpm(db):
    return buat_pengguna("StafLPM", peran=Peran.ADMIN)


@pytest.fixture
def tim(periode, prodi, lingkup, standar, auditee, auditor):
    """Argumen lengkap dan valid untuk simpan_audit/periksa_tim."""
    return {
        "periode": periode,
        "unit": prodi,
        "lingkup": [lingkup],
        "auditee": auditee,
        "auditor": auditor[:3],
        "ketua": auditor[0],
    }


def berkas_excel(kolom, baris, nama_sheet="Plot Audit"):
    wb = Workbook()
    ws = wb.active
    ws.title = nama_sheet
    ws.append([label for _, label in kolom])
    for b in baris:
        ws.append([b.get(k, "") for k, _ in kolom])
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile("plot.xlsx", buf.getvalue())
