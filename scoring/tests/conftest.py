from decimal import Decimal

import pytest

from scoring.parameter import Kategori, ParameterPenilaian


@pytest.fixture
def params():
    """Parameter yang dikonfirmasi klien 31 Okt 2026 (BRD 10.6).

    Proporsi NE/NK masih terbuka; nilai 70/30 di sini hanya untuk tes.
    """
    return ParameterPenilaian(
        skor_kategori={
            Kategori.KTS: 1,
            Kategori.OB: 2,
            Kategori.SESUAI: 3,
            Kategori.PELAMPAUAN: 4,
        },
        kkm=Decimal("75"),
        ambang_deviasi=Decimal("10"),
        minimal_auditor=3,
        penyesuaian_kts=Decimal("-0.5"),
        penyesuaian_ob=Decimal("-0.3"),
        penyesuaian_kelebihan=Decimal("0.25"),
        bobot_a=Decimal("60"),
        bobot_b=Decimal("30"),
        bobot_c=Decimal("10"),
        proporsi_ne=Decimal("70"),
        proporsi_nk=Decimal("30"),
    )
