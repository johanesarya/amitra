"""Tes rumus BRD Bab 6. Ditulis sebelum implementasi (aturan proyek)."""

from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

import pytest

from scoring.parameter import Kategori
from scoring.rumus import (
    JumlahTemuan,
    bulatkan,
    butir_penyumbang_deviasi,
    deviasi,
    hasil_akhir,
    hitung_jumlah_temuan,
    kategori_mayoritas,
    konversi_skala_100,
    memenuhi_kkm,
    nilai_auditor,
    nilai_efektif,
    nilai_kesimpulan,
    perlu_audit_lapangan,
    rata_rata,
    validasi_jumlah_auditor,
)

K = Kategori


# --- 6.1 Skala ------------------------------------------------------------------

def test_skala_1_sampai_4(params):
    assert params.skor(K.KTS) == 1
    assert params.skor(K.OB) == 2
    assert params.skor(K.SESUAI) == 3
    assert params.skor(K.PELAMPAUAN) == 4
    assert params.skor_maks == 4


def test_parameter_menolak_skala_tidak_lengkap(params):
    with pytest.raises(ValueError):
        replace(params, skor_kategori={K.KTS: 1, K.OB: 2, K.SESUAI: 3})


# --- 6.2 Nilai per auditor (BR-03, BR-05) -----------------------------------------

def test_semua_sesuai_tepat_75(params):
    assert nilai_auditor([3, 3, 3, 3, 3], params) == 75


def test_semua_pelampauan_100_dan_semua_kts_25(params):
    # BR-05: nilai maksimal 100; nilai minimal 25
    assert nilai_auditor([4] * 7, params) == 100
    assert nilai_auditor([1] * 7, params) == 25


def test_nilai_auditor_rumus(params):
    # (3+3+4+2) / (4×4) × 100 = 75; (3+4+4+3) / 16 × 100 = 87,5
    assert nilai_auditor([3, 3, 4, 2], params) == 75
    assert nilai_auditor([3, 4, 4, 3], params) == Fraction(175, 2)


def test_nilai_auditor_eksak_tanpa_galat_float(params):
    # 10 / (4×3) × 100 = 250/3
    assert nilai_auditor([3, 3, 4], params) == Fraction(250, 3)


def test_butir_tidak_berlaku_dikeluarkan_dari_pembagi(params):
    # BR-03: None = butir ditandai "Tidak berlaku" oleh ketua
    assert nilai_auditor([3, None, 3, None], params) == 75


@pytest.mark.parametrize("skor", [[], [None, None]])
def test_nilai_auditor_tanpa_butir_berlaku_ditolak(params, skor):
    with pytest.raises(ValueError):
        nilai_auditor(skor, params)


@pytest.mark.parametrize("nilai_salah", [0, 5, -1, 2.5, True])
def test_nilai_auditor_menolak_skor_di_luar_skala(params, nilai_salah):
    with pytest.raises(ValueError):
        nilai_auditor([3, nilai_salah], params)


# --- Jumlah auditor (FR-13) ---------------------------------------------------------

@pytest.mark.parametrize("m", [3, 5, 7, 9])
def test_jumlah_auditor_ganjil_minimal_3_diterima(params, m):
    validasi_jumlah_auditor(m, params)


@pytest.mark.parametrize("m", [0, 1, 2, 4, 6])
def test_jumlah_auditor_genap_atau_kurang_dari_3_ditolak(params, m):
    with pytest.raises(ValueError):
        validasi_jumlah_auditor(m, params)


# --- 6.3 Deviasi (BR-06, BR-09) -----------------------------------------------------

def test_deviasi_contoh_brd(params):
    # BR-06: N = 80, 75, 68 → D = 12
    assert deviasi([80, 75, 68], params) == 12


def test_deviasi_eksak_untuk_nilai_pecahan(params):
    # 260/3 − 230/3 = tepat 10, bukan 10,0000000001
    assert deviasi([Fraction(260, 3), Fraction(245, 3), Fraction(230, 3)], params) == 10


