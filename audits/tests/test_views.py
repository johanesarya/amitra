"""Halaman Plot Audit, akses per penugasan (NFR-08, FR-16), dan FR-17."""

import json
import re

import pytest
from django.urls import reverse

from accounts.peran import Peran
from audits.layanan import simpan_audit
from audits.models import Audit

from .conftest import buat_pengguna

pytestmark = pytest.mark.django_db


@pytest.fixture
def audit(tim, admin_lpm):
    return simpan_audit(**tim, oleh=admin_lpm)


def data_form(tim, **ubah):
    data = {
        "periode": tim["periode"].pk,
        "unit": tim["unit"].pk,
        "lingkup": [l.pk for l in tim["lingkup"]],
        "auditee": tim["auditee"].pk,
        "auditor": [a.pk for a in tim["auditor"]],
        "ketua": tim["ketua"].pk,
        "jadwal_audit_lapangan": "2026-02-20T09:00",
    }
    data.update(ubah)
    return data


# --- Hak akses plot (Bab 4, NFR-08) ------------------------------------------------

@pytest.mark.parametrize("nama_url", ["audits:daftar", "audits:buat", "audits:impor"])
@pytest.mark.parametrize("peran, status", [
    (Peran.ADMIN, 200), (Peran.MASTER_ADMIN, 200), (Peran.PENGGUNA, 403), (Peran.VIEWER, 403),
])
def test_hak_akses_halaman_plot(client, periode, nama_url, peran, status):
    client.force_login(buat_pengguna("Uji", peran=peran))
    assert client.get(reverse(nama_url)).status_code == status


def test_pengguna_biasa_tidak_bisa_post_plot(client, tim, auditor):
    client.force_login(auditor[4])
    assert client.post(reverse("audits:buat"), data_form(tim)).status_code == 403
    assert not Audit.objects.exists()


def test_periksa_tim_ditolak_untuk_pengguna_biasa(client, tim, auditor):
    client.force_login(auditor[4])
    assert client.post(reverse("audits:periksa_tim"), data_form(tim)).status_code == 403


# --- Buat dan ubah audit -----------------------------------------------------------

def test_buat_audit_lewat_formulir(client, tim, admin_lpm):
    client.force_login(admin_lpm)
    resp = client.post(reverse("audits:buat"), data_form(tim))
    assert resp.status_code == 302
    audit = Audit.objects.get()
    assert audit.ketua == tim["ketua"] and len(audit.auditor) == 3
    assert audit.jadwal_audit_lapangan is not None


def test_galat_menampilkan_pesan_spesifik_dan_isian_tidak_hilang(client, tim, admin_lpm, auditor):
    # FR-17: pesan spesifik, bukan "koneksi server gagal"; data form tetap
    client.force_login(admin_lpm)
    pilihan = [auditor[0].pk, auditor[1].pk]
    resp = client.post(reverse("audits:buat"), data_form(tim, auditor=pilihan))
    assert resp.status_code == 200
    isi = resp.content.decode()
    assert "Jumlah auditor harus ganjil" in isi or "minimal 3" in isi
    assert resp.context["form"].id_auditor_terpilih() == [str(pk) for pk in pilihan]
    terpilih_di_halaman = re.search(r'<script id="data-terpilih"[^>]*>(.*?)</script>', isi).group(1)
    assert json.loads(terpilih_di_halaman) == [str(pk) for pk in pilihan]
    assert f'<option value="{tim["unit"].pk}" selected>' in isi
    assert not Audit.objects.exists()


def test_periksa_tim_htmx(client, tim, admin_lpm, auditor):
    client.force_login(admin_lpm)
    ok = client.post(reverse("audits:periksa_tim"), data_form(tim)).content.decode()
    assert "siap disimpan" in ok
    salah = client.post(reverse("audits:periksa_tim"), data_form(tim, ketua=auditor[4].pk)).content.decode()
    assert "Belum dapat disimpan" in salah and "harus salah satu auditor" in salah


def test_formulir_menampilkan_beban_dan_tanda_konflik(client, tim, admin_lpm, audit, auditor, prodi):
    auditor[3].homebase = prodi
    auditor[3].save()
    client.force_login(admin_lpm)
    resp = client.get(reverse("audits:buat"))
    calon = {c["user"].pk: c for c in resp.context["calon_auditor"]}
    assert calon[auditor[0].pk]["beban"] == 1
    assert calon[auditor[4].pk]["beban"] == 0
    assert prodi.pk in calon[auditor[3].pk]["unit_konflik"]


