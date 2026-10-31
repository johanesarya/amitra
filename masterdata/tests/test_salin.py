"""Salin standar dari periode lalu (FR-11)."""

import pytest

from masterdata.models import Periode, PernyataanStandar, Standar, TipeUnit
from masterdata.salin import salin_standar

pytestmark = pytest.mark.django_db


@pytest.fixture
def periode_baru(db):
    return Periode.objects.create(nama="AMI 2026/2027", tahun_akademik="2026/2027")


def test_salin_standar_beserta_pernyataan_dan_tipe_unit(periode, periode_baru, lingkup, prodi):
    s = Standar.objects.create(periode=periode, kode="1", nama="A", lingkup=lingkup, urutan=3)
    p = PernyataanStandar.objects.create(standar=s, kode="1.1", pernyataan="Butir", pertanyaan_panduan="?", urutan=2)
    p.tipe_unit.set([TipeUnit.PRODI_S1, TipeUnit.PRODI_S2])
    PernyataanStandar.objects.create(standar=s, kode="1.2", pernyataan="Nonaktif", aktif=False)
    Standar.objects.create(
        periode=periode, kode="T", nama="Turunan disetujui", lingkup=lingkup,
        sumber=Standar.Sumber.TURUNAN, unit_pengusul=prodi,
    )
    Standar.objects.create(
        periode=periode, kode="X", nama="Ditolak", lingkup=lingkup,
        sumber=Standar.Sumber.TURUNAN, unit_pengusul=prodi, status=Standar.Status.DITOLAK,
    )

    assert salin_standar(periode, periode_baru) == (2, 2)

    baru = Standar.objects.get(periode=periode_baru, kode="1")
    assert baru.pk != s.pk and baru.urutan == 3
    p_baru = baru.pernyataan.get(kode="1.1")
    assert p_baru.pertanyaan_panduan == "?" and p_baru.urutan == 2
    assert p_baru.asal == p  # butir yang sama antarperiode (FR-21, BR-17)
    assert set(p_baru.tipe_unit.values_list("kode", flat=True)) == {TipeUnit.PRODI_S1, TipeUnit.PRODI_S2}
    assert baru.pernyataan.get(kode="1.2").aktif is False
    assert set(Standar.objects.filter(periode=periode_baru).values_list("kode", flat=True)) == {"1", "T"}
    # Data asal tidak berubah
    assert Standar.objects.filter(periode=periode).count() == 3


def test_salin_ditolak_bila_tujuan_sudah_punya_standar(periode, periode_baru, lingkup):
    Standar.objects.create(periode=periode, kode="1", nama="A", lingkup=lingkup)
    Standar.objects.create(periode=periode_baru, kode="9", nama="B", lingkup=lingkup)
    with pytest.raises(ValueError, match="sudah memiliki standar"):
        salin_standar(periode, periode_baru)


def test_salin_ke_periode_sendiri_ditolak(periode):
    with pytest.raises(ValueError):
        salin_standar(periode, periode)
