from unittest import mock

import pytest

from findings.tests.conftest import *  # noqa: F401,F403 — fixture audit (Perumusan Temuan), ketua, dst.

PDF_UJI = b"%PDF-1.4 dokumen uji"


@pytest.fixture(autouse=True)
def media_sementara(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def pdf_palsu():
    """WeasyPrint di-mock: tes tidak bergantung pada pustaka Pango/GTK."""
    with mock.patch("documents.tugas.render_pdf", return_value=PDF_UJI) as m:
        yield m
