from django.contrib import admin

from audits.admin import HanyaBacaMixin

from .models import KirimanEmail, Notifikasi


@admin.register(KirimanEmail)
class KirimanEmailAdmin(HanyaBacaMixin, admin.ModelAdmin):
    list_display = ["subjek", "penerima", "jenis", "status", "percobaan", "dibuat_pada", "terkirim_pada"]
    list_filter = ["status", "jenis"]
    search_fields = ["penerima", "subjek"]


@admin.register(Notifikasi)
class NotifikasiAdmin(HanyaBacaMixin, admin.ModelAdmin):
    list_display = ["judul", "penerima", "jenis", "dibaca_pada", "dibuat_pada"]
    list_filter = ["jenis"]
    search_fields = ["judul", "penerima__email"]
