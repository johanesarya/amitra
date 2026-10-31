"""Pengaturan untuk pytest: antrean berjalan sinkron agar tugas langsung dieksekusi."""

from .settings import *  # noqa: F401,F403
from .settings import Q_CLUSTER

Q_CLUSTER = {**Q_CLUSTER, "sync": True}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # tes lebih cepat
