"""Kategori penilaian dan parameter rumus per periode (BRD 6.1, FR-12).

Nilai default tidak ditulis di sini; nilai itu disimpan di Pengaturan periode
(app `masterdata`) lalu dikirim ke `ParameterPenilaian`.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Kategori(StrEnum):
    KTS = "KTS"
    OB = "OB"
    SESUAI = "SESUAI"
    PELAMPAUAN = "PELAMPAUAN"

    @property
    def label(self):
        return {
            Kategori.KTS: "KTS (Ketidaksesuaian)",
            Kategori.OB: "OB (Observasi)",
            Kategori.SESUAI: "Sesuai",
            Kategori.PELAMPAUAN: "Pelampauan",
        }[self]


@dataclass(frozen=True)
class ParameterPenilaian:
    """Semua angka Bab 6. Persentase (bobot, proporsi) ditulis 0–100."""

    skor_kategori: dict[Kategori, int]
    kkm: Decimal
    ambang_deviasi: Decimal
    minimal_auditor: int
    penyesuaian_kts: Decimal
    penyesuaian_ob: Decimal
    penyesuaian_kelebihan: Decimal
    bobot_a: Decimal
    bobot_b: Decimal
    bobot_c: Decimal
    # BRD 10.6: proporsi NE/NK dalam hasil akhir belum diputuskan LPM.
    proporsi_ne: Decimal | None = None
    proporsi_nk: Decimal | None = None

    def __post_init__(self):
        if set(self.skor_kategori) != set(Kategori):
            raise ValueError("Skala penilaian harus memuat KTS, OB, Sesuai, dan Pelampauan.")
        urutan = [self.skor_kategori[k] for k in Kategori]
        if urutan[0] < 1 or any(a >= b for a, b in zip(urutan, urutan[1:])):
            raise ValueError("Skor kategori harus bilangan positif yang naik dari KTS ke Pelampauan.")
        if not 0 <= self.kkm <= 100:
            raise ValueError("KKM harus di antara 0 dan 100.")
        if self.ambang_deviasi < 0:
            raise ValueError("Ambang deviasi tidak boleh negatif.")
        if self.minimal_auditor < 1:
            raise ValueError("Minimal auditor harus paling sedikit 1.")
        if self.bobot_a + self.bobot_b + self.bobot_c != 100:
            raise ValueError("Total bobot Kesimpulan A, B, dan C wajib 100% (BR-12a).")
        if (self.proporsi_ne is None) != (self.proporsi_nk is None):
            raise ValueError("Proporsi NE dan NK harus diisi keduanya atau dikosongkan keduanya.")
        if self.proporsi_ne is not None and self.proporsi_ne + self.proporsi_nk != 100:
            raise ValueError("Total proporsi NE dan NK dalam hasil akhir wajib 100%.")

    def skor(self, kategori):
        return self.skor_kategori[Kategori(kategori)]

    @property
    def skor_maks(self):
        return max(self.skor_kategori.values())

    @property
    def skor_berlaku(self):
        return frozenset(self.skor_kategori.values())
