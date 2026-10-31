from pathlib import Path

from django.core.management.base import BaseCommand

from masterdata.impor import buat_template

TUJUAN = Path(__file__).resolve().parents[2] / "static" / "masterdata" / "template_impor_standar.xlsx"


class Command(BaseCommand):
    help = "Buat ulang berkas template impor standar (FR-09) di folder static."

    def handle(self, *args, **options):
        buat_template().save(TUJUAN)
        self.stdout.write(self.style.SUCCESS(f"Template ditulis ke {TUJUAN}"))
