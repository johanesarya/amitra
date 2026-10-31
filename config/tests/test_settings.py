"""Smoke test kerangka proyek (NFR-15: konfigurasi lewat variabel lingkungan)."""

import importlib

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model

from config import settings as config_settings


def test_database_dari_database_url(monkeypatch):
    # Muat ulang modul settings; django.conf.settings sudah diganti DB tes oleh pytest-django.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///lain.sqlite3")
    modul = importlib.reload(config_settings)
    db = modul.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.sqlite3"
    assert db["NAME"] == str(modul.BASE_DIR / "lain.sqlite3")


def test_semua_app_siami_terpasang():
    for label in ["accounts", "masterdata", "audits", "findings", "documents", "notifications"]:
        assert apps.is_installed(label), label


def test_model_pengguna_kustom():
    assert get_user_model()._meta.label == "accounts.User"


def test_bahasa_dan_zona_waktu():
    assert settings.LANGUAGE_CODE == "id"
    assert settings.TIME_ZONE == "Asia/Jakarta"


def test_timeout_sesi_60_menit():
    # NFR-07
    assert settings.SESSION_COOKIE_AGE == 3600
    assert settings.SESSION_SAVE_EVERY_REQUEST is True
