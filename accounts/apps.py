from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Akun & Peran"

    def ready(self):
        from .izin import sinkronkan_izin_grup

        post_migrate.connect(sinkronkan_izin_grup, sender=self, dispatch_uid="accounts_sinkronkan_izin_grup")
        from . import penerima_jejak  # noqa: F401  (audit log NFR-10)
