from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "documents"
    verbose_name = "Dokumen"

    def ready(self):
        from . import penerima  # noqa: F401
