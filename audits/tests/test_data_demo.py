"""Perintah isi_data_demo (NFR-15): satu siklus penuh di berbagai status, lewat layanan aplikasi."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from accounts.jejak import periksa
from accounts.models import User
from audits.models import Audit
from findings.models import PTK

pytestmark = pytest.mark.django_db
S = Audit.Status


@pytest.fixture
def demo(settings, tmp_path):
    settings.DEBUG = True
    settings.MEDIA_ROOT = tmp_path
    call_command("isi_data_demo")


def status(kode, tahun="2025/2026"):
    return Audit.objects.get(unit__kode=kode, periode__tahun_akademik=tahun).status


def test_status_audit_demo(demo):
    assert status("DEMO-TE", "2024/2025") == S.TINDAK_LANJUT_PTK
    assert status("DEMO-BAK") == S.BELUM_MULAI
    assert status("DEMO-TS") == S.PENGISIAN_SER
    assert status("DEMO-TE") == S.PENILAIAN_AUDITOR
    assert status("DEMO-MT") == S.PERLU_AUDIT_LAPANGAN
    assert status("DEMO-IH") == S.MENUNGGU_PERSETUJUAN
    assert status("DEMO-FT") == S.DITUTUP
    lama = Audit.objects.get(unit__kode="DEMO-TE", periode__tahun_akademik="2024/2025")
    assert lama.ptk.count() == 2 and all(p.realisasi and p.status == PTK.Status.DIRENCANAKAN for p in lama.ptk.all())
    assert periksa() == []  # audit log utuh


def test_dijalankan_ulang_tidak_dobel(demo):
    jumlah = Audit.objects.count()
    call_command("isi_data_demo")
    assert Audit.objects.count() == jumlah


def test_ditolak_di_produksi(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("isi_data_demo")


HALAMAN_PER_PERAN = [
    ("master@demo.local", ["beranda", "audits:dashboard", "audits:daftar", "analitik:beranda", "notifications:daftar"]),
    ("admin@demo.local", ["audits:dashboard", "admin:accounts_logaudit_changelist"]),
    ("rektor@demo.local", ["analitik:beranda"]),
    ("kaprodi.ts@demo.local", ["beranda", "audits:riwayat"]),
    ("kaprodi.te@demo.local", ["beranda", "audits:riwayat"]),
    ("dosen4@demo.local", ["beranda"]),
]


def test_semua_peran_masuk_dan_semua_halaman_audit_terbuka(client, demo):
    # Satu tes agar data demo cukup diisi sekali (pengisian ±12 detik).
    for email, halaman in HALAMAN_PER_PERAN:
        client.logout()
        r = client.post(reverse("account_login"), {"login": email, "password": "demo-siami-2026"})
        assert r.status_code == 302, email
        for nama in halaman:
            assert client.get(reverse(nama)).status_code == 200, (email, nama)
    client.force_login(User.objects.get(email="master@demo.local"))
    for a in Audit.objects.all():
        for nama in ("audits:detail", "audits:ser", "documents:daftar", "findings:verifikasi"):
            assert client.get(reverse(nama, args=[a.pk])).status_code == 200, (a.unit, nama)
