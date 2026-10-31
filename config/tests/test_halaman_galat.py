"""Halaman galat berbahasa Indonesia (NFR-19)."""

import pytest
from django.template.loader import render_to_string
from django.urls import reverse

from audits.tests.conftest import buat_pengguna

pytestmark = pytest.mark.django_db


def test_403_berbahasa_indonesia_dengan_alasan(client, settings):
    settings.DEBUG = False
    client.force_login(buat_pengguna("Orang"))
    resp = client.get(reverse("audits:dashboard"))
    assert resp.status_code == 403
    assert "Akses ditolak" in resp.content.decode() and "Tugas Saya" in resp.content.decode()


def test_404_berbahasa_indonesia(client, settings):
    settings.DEBUG = False
    resp = client.get("/tidak-ada/")
    assert resp.status_code == 404 and "Halaman tidak ditemukan" in resp.content.decode()


def test_500_tanpa_konteks_tetap_bisa_dirender():
    assert "Terjadi gangguan" in render_to_string("500.html")
