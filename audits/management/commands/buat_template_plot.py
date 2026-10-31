from pathlib import Path

from django.core.management.base import BaseCommand

from audits.impor_plot import buat_template

TUJUAN = Path(__file__).resolve().parents[2] / "static" / "audits" / "template_plot_audit.xlsx"


class Command(BaseCommand):
    help = "Buat ulang berkas template plot massal audit (FR-15) di folder static."

    def handle(self, *args, **options):
        buat_template().save(TUJUAN)
        self.stdout.write(self.style.SUCCESS(f"Template ditulis ke {TUJUAN}"))
