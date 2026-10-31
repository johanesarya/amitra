"""Rumus penilaian AMI (BRD Bab 6).

Semua hasil berupa `Fraction` agar pembandingan dengan ambang (D > 10, NE ≥ 75)
eksak. Pembulatan hanya dilakukan saat menyimpan atau menampilkan, lewat
`bulatkan()`.
"""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction

from .parameter import Kategori, ParameterPenilaian


@dataclass(frozen=True)
class JumlahTemuan:
    kts: int
    ob: int
    kelebihan: int


def _pecahan(nilai):
    if isinstance(nilai, (bool, float)):
        raise TypeError(f"Nilai harus int, Decimal, atau Fraction, bukan {type(nilai).__name__}.")
    return Fraction(nilai)


def _persen(nilai):
    return _pecahan(nilai) / 100


def validasi_jumlah_auditor(jumlah: int, params: ParameterPenilaian) -> None:
    """FR-13: jumlah auditor ganjil dan minimal sesuai Pengaturan."""
    if jumlah < params.minimal_auditor:
        raise ValueError(f"Jumlah auditor minimal {params.minimal_auditor}, saat ini {jumlah}.")
    if jumlah % 2 == 0:
        raise ValueError(f"Jumlah auditor harus ganjil, saat ini {jumlah}.")


def nilai_auditor(skor: Sequence[int | None], params: ParameterPenilaian) -> Fraction:
    """6.2: N_i = Σ skor / (skor_maks × n) × 100.

    `None` menandai butir "Tidak berlaku" dan dikeluarkan dari pembagi (BR-03).
    """
    berlaku = [s for s in skor if s is not None]
    if not berlaku:
        raise ValueError("Tidak ada butir berlaku untuk dihitung.")
    for s in berlaku:
        if isinstance(s, bool) or not isinstance(s, int) or s not in params.skor_berlaku:
            raise ValueError(f"Skor {s!r} di luar skala penilaian.")
    return Fraction(sum(berlaku) * 100, params.skor_maks * len(berlaku))


def deviasi(nilai: Sequence, params: ParameterPenilaian) -> Fraction:
    """6.3: D = nilai auditor tertinggi − terendah (BR-06)."""
    validasi_jumlah_auditor(len(nilai), params)
    pecahan = [_pecahan(n) for n in nilai]
    return max(pecahan) - min(pecahan)


def butir_penyumbang_deviasi(skor_per_butir: Mapping) -> list:
    """BR-09: butir yang skornya berbeda antar-auditor, urutan dipertahankan."""
    return [
        butir
        for butir, skor in skor_per_butir.items()
        if len({s for s in skor if s is not None}) > 1
    ]


def kategori_mayoritas(kategori: Sequence[Kategori]) -> Kategori | None:
    """BR-13: kategori terbanyak; `None` bila tidak ada satu kategori terbanyak
    sehingga ketua wajib menetapkan dengan alasan."""
    if not kategori:
        raise ValueError("Daftar kategori kosong.")
    teratas = Counter(Kategori(k) for k in kategori).most_common(2)
    if len(teratas) > 1 and teratas[0][1] == teratas[1][1]:
        return None
    return teratas[0][0]


def hitung_jumlah_temuan(kategori_final: Iterable[Kategori | None]) -> JumlahTemuan:
    """BR-14: hitung temuan per jenis dari kategori final.

    `None` dianggap butir tidak berlaku; kategori seri harus sudah ditetapkan
    ketua sebelum fungsi ini dipanggil.
    """
    jumlah = Counter(Kategori(k) for k in kategori_final if k is not None)
    return JumlahTemuan(
        kts=jumlah[Kategori.KTS],
        ob=jumlah[Kategori.OB],
        kelebihan=jumlah[Kategori.PELAMPAUAN],
    )


def rata_rata(nilai: Sequence) -> Fraction:
    if not nilai:
        raise ValueError("Daftar nilai kosong.")
    return sum((_pecahan(n) for n in nilai), Fraction(0)) / len(nilai)


def nilai_efektif(nilai: Sequence, temuan: JumlahTemuan, params: ParameterPenilaian) -> Fraction:
    """6.4: NE = rata-rata N_i + K_KTS×p_KTS + K_OB×p_OB + K_Kel×p_Kel.

    Penyesuaian bertanda (default −0,5; −0,3; +0,25) dan diambil dari Pengaturan.
    """
    return (
        rata_rata(nilai)
        + temuan.kts * _pecahan(params.penyesuaian_kts)
        + temuan.ob * _pecahan(params.penyesuaian_ob)
        + temuan.kelebihan * _pecahan(params.penyesuaian_kelebihan)
    )


def memenuhi_kkm(ne, params: ParameterPenilaian) -> bool:
    """BR-10: NE ≥ KKM → "Memenuhi KKM"."""
    return _pecahan(ne) >= _pecahan(params.kkm)


def perlu_audit_lapangan(d, ne, params: ParameterPenilaian) -> bool:
    """BR-07, BR-08, BR-11: Audit Lapangan hanya bila D > ambang DAN NE ≥ KKM."""
    return _pecahan(d) > _pecahan(params.ambang_deviasi) and memenuhi_kkm(ne, params)


def konversi_skala_100(skor: int, params: ParameterPenilaian) -> Fraction:
    """Kesimpulan A/B/C skala penilaian → skala 100 (BR-12; skala masih usulan, BRD 10.6)."""
    if isinstance(skor, bool) or not isinstance(skor, int) or skor not in params.skor_berlaku:
        raise ValueError(f"Skor {skor!r} di luar skala penilaian.")
    return Fraction(skor * 100, params.skor_maks)


def nilai_kesimpulan(a, b, c, params: ParameterPenilaian) -> Fraction:
    """BR-12a: NK = bobot_A×A + bobot_B×B + bobot_C×C (A, B, C dalam skala 100).

    `c=None` berarti Kesimpulan C tidak berlaku (unit belum punya PTK periode lalu):
    bobot C dibagi ke A dan B sebanding bobotnya (keputusan sementara, menunggu LPM).
    """
    if a is None or b is None:
        raise ValueError("Kesimpulan A dan B wajib dinilai.")
    bobot_a, bobot_b = _pecahan(params.bobot_a), _pecahan(params.bobot_b)
    if c is None:
        return (bobot_a * _pecahan(a) + bobot_b * _pecahan(b)) / (bobot_a + bobot_b)
    return (bobot_a * _pecahan(a) + bobot_b * _pecahan(b) + _pecahan(params.bobot_c) * _pecahan(c)) / 100


def hasil_akhir(ne, nk, params: ParameterPenilaian) -> Fraction:
    """BR-12b: gabungan NE dan NK sesuai proporsi di Pengaturan."""
    if params.proporsi_ne is None:
        raise ValueError("Proporsi NE dan NK dalam hasil akhir belum ditetapkan di Pengaturan.")
    return _persen(params.proporsi_ne) * _pecahan(ne) + _persen(params.proporsi_nk) * _pecahan(nk)


def bulatkan(nilai, tempat: int = 2) -> Decimal:
    """Bulatkan ke `tempat` desimal dengan setengah ke atas (seperti ROUND di Excel)."""
    pecahan = _pecahan(nilai)
    with localcontext() as ctx:
        ctx.prec = 50
        hasil = Decimal(pecahan.numerator) / Decimal(pecahan.denominator)
        return hasil.quantize(Decimal(1).scaleb(-tempat), rounding=ROUND_HALF_UP)
