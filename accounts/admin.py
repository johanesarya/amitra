from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm

from .models import LogAudit, User
from .peran import Peran


class PenggunaTambahForm(forms.ModelForm):
    """Akun dibuat tanpa password; pengguna masuk lewat Google (FR-01)."""

    class Meta:
        model = User
        fields = ["email", "nama", "npp", "telepon", "homebase", "peran", "akun_tamu"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_unusable_password()
        if commit:
            user.save()
            self.save_m2m()
        return user


class PenggunaUbahForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"
        field_classes = {}


def _aksi_tetapkan(peran):
    def aksi(modeladmin, request, queryset):
        jumlah = 0
        for user in queryset:
            if user.pk == request.user.pk:
                continue  # tidak boleh mengubah peran sendiri
            user.peran = peran
            user.save()  # save(), bukan update(): menyinkronkan grup dan status
            jumlah += 1
        modeladmin.message_user(request, f"Peran {jumlah} pengguna ditetapkan menjadi {peran.label}.", messages.SUCCESS)

    aksi.__name__ = f"tetapkan_{peran.value.lower()}"
    aksi.short_description = f"Tetapkan peran: {peran.label}"
    aksi.allowed_permissions = ("tetapkan_peran",)
    return aksi


@admin.register(User)
class PenggunaAdmin(UserAdmin):
    form = PenggunaUbahForm
    add_form = PenggunaTambahForm
    ordering = ["nama", "email"]
    list_display = ["email", "nama", "peran", "homebase", "is_active", "last_login"]
    list_filter = ["peran", "akun_tamu", "homebase__tipe", "is_active"]
    search_fields = ["email", "nama", "npp"]
    filter_horizontal = ["unit_jabatan"]
    readonly_fields = ["last_login", "date_joined"]
    actions = [_aksi_tetapkan(p) for p in Peran if p != Peran.MENUNGGU] + ["kirim_undangan_tamu"]

    @admin.action(description="Kirim undangan akun tamu (tautan penetapan password)", permissions=["tetapkan_peran"])
    def kirim_undangan_tamu(self, request, queryset):
        from .undangan import kirim_undangan

        tamu = [u for u in queryset if u.akun_tamu and u.is_active]
        for u in tamu:
            kirim_undangan(u)
        lewat = queryset.count() - len(tamu)
        pesan = f"Undangan dikirim ke {len(tamu)} akun tamu."
        if lewat:
            pesan += f" {lewat} pengguna dilewati karena bukan akun tamu aktif."
        self.message_user(request, pesan, messages.SUCCESS if tamu else messages.WARNING)

    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Data pribadi", {"fields": ["nama", "npp", "telepon"]}),
        ("Unit", {"fields": ["homebase", "unit_jabatan"]}),
        ("Peran", {"fields": ["peran", "akun_tamu"]}),
        ("Status", {"fields": ["is_superuser", "last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": ["email", "nama", "npp", "telepon", "homebase", "peran", "akun_tamu"]}),
    ]

    def has_tetapkan_peran_permission(self, request):
        return request.user.has_perm("accounts.tetapkan_peran")

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not self.has_tetapkan_peran_permission(request) or (obj is not None and obj.pk == request.user.pk):
            ro.append("peran")
        if not request.user.is_superuser:
            ro.append("is_superuser")
        if not self.has_tetapkan_peran_permission(request):
            ro.append("akun_tamu")
        return ro


@admin.register(LogAudit)
class LogAuditAdmin(admin.ModelAdmin):
    """NFR-10 / Bab 4: Master Admin dan Admin melihat log; tidak ada yang bisa menambah, mengubah, atau menghapus."""

    list_display = ["waktu", "aksi", "aktor_email", "objek_nama", "audit_id", "ip"]
    list_filter = ["aksi"]
    date_hierarchy = "waktu"
    search_fields = ["aktor_email", "objek_nama", "alasan"]
    readonly_fields = [f.name for f in LogAudit._meta.fields]
    list_per_page = 50

    def lookup_allowed(self, lookup, value, request=None):
        # Tautan "Log" dari halaman audit memakai ?audit_id=<pk>.
        return lookup in ("audit_id", "aktor__id__exact") or super().lookup_allowed(lookup, value, request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "bisa_ekspor": request.user.has_perm("accounts.ekspor_log")}
        return super().changelist_view(request, extra_context)
