from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_q.models import Schedule


class Command(BaseCommand):
    help = "Pasang atau perbarui jadwal Django-Q2. Aman dijalankan berulang, mis. saat deploy."

    def handle(self, *args, **options):
        sekarang = timezone.localtime()
        # FR-46: pengingat H-3 sampai H setiap pagi pukul 07.00 waktu lokal.
        pagi = timezone.make_aware(datetime.combine(sekarang.date(), time(7, 0)))
        if pagi <= sekarang:
            pagi += timedelta(days=1)
        jadwal = [
            ("pengingat-harian", "notifications.tugas.kirim_pengingat_harian", {"schedule_type": Schedule.DAILY, "next_run": pagi}),
            # NFR-10: sambungkan log audit baru ke rantai hash tiap 10 menit.
            ("segel-log", "accounts.jejak.segel", {"schedule_type": Schedule.MINUTES, "minutes": 10, "next_run": sekarang}),
        ]
        for nama, fungsi, opsi in jadwal:
            s, baru = Schedule.objects.update_or_create(name=nama, defaults={"func": fungsi, "repeats": -1, **opsi})
            status = "dipasang" if baru else "diperbarui"
            self.stdout.write(self.style.SUCCESS(f"Jadwal {nama} {status}; berikutnya {timezone.localtime(s.next_run):%d-%m-%Y %H.%M}."))