def test_deviasi_memeriksa_jumlah_auditor(params):
    with pytest.raises(ValueError):
        deviasi([80, 75], params)


def test_butir_penyumbang_deviasi():
    # BR-09: butir dengan nilai berbeda antar-auditor
    skor = {
        "1.1": [3, 3, 3],
        "1.2": [3, 4, 3],
        "1.3": [2, 2, 2],
        "1.4": [1, 2, 3],
        "1.5": [None, None, None],  # tidak berlaku
    }
    assert butir_penyumbang_deviasi(skor) == ["1.2", "1.4"]


# --- 6.5 Kategori final dan temuan (BR-13, BR-14) -----------------------------------

@pytest.mark.parametrize(
    "kategori, hasil",
    [
        ([K.SESUAI, K.SESUAI, K.OB], K.SESUAI),
        ([K.KTS, K.KTS, K.KTS], K.KTS),
        ([K.PELAMPAUAN, K.SESUAI, K.PELAMPAUAN, K.OB, K.SESUAI], None),  # seri 2-2
        ([K.KTS, K.OB, K.SESUAI], None),  # semua berbeda
        ([K.OB, K.OB, K.SESUAI, K.KTS, K.PELAMPAUAN], K.OB),
    ],
)
def test_kategori_mayoritas(kategori, hasil):
    # None = tidak ada modus tunggal; ketua wajib menetapkan dengan alasan
    assert kategori_mayoritas(kategori) == hasil


def test_kategori_mayoritas_daftar_kosong_ditolak():
    with pytest.raises(ValueError):
        kategori_mayoritas([])


def test_hitung_jumlah_temuan():
    final = [K.SESUAI, K.PELAMPAUAN, K.OB, K.KTS, K.OB, K.SESUAI, None]
    assert hitung_jumlah_temuan(final) == JumlahTemuan(kts=1, ob=2, kelebihan=1)


# --- 6.4 Nilai efektif dan KKM (BR-10) -----------------------------------------------

def test_rata_rata():
    assert rata_rata([75, Fraction(175, 2), Fraction(275, 4)]) == Fraction(925, 12)


def test_nilai_efektif_dengan_penyesuaian(params):
    # rata-rata 80 − 0,5×2 − 0,3×3 + 0,25×4 = 80 − 1 − 0,9 + 1 = 79,1
    ne = nilai_efektif([80, 82, 78], JumlahTemuan(kts=2, ob=3, kelebihan=4), params)
    assert ne == Fraction("79.1")


def test_nilai_efektif_tanpa_temuan_sama_dengan_rata_rata(params):
    assert nilai_efektif([75, 75, 75], JumlahTemuan(0, 0, 0), params) == 75


def test_penyesuaian_diambil_dari_parameter(params):
    p = replace(params, penyesuaian_kts=Decimal("-1"))
    assert nilai_efektif([80, 80, 80], JumlahTemuan(kts=2, ob=0, kelebihan=0), p) == 78


@pytest.mark.parametrize("ne, hasil", [(75, True), (Fraction("74.99"), False), (90, True)])
def test_memenuhi_kkm(params, ne, hasil):
    assert memenuhi_kkm(ne, params) is hasil


# --- Syarat Audit Lapangan (BR-07, BR-08, BR-11) --------------------------------------

@pytest.mark.parametrize(
    "d, ne, hasil",
    [
        (12, 80, True),  # BR-08
        (Fraction("10.01"), 75, True),
        (10, 80, False),  # D tepat 10 tidak > 10
        (12, Fraction("74.9"), False),  # BR-07: D > 10 tetapi NE < 75
        (5, 60, False),
    ],
)
def test_perlu_audit_lapangan(params, d, ne, hasil):
    assert perlu_audit_lapangan(d, ne, params) is hasil


def test_ambang_deviasi_dan_kkm_dari_parameter(params):
    p = replace(params, ambang_deviasi=Decimal("15"), kkm=Decimal("70"))
    assert perlu_audit_lapangan(12, 72, p) is False
    assert perlu_audit_lapangan(16, 72, p) is True


