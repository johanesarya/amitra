from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from audits.admin import HanyaBacaMixin

from .models import Dokumen, Ekspor, NomorSurat, PengaturanDokumen, PolaNomorSurat


def _tautan_unduh(berkas, url):
    """NFR-08: /media/ tidak dilayani; unduhan selalu lewat view yang memeriksa hak akses."""
    return format_html('<a href="{}">Unduh</a>', url) if berkas else "—"


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
    exclude = ["berkas", "berkas_excel", "scan"]
    readonly_fields = ["pdf", "excel", "scan_bertanda_tangan"]

    def _unduh(self, obj, bentuk, berkas):
        return _tautan_unduh(berkas, reverse("documents:unduh", args=[obj.audit_id, obj.pk, bentuk]))

    @admin.display(description="PDF")
    def pdf(self, obj):
        return self._unduh(obj, "pdf", obj.berkas)

    @admin.display(description="Excel")
    def excel(self, obj):
        return self._unduh(obj, "excel", obj.berkas_excel)

    @admin.display(description="scan bertanda tangan")
    def scan_bertanda_tangan(self, obj):
        return self._unduh(obj, "scan", obj.scan)


@admin.register(Ekspor)
class EksporAdmin(HanyaBacaMixin, admin.ModelAdmin):
    list_display = ["judul", "jenis", "diminta_oleh", "status", "diminta_pada", "selesai_pada"]
    list_filter = ["jenis", "status"]
    exclude = ["berkas", "berkas_pdf"]
    readonly_fields = ["excel", "pdf"]

    @admin.display(description="Excel")
    def excel(self, obj):
        return _tautan_unduh(obj.berkas, reverse("ekspor:unduh", args=[obj.pk, "excel"]))

    @admin.display(description="PDF")
    def pdf(self, obj):
        return _tautan_unduh(obj.berkas_pdf, reverse("ekspor:unduh", args=[obj.pk, "pdf"]))
