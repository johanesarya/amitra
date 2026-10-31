from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from masterdata.models import (
    LingkupBidang,
    PengaturanInstitusi,
    PengaturanPeriode,
    Periode,
    PernyataanStandar,
    Standar,
    TahapanPeriode,
    TipeUnit,
    Unit,
)
from scoring.parameter import Kategori

pytestmark = pytest.mark.django_db


def test_delapan_tipe_unit_terisi_migrasi():
    # FR-06
    assert list(TipeUnit.objects.values_list("kode", flat=True)) == [
        "FAKULTAS", "PRODI_S1", "PRODI_S2", "PRODI_S3", "PRODI_PROFESI", "LEMBAGA", "BIRO", "UPT",
    ]


# --- Unit (FR-06) -----------------------------------------------------------------

def test_prodi_wajib_punya_fakultas_induk():
    with pytest.raises(ValidationError) as e:
        Unit(nama="Prodi X", kode="X", tipe_id=TipeUnit.PRODI_S1).full_clean()
    assert "induk" in e.value.message_dict


def test_induk_prodi_harus_fakultas():
    biro = Unit.objects.create(nama="Biro Akademik", kode="BAK", tipe_id=TipeUnit.BIRO)
    with pytest.raises(ValidationError):
        Unit(nama="Prodi X", kode="X", tipe_id=TipeUnit.PRODI_S2, induk=biro).full_clean()


def test_unit_non_prodi_tidak_boleh_punya_induk(fakultas):
    with pytest.raises(ValidationError):
        Unit(nama="UPT TI", kode="UPTTI", tipe_id=TipeUnit.UPT, induk=fakultas).full_clean()


def test_prodi_dengan_fakultas_valid(fakultas):
    Unit(nama="Teknik Sipil", kode="TS", tipe_id=TipeUnit.PRODI_S1, induk=fakultas).full_clean()


# --- Periode dan tahapan (FR-05) ---------------------------------------------------

def test_hanya_satu_periode_aktif_di_database():
    Periode.objects.create(nama="A", tahun_akademik="2024/2025", aktif=True)
    with pytest.raises(IntegrityError):
        Periode.objects.create(nama="B", tahun_akademik="2025/2026", aktif=True)


def test_periode_aktif_kedua_ditolak_validasi_form():
    Periode.objects.create(nama="A", tahun_akademik="2024/2025", aktif=True)
    with pytest.raises(ValidationError):
        Periode(nama="B", tahun_akademik="2025/2026", aktif=True).full_clean()


def test_aktifkan_menonaktifkan_periode_lain():
    lama = Periode.objects.create(nama="A", tahun_akademik="2024/2025", aktif=True)
    baru = Periode.objects.create(nama="B", tahun_akademik="2025/2026")
    baru.aktifkan()
    lama.refresh_from_db()
    assert baru.aktif and not lama.aktif
    assert Periode.objects.filter(aktif=True).count() == 1


def test_tanggal_selesai_tahapan_tidak_boleh_sebelum_mulai(periode):
    tahap = TahapanPeriode(
        periode=periode,
        jenis=TahapanPeriode.Jenis.PENGISIAN_SER,
        tanggal_mulai=date(2026, 2, 10),
        tanggal_selesai=date(2026, 2, 1),
    )
    with pytest.raises(ValidationError):
        tahap.full_clean()


def test_satu_jenis_tahap_sekali_per_periode(periode):
    TahapanPeriode.objects.create(
        periode=periode, jenis="PENGISIAN_SER", tanggal_mulai=date(2026, 1, 24), tanggal_selesai=date(2026, 2, 8)
    )
    with pytest.raises(ValidationError):
        TahapanPeriode(
            periode=periode, jenis="PENGISIAN_SER", tanggal_mulai=date(2026, 3, 1), tanggal_selesai=date(2026, 3, 2)
        ).full_clean()


# --- Pengaturan periode (FR-12, BR-12a) -------------------------------------------

def test_pengaturan_awal_sesuai_keputusan_klien(periode):
    p = periode.parameter()
    assert p.skor_kategori == {Kategori.KTS: 1, Kategori.OB: 2, Kategori.SESUAI: 3, Kategori.PELAMPAUAN: 4}
    assert p.kkm == 75 and p.ambang_deviasi == 10 and p.minimal_auditor == 3
    assert (p.penyesuaian_kts, p.penyesuaian_ob, p.penyesuaian_kelebihan) == (
        Decimal("-0.5"), Decimal("-0.3"), Decimal("0.25"),
    )
    assert (p.bobot_a, p.bobot_b, p.bobot_c) == (60, 30, 10)
    assert p.proporsi_ne is None and p.proporsi_nk is None  # BRD 10.6 masih terbuka


def test_pengaturan_menolak_bobot_tidak_100(periode):
    pengaturan = periode.pengaturan
    pengaturan.bobot_a = Decimal("50")
    with pytest.raises(ValidationError, match="100%"):
        pengaturan.full_clean()


def test_pengaturan_menolak_proporsi_setengah_terisi(periode):
    pengaturan = periode.pengaturan
    pengaturan.proporsi_ne = Decimal("70")
    with pytest.raises(ValidationError):
        pengaturan.full_clean()