# --- Kesimpulan A/B/C dan hasil akhir (BR-12, BR-12a, BR-12b) ------------------------

@pytest.mark.parametrize("skor, hasil", [(1, 25), (2, 50), (3, 75), (4, 100)])
def test_konversi_skala_100(params, skor, hasil):
    assert konversi_skala_100(skor, params) == hasil


def test_nilai_kesimpulan_bobot_60_30_10(params):
    # 0,6×75 + 0,3×50 + 0,1×100 = 45 + 15 + 10 = 70
    assert nilai_kesimpulan(75, 50, 100, params) == 70


def test_nilai_kesimpulan_c_tidak_berlaku_bobot_dibagi_proporsional(params):
    # Unit tanpa PTK periode lalu: bobot C dibagi ke A dan B sebanding 60:30
    # (keputusan sementara 31 Okt 2026, menunggu konfirmasi LPM).
    # (60×75 + 30×50) / 90 = 6000/90 = 200/3
    assert nilai_kesimpulan(75, 50, None, params) == Fraction(200, 3)


def test_nilai_kesimpulan_c_tidak_berlaku_dengan_a_b_sama(params):
    assert nilai_kesimpulan(80, 80, None, params) == 80


def test_nilai_kesimpulan_a_dan_b_wajib(params):
    with pytest.raises(ValueError):
        nilai_kesimpulan(None, 50, 100, params)


def test_bobot_kesimpulan_wajib_total_100(params):
    with pytest.raises(ValueError):
        replace(params, bobot_a=Decimal("50"))


def test_hasil_akhir_gabungan_ne_dan_nk(params):
    # 0,7×80 + 0,3×70 = 56 + 21 = 77
    assert hasil_akhir(80, 70, params) == 77


def test_hasil_akhir_ditolak_bila_proporsi_belum_ditetapkan(params):
    # BRD 10.6: proporsi NE/NK masih menunggu keputusan LPM
    p = replace(params, proporsi_ne=None, proporsi_nk=None)
    with pytest.raises(ValueError):
        hasil_akhir(80, 70, p)


def test_proporsi_ne_nk_wajib_total_100(params):
    with pytest.raises(ValueError):
        replace(params, proporsi_ne=Decimal("60"))


# --- Pembulatan untuk penyimpanan/tampilan -------------------------------------------

@pytest.mark.parametrize(
    "nilai, hasil",
    [
        (Fraction(925, 12), Decimal("77.08")),
        (Fraction(250, 3), Decimal("83.33")),
        (Fraction("74.995"), Decimal("75.00")),
    ],
)
def test_bulatkan_half_up(nilai, hasil):
    assert bulatkan(nilai) == hasil


# --- Contoh lengkap satu audit ---------------------------------------------------------

def test_contoh_lengkap_satu_audit(params):
    skor = {  # butir → [auditor 1, auditor 2, auditor 3]
        "1.1": [3, 3, 3],
        "1.2": [3, 4, 3],
        "1.3": [4, 4, 3],
        "1.4": [2, 3, 2],
    }
    per_auditor = list(zip(*skor.values()))
    n = [nilai_auditor(s, params) for s in per_auditor]
    assert n == [75, Fraction(175, 2), Fraction(275, 4)]  # 75; 87,5; 68,75

    d = deviasi(n, params)
    assert d == Fraction(75, 4)  # 18,75

    skor_ke_kategori = {v: k for k, v in params.skor_kategori.items()}
    final = [kategori_mayoritas([skor_ke_kategori[s] for s in baris]) for baris in skor.values()]
    assert final == [K.SESUAI, K.SESUAI, K.PELAMPAUAN, K.OB]

    temuan = hitung_jumlah_temuan(final)
    ne = nilai_efektif(n, temuan, params)
    # 925/12 − 0,3 + 0,25 = 77,0333…
    assert bulatkan(ne) == Decimal("77.03")
    assert memenuhi_kkm(ne, params)
    assert perlu_audit_lapangan(d, ne, params)
    assert butir_penyumbang_deviasi(skor) == ["1.2", "1.3", "1.4"]
