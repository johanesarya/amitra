"""Peran global dan pemetaannya ke izin Django (BRD Bab 4).

Peran Auditee/Auditor/Ketua TIDAK ada di sini: peran itu melekat pada
penugasan per audit (FR-04) di app `audits`.
"""

from django.db import models


class Peran(models.TextChoices):
    MENUNGGU = "MENUNGGU", "Menunggu Peran"
    PENGGUNA = "PENGGUNA", "Pengguna (dosen/tendik)"
    VIEWER = "VIEWER", "Viewer (Rektorat)"
    ADMIN = "ADMIN", "Admin LPM"
    MASTER_ADMIN = "MASTER_ADMIN", "Master Admin LPM"
    NONAKTIF = "NONAKTIF", "Nonaktif"


PERAN_STAF = frozenset({Peran.ADMIN, Peran.MASTER_ADMIN})

GRUP_PERAN = {
    Peran.MASTER_ADMIN: "Master Admin",
    Peran.ADMIN: "Admin",
    Peran.VIEWER: "Viewer",
}


def _crud(app, *model, tanpa=()):
    return [f"{app}.{aksi}_{m}" for m in model for aksi in ("view", "add", "change", "delete") if aksi not in tanpa]


_MODEL_PERIODE_UNIT = ["periode", "tahapanperiode", "pengaturanperiode", "pengaturaninstitusi", "unit", "kategorisurat"]
_MODEL_STANDAR = ["standar", "pernyataanstandar", "lingkupbidang", "tujuanaudit"]
# Plot penugasan: Master Admin dan Admin sama-sama "Ya" (Bab 4).
_IZIN_PLOT = [*_crud("audits", "audit"), "audits.view_penugasan"]
_IZIN_DOKUMEN = [
    "documents.view_dokumen", "documents.change_dokumen",
    "documents.view_nomorsurat", "documents.change_nomorsurat",
]

# Bab 4: Master Admin mengelola periode, unit, pengguna, peran, dan standar.
# Admin hanya melihat periode, unit, dan pengguna, tetapi mengelola standar dan impor.
# Pengguna tidak dihapus (jejak audit); gunakan peran Nonaktif.
IZIN_GRUP = {
    "Master Admin": [
        *_crud("masterdata", *_MODEL_PERIODE_UNIT, *_MODEL_STANDAR),
        "masterdata.view_tipeunit",
        *_crud("accounts", "user", tanpa=("delete",)),
        "accounts.tetapkan_peran",
        "accounts.view_logaudit",
        "accounts.ekspor_log",
        *_IZIN_PLOT,
        "audits.buka_kunci_audit",  # Bab 4: buka kunci/reset hanya Master Admin
        *_crud("documents", "polanomorsurat", "pengaturandokumen"),
        *_IZIN_DOKUMEN,
        "audits.lihat_analitik",
    ],
    "Admin": [
        *[f"masterdata.view_{m}" for m in _MODEL_PERIODE_UNIT],
        *_crud("masterdata", *_MODEL_STANDAR),
        "masterdata.view_tipeunit",
        "accounts.view_user",
        "accounts.view_logaudit",
        *_IZIN_PLOT,
        "documents.view_polanomorsurat", "documents.view_pengaturandokumen",
        *_IZIN_DOKUMEN,
        "audits.lihat_analitik",
    ],
    # Viewer (Rektorat): rapor, grafik, dan tren lintas unit, hanya-baca (Bab 4).
    "Viewer": ["audits.lihat_analitik"],
}
