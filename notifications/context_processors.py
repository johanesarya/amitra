from .tenggat import HARI_PENGINGAT, tenggat_pengguna


def notifikasi(request):
    """Jumlah belum dibaca (lonceng) dan banner tenggat H-3 sampai H (FR-46) di semua halaman."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or user.menunggu_peran or request.headers.get("HX-Request"):
        return {}
    return {
        "jumlah_belum_dibaca": user.notifikasi.filter(dibaca_pada__isnull=True).count(),
        "banner_tenggat": [t for t in tenggat_pengguna(user) if t.sisa in HARI_PENGINGAT],
    }