def test_ubah_tim(client, tim, admin_lpm, audit, auditor):
    client.force_login(admin_lpm)
    url = reverse("audits:ubah", args=[audit.pk])
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.context["form"].id_ketua_terpilih() == str(tim["ketua"].pk)
    resp = client.post(url, data_form(tim, auditor=[a.pk for a in auditor[2:5]], ketua=auditor[2].pk, audit=audit.pk))
    assert resp.status_code == 302
    assert Audit.objects.get().ketua == auditor[2]


def test_ubah_tim_ditolak_setelah_penilaian_dimulai(client, tim, admin_lpm, audit):
    audit.status = Audit.Status.PENILAIAN_AUDITOR
    audit.save()
    client.force_login(admin_lpm)
    resp = client.post(reverse("audits:ubah", args=[audit.pk]), data_form(tim))
    assert resp.status_code == 200
    assert "Tim tidak dapat diubah" in resp.content.decode()


def test_daftar_dan_filter(client, tim, admin_lpm, audit, fakultas):
    client.force_login(admin_lpm)
    isi = client.get(reverse("audits:daftar")).content.decode()
    assert "Teknik Elektro" in isi and "Ani" in isi
    kosong = client.get(reverse("audits:daftar"), {"periode": tim["periode"].pk, "status": "FINAL"})
    assert list(kosong.context["daftar_audit"]) == []
    per_fakultas = client.get(reverse("audits:daftar"), {"periode": tim["periode"].pk, "fakultas": fakultas.pk})
    assert list(per_fakultas.context["daftar_audit"]) == [audit]


def test_hapus_audit_belum_mulai(client, admin_lpm, audit):
    client.force_login(admin_lpm)
    url = reverse("audits:hapus", args=[audit.pk])
    assert client.get(url).status_code == 200  # ringkasan konfirmasi (NFR-21)
    assert client.post(url).status_code == 302
    assert not Audit.objects.exists()


def test_hapus_ditolak_setelah_dimulai(client, admin_lpm, audit):
    audit.status = Audit.Status.PENGISIAN_SER
    audit.save()
    client.force_login(admin_lpm)
    client.post(reverse("audits:hapus", args=[audit.pk]))
    assert Audit.objects.exists()


# --- Akses per penugasan dan FR-16 --------------------------------------------------

def test_auditor_melihat_standar_segera_setelah_diplot(client, audit, auditor):
    client.force_login(auditor[1])
    resp = client.get(reverse("audits:detail", args=[audit.pk]))
    assert resp.status_code == 200
    isi = resp.content.decode()
    assert "Prodi memiliki profil lulusan." in isi
    assert "Peran Anda di audit ini" in isi


def test_auditee_melihat_audit_unitnya(client, audit, auditee):
    client.force_login(auditee)
    assert client.get(reverse("audits:detail", args=[audit.pk])).status_code == 200


def test_pengguna_lain_ditolak_walau_tahu_url(client, audit):
    client.force_login(buat_pengguna("Orang"))
    assert client.get(reverse("audits:detail", args=[audit.pk])).status_code == 403


def test_viewer_tidak_bisa_melihat_detail_audit(client, audit):
    client.force_login(buat_pengguna("Rektor", peran=Peran.VIEWER))
    assert client.get(reverse("audits:detail", args=[audit.pk])).status_code == 403


def test_admin_lpm_melihat_semua_audit(client, audit, admin_lpm):
    client.force_login(admin_lpm)
    assert client.get(reverse("audits:detail", args=[audit.pk])).status_code == 200


def test_tamu_dialihkan_ke_login(client, audit):
    resp = client.get(reverse("audits:detail", args=[audit.pk]))
    assert resp.status_code == 302 and reverse("account_login") in resp.url


def test_tugas_saya_menampilkan_penugasan(client, audit, auditor):
    client.force_login(auditor[0])
    isi = client.get(reverse("beranda")).content.decode()
    assert "Teknik Elektro" in isi and "Ketua auditor" in isi
