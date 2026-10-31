from django.core.management.base import BaseCommand, CommandError

from accounts.jejak import periksa, segel


class Command(BaseCommand):
    help = "NFR-10: segel log baru lalu periksa apakah ada log audit yang diubah atau dihapus."

    def handle(self, *args, **options):
        disegel = segel()
        masalah = periksa()
        if masalah:
            for m in masalah:
                self.stderr.write(self.style.ERROR(m))
            raise CommandError(f"{len(masalah)} masalah ditemukan pada log audit.")
        self.stdout.write(self.style.SUCCESS(f"Log audit utuh. {disegel} log baru disegel."))
