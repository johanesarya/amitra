from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission

from .peran import IZIN_GRUP


def sinkronkan_izin_grup(using="default", **kwargs):
    """Buat grup peran dan samakan izinnya dengan `IZIN_GRUP` (dijalankan tiap migrate)."""
    # Izin app lain dibuat di post_migrate masing-masing; pastikan semuanya sudah ada.
    for app_config in global_apps.get_app_configs():
        create_permissions(app_config, verbosity=0, using=using)

    for nama_grup, daftar in IZIN_GRUP.items():
        izin = []
        for kode in daftar:
            app_label, codename = kode.split(".")
            try:
                izin.append(
                    Permission.objects.using(using).get(content_type__app_label=app_label, codename=codename)
                )
            except Permission.DoesNotExist as e:
                raise LookupError(f"Izin {kode} untuk grup {nama_grup} tidak ditemukan.") from e
        grup, _ = Group.objects.using(using).get_or_create(name=nama_grup)
        grup.permissions.set(izin)
