"""Plot massal dari Excel (FR-15)."""

from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from audits import impor_plot
from audits.layanan import simpan_audit
from audits.models import Audit

from .conftest import berkas_excel

pytestmark = pytest.mark.django_db

TEMPLATE = Path(__file__).resolve().parents[1] / "static" / "audits" / "template_plot_audit.xlsx"


def baris(tim, **ubah):
    data = {
        "kode_unit": tim["unit"].kode,
        "lingkup": tim["lingkup"][0].nama,
        "auditee": tim["auditee"].email,
        "auditor": ", ".join(a.email for a in tim["auditor"]),
        "ketua": tim["ketua"].email,
        "jadwal": "",
    }
    data.update(ubah)
    return data


def test_template_statis_sesuai_kolom():
    ws = load_workbook(TEMPLATE)["Plot Audit"]
    assert [c.value for c in ws[1]] == [label for _, label in impor_plot.KOLOM]


def test_validasi_dan_simpan(tim, admin_lpm, prodi_lain, auditor):
    data = [
        (2, baris(tim, jadwal="2026-02-20 09:00")),
        (3, baris(tim, kode_unit="ts", auditor=f"{auditor[2].email}; {auditor[3].email}; {auditor[4].email}",
                  ketua=auditor[3].email.upper())),
    ]
    hasil = impor_plot.validasi(data, tim["periode"])
    assert [b.galat for b in hasil.baris] == [[], []]
    assert impor_plot.simpan(hasil, tim["periode"], admin_lpm) == 2
    a1 = Audit.objects.get(unit=tim["unit"])
    assert timezone.localtime(a1.jadwal_audit_lapangan).strftime("%Y-%m-%d %H:%M") == "2026-02-20 09:00"
    assert Audit.objects.get(unit=prodi_lain).ketua == auditor[3]


def test_galat_per_baris(tim, admin_lpm, auditor, prodi_lain):
    simpan_audit(**{**tim, "unit": prodi_lain}, oleh=admin_lpm)
    data = [
        (2, baris(tim, kode_unit="XX")),
        (3, baris(tim, auditee="tidakada@unika.ac.id")),
        (4, baris(tim, lingkup="Antah")),
        (5, baris(tim, auditor=f"{auditor[0].email}, {auditor[1].email}")),
        (6, baris(tim, jadwal="besok pagi")),
        (7, baris(tim, kode_unit=prodi_lain.kode)),  # sudah diaudit
        (8, baris(tim)),
        (9, baris(tim)),  # unit sama dengan baris 8
        (10, baris(tim, ketua="")),
    ]
    galat = {b.nomor: " ".join(b.galat) for b in impor_plot.validasi(data, tim["periode"]).baris}
    assert "kode \"XX\" tidak ditemukan" in galat[2]
    assert "tidakada@unika.ac.id belum terdaftar" in galat[3]
    assert "\"Antah\" tidak dikenal" in galat[4]
    assert "ganjil" in galat[5] or "minimal" in galat[5]
    assert "Jadwal Audit Lapangan harus berformat" in galat[6]
    assert "sudah memiliki audit" in galat[7]
    assert "sudah ada di baris" in galat[9]
    assert "Email Ketua wajib diisi" in galat[10]


def test_satu_baris_salah_tidak_menyimpan_apa_pun(tim, admin_lpm):
    hasil = impor_plot.validasi([(2, baris(tim)), (3, baris(tim, kode_unit="XX"))], tim["periode"])
    with pytest.raises(ValueError):
        impor_plot.simpan(hasil, tim["periode"], admin_lpm)
    assert not Audit.objects.exists()


def test_alur_impor_lewat_halaman(client, tim, admin_lpm):
    client.force_login(admin_lpm)
    berkas = berkas_excel(impor_plot.KOLOM, [baris(tim)])
    resp = client.post(reverse("audits:impor"), {"periode": tim["periode"].pk, "berkas": berkas, "aksi": "pratinjau"})
    assert resp.status_code == 200 and "Semua baris valid" in resp.content.decode()
    assert not Audit.objects.exists()
    resp = client.post(reverse("audits:impor"), {"aksi": "simpan"})
    assert resp.status_code == 302
    assert Audit.objects.count() == 1


def test_berkas_salah_ditampilkan_di_formulir(client, tim, admin_lpm):
    from django.core.files.uploadedfile import SimpleUploadedFile

    client.force_login(admin_lpm)
    resp = client.post(
        reverse("audits:impor"),
        {"periode": tim["periode"].pk, "berkas": SimpleUploadedFile("a.csv", b"x"), "aksi": "pratinjau"},
    )
    assert ".xlsx" in resp.content.decode()