def test_periode_baru_menyalin_pengaturan_periode_terakhir(periode):
    periode.pengaturan.kkm = Decimal("80")
    periode.pengaturan.save()
    baru = Periode.objects.create(nama="AMI 2026/2027", tahun_akademik="2026/2027")
    assert PengaturanPeriode.pastikan_ada(baru).kkm == Decimal("80")


def test_pastikan_ada_tidak_menimpa_pengaturan_yang_ada(periode):
    periode.pengaturan.kkm = Decimal("70")
    periode.pengaturan.save()
    assert PengaturanPeriode.pastikan_ada(periode).kkm == Decimal("70")


def test_pengaturan_institusi_hanya_satu_baris():
    PengaturanInstitusi(nama_institusi="A").save()
    PengaturanInstitusi(nama_institusi="B").save()
    assert PengaturanInstitusi.objects.count() == 1
    assert PengaturanInstitusi.muat().nama_institusi == "B"


# --- Standar (FR-07, FR-10) --------------------------------------------------------

def test_standar_turunan_wajib_unit_pengusul(periode, lingkup):
    with pytest.raises(ValidationError):
        Standar(periode=periode, kode="T1", nama="X", lingkup=lingkup, sumber=Standar.Sumber.TURUNAN).full_clean()


def test_kode_standar_unik_per_periode(periode, lingkup):
    Standar.objects.create(periode=periode, kode="1", nama="A", lingkup=lingkup)
    with pytest.raises(ValidationError):
        Standar(periode=periode, kode="1", nama="B", lingkup=lingkup).full_clean()


# --- Pernyataan berlaku untuk unit (FR-08, FR-18) -----------------------------------

def _pernyataan(standar, kode, tipe, aktif=True):
    p = PernyataanStandar.objects.create(standar=standar, kode=kode, pernyataan=f"Butir {kode}", aktif=aktif)
    p.tipe_unit.set(tipe)
    return p


def test_berlaku_untuk_menyaring_tipe_lingkup_status_dan_periode(periode, lingkup, fakultas, prodi):
    penelitian = LingkupBidang.objects.create(nama="Penelitian")
    lain = Periode.objects.create(nama="Lama", tahun_akademik="2024/2025")

    s1 = Standar.objects.create(periode=periode, kode="1", nama="Pendidikan", lingkup=lingkup, urutan=1)
    s2 = Standar.objects.create(periode=periode, kode="2", nama="Penelitian", lingkup=penelitian, urutan=2)
    s_lama = Standar.objects.create(periode=lain, kode="1", nama="Lama", lingkup=lingkup)
    s_ajuan = Standar.objects.create(
        periode=periode, kode="T1", nama="Ajuan", lingkup=lingkup, urutan=3,
        sumber=Standar.Sumber.TURUNAN, unit_pengusul=prodi, status=Standar.Status.DIAJUKAN,
    )

    _pernyataan(s1, "1.2", [TipeUnit.PRODI_S1])
    _pernyataan(s1, "1.1", [TipeUnit.PRODI_S1, TipeUnit.FAKULTAS])
    _pernyataan(s1, "1.3", [TipeUnit.FAKULTAS])  # tipe lain
    _pernyataan(s1, "1.4", [TipeUnit.PRODI_S1], aktif=False)  # nonaktif
    _pernyataan(s2, "2.1", [TipeUnit.PRODI_S1])  # lingkup lain
    _pernyataan(s_lama, "1.1", [TipeUnit.PRODI_S1])  # periode lain
    _pernyataan(s_ajuan, "T1.1", [TipeUnit.PRODI_S1])  # belum disetujui

    hasil = PernyataanStandar.objects.berlaku_untuk(prodi, periode, lingkup=[lingkup])
    assert [p.kode for p in hasil] == ["1.1", "1.2"]

    semua_lingkup = PernyataanStandar.objects.berlaku_untuk(prodi, periode)
    assert [p.kode for p in semua_lingkup] == ["1.1", "1.2", "2.1"]


def test_standar_turunan_berlaku_untuk_pengusul_dan_prodi_di_bawahnya(periode, lingkup, fakultas, prodi):
    prodi_lain_fak = Unit.objects.create(
        nama="Fakultas Hukum", kode="FH", tipe_id=TipeUnit.FAKULTAS
    )
    prodi_hukum = Unit.objects.create(nama="Ilmu Hukum", kode="IH", tipe_id=TipeUnit.PRODI_S1, induk=prodi_lain_fak)

    s_fak = Standar.objects.create(
        periode=periode, kode="TF", nama="Turunan FT", lingkup=lingkup,
        sumber=Standar.Sumber.TURUNAN, unit_pengusul=fakultas,
    )
    _pernyataan(s_fak, "TF.1", [TipeUnit.PRODI_S1])

    assert [p.kode for p in PernyataanStandar.objects.berlaku_untuk(prodi, periode)] == ["TF.1"]
    assert list(PernyataanStandar.objects.berlaku_untuk(prodi_hukum, periode)) == []
