"""Halaman Admin master data, impor (FR-09), salin (FR-11), dan hak akses (NFR-08)."""

from decimal import Decimal

import pytest
from django.urls import reverse

from masterdata.models import PengaturanPeriode, Periode, PernyataanStandar, Standar

from .conftest import baris_excel, berkas_excel

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "model",
    ["unit", "periode", "tipeunit", "lingkupbidang", "standar", "pernyataanstandar"],
)
def test_halaman_daftar_admin_terbuka(admin_client, model):
    assert admin_client.get(reverse(f"admin:masterdata_{model}_changelist")).status_code == 200


def test_halaman_tambah_periode_menampilkan_pengaturan_periode_terakhir(admin_client, periode):
    periode.pengaturan.kkm = Decimal("80")
    periode.pengaturan.save()
    resp = admin_client.get(reverse("admin:masterdata_periode_add"))
    assert resp.status_code == 200
    assert 'name="pengaturan-0-kkm" value="80.00"' in resp.content.decode()


def _data_periode_baru(**pengaturan):
    data = {
        "nama": "AMI 2026/2027",
        "tahun_akademik": "2026/2027",
        "tahapan-TOTAL_FORMS": "0",
        "tahapan-INITIAL_FORMS": "0",
        "pengaturan-TOTAL_FORMS": "1",
        "pengaturan-INITIAL_FORMS": "0",
    }
    nilai = {k: str(v) if v is not None else "" for k, v in PengaturanPeriode.nilai_awal().items()}
    nilai.update(pengaturan)
    data.update({f"pengaturan-0-{k}": v for k, v in nilai.items()})
    return data


def test_tambah_periode_tanpa_mengubah_pengaturan_tetap_membuat_pengaturan(admin_client):
    resp = admin_client.post(reverse("admin:masterdata_periode_add"), _data_periode_baru())
    assert resp.status_code == 302
    assert Periode.objects.get().pengaturan.kkm == 75


def test_tambah_periode_dengan_bobot_salah_ditolak(admin_client):
    resp = admin_client.post(reverse("admin:masterdata_periode_add"), _data_periode_baru(bobot_a="50"))
    assert resp.status_code == 200
    assert "100%" in resp.content.decode()
    assert not Periode.objects.exists()


def test_aksi_aktifkan_periode(admin_client, periode):
    resp = admin_client.post(
        reverse("admin:masterdata_periode_changelist"),
        {"action": "aktifkan_periode", "_selected_action": [periode.pk]},
    )
    assert resp.status_code == 302
    periode.refresh_from_db()
    assert periode.aktif


def test_pengaturan_institusi_langsung_ke_formulir(admin_client):
    resp = admin_client.get(reverse("admin:masterdata_pengaturaninstitusi_changelist"))
    assert resp.status_code == 302
    assert resp.url == reverse("admin:masterdata_pengaturaninstitusi_change", args=[1])


# --- Impor (FR-09) ----------------------------------------------------------------

URL_IMPOR = "admin:masterdata_standar_impor"


def test_halaman_impor_dan_tautan_template(admin_client, periode):
    isi = admin_client.get(reverse(URL_IMPOR)).content.decode()
    assert "template_impor_standar.xlsx" in isi
    daftar = admin_client.get(reverse("admin:masterdata_standar_changelist")).content.decode()
    assert reverse(URL_IMPOR) in daftar


def test_impor_pratinjau_lalu_simpan(admin_client, periode, lingkup):
    berkas = berkas_excel([baris_excel(), baris_excel(kode_pernyataan="1.2")])
    resp = admin_client.post(reverse(URL_IMPOR), {"periode": periode.pk, "berkas": berkas, "aksi": "pratinjau"})
    assert resp.status_code == 200
    assert "Semua baris valid" in resp.content.decode()
    assert not Standar.objects.exists()  # belum disimpan sebelum konfirmasi

    resp = admin_client.post(reverse(URL_IMPOR), {"aksi": "simpan"})
    assert resp.status_code == 302
    assert PernyataanStandar.objects.filter(standar__periode=periode).count() == 2


def test_impor_dengan_galat_tidak_menampilkan_tombol_simpan(admin_client, periode, lingkup):
    berkas = berkas_excel([baris_excel(lingkup="Salah")])
    resp = admin_client.post(reverse(URL_IMPOR), {"periode": periode.pk, "berkas": berkas, "aksi": "pratinjau"})
    isi = resp.content.decode()
    assert "1 baris bermasalah" in isi
    assert 'value="simpan"' not in isi


def test_simpan_tanpa_pratinjau_dialihkan(admin_client):
    resp = admin_client.post(reverse(URL_IMPOR), {"aksi": "simpan"})
    assert resp.status_code == 302
    assert not Standar.objects.exists()


def test_galat_berkas_ditampilkan_di_formulir(admin_client, periode):
    from django.core.files.uploadedfile import SimpleUploadedFile

    resp = admin_client.post(
        reverse(URL_IMPOR),
        {"periode": periode.pk, "berkas": SimpleUploadedFile("a.csv", b"x"), "aksi": "pratinjau"},
    )
    assert resp.status_code == 200
    assert ".xlsx" in resp.content.decode()


def test_impor_ditolak_untuk_staf_tanpa_izin(client, django_user_model, periode):
    # NFR-08: diperiksa di server, bukan hanya disembunyikan dari menu
    from accounts.peran import Peran

    staf = django_user_model.objects.create_user("staf@unika.ac.id", peran=Peran.ADMIN)
    staf.groups.clear()  # staf tanpa izin apa pun
    client.force_login(staf)
    assert client.get(reverse(URL_IMPOR)).status_code == 403
    url_salin = reverse("admin:masterdata_periode_salin_standar", args=[periode.pk])
    assert client.get(url_salin).status_code == 403


def test_impor_dialihkan_ke_login_bila_belum_masuk(client):
    resp = client.get(reverse(URL_IMPOR))
    assert resp.status_code == 302 and "login" in resp.url


# --- Salin (FR-11) ----------------------------------------------------------------

def test_salin_standar_lewat_admin(admin_client, periode, lingkup):
    Standar.objects.create(periode=periode, kode="1", nama="A", lingkup=lingkup)
    baru = Periode.objects.create(nama="AMI 2026/2027", tahun_akademik="2026/2027")
    url = reverse("admin:masterdata_periode_salin_standar", args=[baru.pk])
    assert admin_client.get(url).status_code == 200
    resp = admin_client.post(url, {"asal": periode.pk})
    assert resp.status_code == 302
    assert baru.standar.count() == 1


def test_salin_ke_periode_berisi_menampilkan_pesan(admin_client, periode, lingkup):
    baru = Periode.objects.create(nama="AMI 2026/2027", tahun_akademik="2026/2027")
    Standar.objects.create(periode=periode, kode="1", nama="A", lingkup=lingkup)
    Standar.objects.create(periode=baru, kode="1", nama="A", lingkup=lingkup)
    resp = admin_client.post(reverse("admin:masterdata_periode_salin_standar", args=[baru.pk]), {"asal": periode.pk})
    assert resp.status_code == 200
    assert "sudah memiliki standar" in resp.content.decode()
