from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import path, reverse

from . import impor
from .models import (
    LingkupBidang,
    PengaturanInstitusi,
    PengaturanPeriode,
    Periode,
    PernyataanStandar,
    Standar,
    TahapanPeriode,
    KategoriSurat,
    TipeUnit,
    TujuanAudit,
    Unit,
)
from .salin import salin_standar


@admin.register(TipeUnit)
class TipeUnitAdmin(admin.ModelAdmin):
    """Tipe unit tetap (diisi migrasi); hanya bisa dilihat."""

    list_display = ["nama", "kode"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ["nama", "kode", "tipe", "induk", "kategori_surat", "nama_pimpinan", "aktif"]
    list_filter = ["tipe", "aktif", "kategori_surat", "induk"]
    search_fields = ["nama", "kode", "nama_pimpinan"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "induk":
            kwargs["queryset"] = Unit.objects.filter(tipe_id=TipeUnit.FAKULTAS)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class TahapanInline(admin.TabularInline):
    model = TahapanPeriode
    extra = 5
    max_num = len(TahapanPeriode.Jenis)

    def get_extra(self, request, obj=None, **kwargs):
        return 0 if obj is not None and obj.tahapan.exists() else self.max_num


class PengaturanPeriodeInline(admin.StackedInline):
    model = PengaturanPeriode
    can_delete = False
    max_num = 1
    fieldsets = [
        ("Skala penilaian auditor", {"fields": [("skor_kts", "skor_ob", "skor_sesuai", "skor_pelampauan")]}),
        ("KKM, deviasi, dan jumlah auditor", {"fields": [("kkm", "ambang_deviasi", "minimal_auditor")]}),
        ("Penyesuaian nilai efektif per temuan", {"fields": [("penyesuaian_kts", "penyesuaian_ob", "penyesuaian_kelebihan")]}),
        ("Bobot Kesimpulan A/B/C (total 100%)", {"fields": [("bobot_a", "bobot_b", "bobot_c")]}),
        (
            "Label opsi Kesimpulan A/B/C",
            {"fields": [("label_kesimpulan_1", "label_kesimpulan_2", "label_kesimpulan_3", "label_kesimpulan_4")]},
        ),
        (
            "Proporsi hasil akhir (total 100%)",
            {
                "fields": [("proporsi_ne", "proporsi_nk")],
                "description": "Belum diputuskan LPM; hasil akhir tidak dihitung selama kosong.",
            },
        ),
    ]


@admin.register(Periode)
class PeriodeAdmin(admin.ModelAdmin):
    list_display = ["nama", "tahun_akademik", "aktif", "cp_lpm"]
    list_filter = ["aktif"]
    search_fields = ["nama", "tahun_akademik"]
    inlines = [TahapanInline, PengaturanPeriodeInline]
    actions = ["aktifkan_periode"]

    def get_formset_kwargs(self, request, obj, inline, prefix):
        kwargs = super().get_formset_kwargs(request, obj, inline, prefix)
        if isinstance(inline, PengaturanPeriodeInline) and (obj is None or obj.pk is None):
            # Periode baru: tampilkan pengaturan periode terakhir sebagai nilai awal.
            kwargs["initial"] = [PengaturanPeriode.nilai_awal()]
        return kwargs

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        PengaturanPeriode.pastikan_ada(form.instance)

    @admin.action(description="Aktifkan periode terpilih")
    def aktifkan_periode(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Pilih tepat satu periode untuk diaktifkan.", messages.ERROR)
            return
        periode = queryset.get()
        periode.aktifkan()
        self.message_user(request, f"{periode} sekarang menjadi periode aktif.", messages.SUCCESS)

    def get_urls(self):
        return [
            path(
                "<int:pk>/salin-standar/",
                self.admin_site.admin_view(self.salin_standar_view),
                name="masterdata_periode_salin_standar",
            ),
        ] + super().get_urls()

    def salin_standar_view(self, request, pk):
        if not request.user.has_perm("masterdata.add_standar"):
            raise PermissionDenied
        tujuan = get_object_or_404(Periode, pk=pk)

        class SalinForm(forms.Form):
            asal = forms.ModelChoiceField(
                label="Salin dari periode",
                queryset=Periode.objects.exclude(pk=tujuan.pk),
            )

        form = SalinForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                jumlah_s, jumlah_p = salin_standar(form.cleaned_data["asal"], tujuan)
            except ValueError as e:
                form.add_error(None, str(e))
            else:
                self.message_user(
                    request, f"{jumlah_s} standar dan {jumlah_p} pernyataan disalin ke {tujuan}.", messages.SUCCESS
                )
                return redirect("admin:masterdata_periode_change", tujuan.pk)
        return render(
            request,
            "admin/masterdata/periode/salin_standar.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "original": tujuan,
                "title": f"Salin standar ke {tujuan}",
                "form": form,
            },
        )


@admin.register(PengaturanInstitusi)
class PengaturanInstitusiAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not PengaturanInstitusi.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = PengaturanInstitusi.muat()
        return redirect("admin:masterdata_pengaturaninstitusi_change", obj.pk)


@admin.register(KategoriSurat)
class KategoriSuratAdmin(admin.ModelAdmin):
    list_display = ["nama", "kode"]
    search_fields = ["nama", "kode"]


@admin.register(TujuanAudit)
class TujuanAuditAdmin(admin.ModelAdmin):
    list_display = ["kode", "teks", "urutan", "aktif"]
    list_editable = ["urutan", "aktif"]


@admin.register(LingkupBidang)
class LingkupBidangAdmin(admin.ModelAdmin):
    list_display = ["nama", "urutan"]
    list_editable = ["urutan"]
    search_fields = ["nama"]


class PernyataanInline(admin.StackedInline):
    model = PernyataanStandar
    extra = 0
    filter_horizontal = ["tipe_unit"]
    fields = [("kode", "urutan", "aktif"), "pernyataan", "pertanyaan_panduan", "tipe_unit"]


class ImporStandarForm(forms.Form):
    periode = forms.ModelChoiceField(label="Periode tujuan", queryset=Periode.objects.all())
    berkas = forms.FileField(label="Berkas Excel (.xlsx)", help_text="Maksimal 2 MB, gunakan template impor.")


@admin.register(Standar)
class StandarAdmin(admin.ModelAdmin):
    list_display = ["kode", "nama", "periode", "lingkup", "sumber", "status", "jumlah_pernyataan"]
    list_filter = ["periode", "lingkup", "sumber", "status"]
    search_fields = ["kode", "nama"]
    inlines = [PernyataanInline]

    @admin.display(description="jumlah pernyataan")
    def jumlah_pernyataan(self, obj):
        return obj.pernyataan.count()

    def get_urls(self):
        return [
            path("impor/", self.admin_site.admin_view(self.impor_view), name="masterdata_standar_impor"),
        ] + super().get_urls()

    KUNCI_SESI = "masterdata_impor_standar"

    def impor_view(self, request):
        """FR-09: unggah → pratinjau dengan galat per baris → simpan."""
        if not (self.has_add_permission(request) and self.has_change_permission(request)):
            raise PermissionDenied

        konteks = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Impor standar dari Excel",
            "template_url": static("masterdata/template_impor_standar.xlsx"),
            "kolom": impor.KOLOM,
        }
        aksi = request.POST.get("aksi")

        if request.method == "POST" and aksi == "simpan":
            tersimpan = request.session.get(self.KUNCI_SESI)
            if not tersimpan:
                self.message_user(request, "Sesi pratinjau sudah berakhir. Unggah ulang berkas.", messages.ERROR)
                return redirect("admin:masterdata_standar_impor")
            periode = get_object_or_404(Periode, pk=tersimpan["periode"])
            hasil = impor.validasi(tersimpan["baris"], periode)
            if not hasil.ada_galat:
                ringkasan = impor.simpan(hasil, periode)
                del request.session[self.KUNCI_SESI]
                self.message_user(
                    request,
                    "Impor selesai: {standar_baru} standar baru, {standar_diperbarui} diperbarui; "
                    "{pernyataan_baru} pernyataan baru, {pernyataan_diperbarui} diperbarui.".format(**ringkasan),
                    messages.SUCCESS,
                )
                return redirect(reverse("admin:masterdata_standar_changelist") + f"?periode__id__exact={periode.pk}")
            # Data berubah sejak pratinjau: tampilkan galat terbaru.
            form = ImporStandarForm(initial={"periode": periode})
            konteks.update(form=form, hasil=hasil, periode=periode)
            return render(request, "admin/masterdata/standar/impor.html", konteks)

        if request.method == "POST":
            form = ImporStandarForm(request.POST, request.FILES)
            if form.is_valid():
                periode = form.cleaned_data["periode"]
                try:
                    baris = impor.baca_berkas(form.cleaned_data["berkas"])
                except impor.GalatImpor as e:
                    form.add_error("berkas", str(e))
                else:
                    hasil = impor.validasi(baris, periode)
                    request.session[self.KUNCI_SESI] = {"periode": periode.pk, "baris": baris}
                    konteks.update(hasil=hasil, periode=periode)
        else:
            aktif = Periode.objects.filter(aktif=True).first()
            form = ImporStandarForm(initial={"periode": aktif})
        konteks["form"] = form
        return render(request, "admin/masterdata/standar/impor.html", konteks)


@admin.register(PernyataanStandar)
class PernyataanStandarAdmin(admin.ModelAdmin):
    list_display = ["kode", "ringkas", "standar", "aktif"]
    list_filter = ["standar__periode", "standar__lingkup", "tipe_unit", "aktif"]
    search_fields = ["kode", "pernyataan", "standar__kode"]
    filter_horizontal = ["tipe_unit"]
    list_select_related = ["standar"]

    @admin.display(description="pernyataan")
    def ringkas(self, obj):
        return obj.pernyataan[:80]
