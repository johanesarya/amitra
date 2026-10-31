from django.contrib import admin

from .models import Audit, Penugasan


class HanyaBacaMixin:
    """Audit dikelola lewat halaman Plot Audit; Admin Django hanya untuk pengecekan."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PenugasanInline(HanyaBacaMixin, admin.TabularInline):
    model = Penugasan
    extra = 0


@admin.register(Audit)
class AuditAdmin(HanyaBacaMixin, admin.ModelAdmin):
    list_display = ["unit", "periode", "status", "jadwal_audit_lapangan"]
    list_filter = ["periode", "status", "unit__tipe"]
    search_fields = ["unit__nama", "unit__kode"]
    inlines = [PenugasanInline]


@admin.register(Penugasan)
class PenugasanAdmin(HanyaBacaMixin, admin.ModelAdmin):
    list_display = ["pengguna", "peran", "ketua", "audit"]
    list_filter = ["peran", "ketua", "audit__periode"]
    search_fields = ["pengguna__email", "pengguna__nama", "audit__unit__nama"]
