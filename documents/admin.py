from django.contrib import admin

from audits.admin import HanyaBacaMixin

from .models import Dokumen, Ekspor, NomorSurat, PengaturanDokumen, PolaNomorSurat


@admin.register(PolaNomorSurat)
class PolaNomorSuratAdmin(admin.ModelAdmin):
    list_display = ["jenis", "kategori", "pola"]
    list_filter = ["jenis", "kategori"]


@admin.register(PengaturanDokumen)
class PengaturanDokumenAdmin(admin.ModelAdmin):
    list_display = ["jenis", "judul", "nomor_formulir"]


@admin.register(NomorSurat)
class NomorSuratAdmin(HanyaBacaMixin, admin.ModelAdmin):
    """Koreksi lewat halaman Dokumen audit agar alasan tercatat dan aturan kunci Final berlaku."""

    list_display = ["teks", "jenis", "audit", "status", "dibuat_pada"]
    list_filter = ["jenis", "status", "tahun"]
    search_fields = ["teks", "audit__unit__nama"]


@admin.register(Dokumen)
class DokumenAdmin(HanyaBacaMixin, admin.ModelAdmin):
    list_display = ["audit", "jenis", "ptk", "status", "versi", "selesai_pada"]
    list_filter = ["jenis", "status"]


@admin.register(Ekspor)
class EksporAdmin(HanyaBacaMixin, admin.ModelAdmin):
    list_display = ["judul", "jenis", "diminta_oleh", "status", "diminta_pada", "selesai_pada"]
    list_filter = ["jenis", "status"]
