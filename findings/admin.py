from django.contrib import admin

from audits.admin import HanyaBacaMixin

from .models import PTK, Kesimpulan, Persetujuan, Temuan, Usulan


@admin.register(Temuan)
class TemuanAdmin(HanyaBacaMixin, admin.ModelAdmin):
    list_display = ["audit", "jenis", "pernyataan", "urutan"]
    list_filter = ["jenis", "audit__periode"]
    search_fields = ["audit__unit__nama", "uraian"]


@admin.register(PTK)
class PTKAdmin(HanyaBacaMixin, admin.ModelAdmin):
    list_display = ["kode", "audit", "status", "target_tanggal", "pic"]
    list_filter = ["status", "audit__periode"]


@admin.register(Kesimpulan)
class KesimpulanAdmin(HanyaBacaMixin, admin.ModelAdmin):
    list_display = ["audit", "skor_a", "skor_b", "skor_c", "c_tidak_berlaku"]


@admin.register(Persetujuan)
class PersetujuanAdmin(HanyaBacaMixin, admin.ModelAdmin):
    list_display = ["audit", "pihak", "keputusan", "oleh", "waktu"]
    list_filter = ["pihak", "keputusan"]


@admin.register(Usulan)
class UsulanAdmin(HanyaBacaMixin, admin.ModelAdmin):
    list_display = ["audit", "oleh", "jenis", "status", "waktu"]
