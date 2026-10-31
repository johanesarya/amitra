from django import forms

from masterdata.models import LingkupBidang, Periode, TipeUnit, Unit

from .layanan import pengguna_bisa_diplot, periksa_tim
from .models import Audit


class PenggunaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.nama or obj.email} — {obj.email}"


class AuditForm(forms.Form):
    """Plot audit (FR-13). Aturan tim diperiksa `layanan.periksa_tim`."""

    unit = forms.ModelChoiceField(
        label="Unit yang diaudit",
        queryset=Unit.objects.filter(aktif=True).select_related("tipe", "induk"),
        empty_label="— Pilih unit —",
    )
    lingkup = forms.ModelMultipleChoiceField(
        label="Lingkup bidang", queryset=LingkupBidang.objects.all(), widget=forms.CheckboxSelectMultiple
    )
    auditee = PenggunaChoiceField(label="Auditee", queryset=None, empty_label="— Pilih auditee —")
    auditor = forms.ModelMultipleChoiceField(label="Auditor", queryset=None, required=False)
    ketua = forms.ModelChoiceField(label="Ketua auditor", queryset=None, required=False)
    jadwal_audit_lapangan = forms.DateTimeField(
        label="Jadwal Audit Lapangan",
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        help_text="Opsional; bisa diisi belakangan.",
    )

    def __init__(self, *args, periode, audit=None, **kwargs):
        if audit is not None and "initial" not in kwargs:
            kwargs["initial"] = {
                "unit": audit.unit,
                "lingkup": list(audit.lingkup.all()),
                "auditee": audit.auditee,
                "auditor": audit.auditor,
                "ketua": audit.ketua,
                "jadwal_audit_lapangan": audit.jadwal_audit_lapangan,
            }
        super().__init__(*args, **kwargs)
        self.periode = periode
        self.audit = audit
        pengguna = pengguna_bisa_diplot()
        for nama in ("auditee", "auditor", "ketua"):
            self.fields[nama].queryset = pengguna
        for nama in ("unit", "auditee", "jadwal_audit_lapangan"):
            self.fields[nama].widget.attrs["class"] = "isian"
        self.fields["unit"].widget.attrs["x-model"] = "unit"
        self.fields["lingkup"].widget.attrs["class"] = "size-4"

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        for pesan in periksa_tim(
            periode=self.periode,
            unit=data["unit"],
            lingkup=data["lingkup"],
            auditee=data["auditee"],
            auditor=data["auditor"],
            ketua=data["ketua"],
            audit=self.audit,
        ):
            self.add_error(None, pesan)
        return data

    def id_auditor_terpilih(self):
        """Id auditor yang dicentang, dari isian yang dikirim atau nilai awal (FR-17)."""
        if self.is_bound:
            return [str(v) for v in self.data.getlist("auditor")]
        return [str(u.pk) for u in self.initial.get("auditor") or []]

    def id_ketua_terpilih(self):
        if self.is_bound:
            return self.data.get("ketua") or ""
        ketua = self.initial.get("ketua")
        return str(ketua.pk) if ketua else ""


class FilterAuditForm(forms.Form):
    periode = forms.ModelChoiceField(label="Periode", queryset=Periode.objects.all(), required=False, empty_label=None)
    fakultas = forms.ModelChoiceField(
        label="Fakultas", queryset=Unit.objects.filter(tipe_id=TipeUnit.FAKULTAS), required=False,
        empty_label="Semua fakultas",
    )
    tipe = forms.ModelChoiceField(label="Tipe unit", queryset=TipeUnit.objects.all(), required=False, empty_label="Semua tipe")
    status = forms.ChoiceField(label="Status", choices=[("", "Semua status")] + Audit.Status.choices, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "isian"


class ImporPlotForm(forms.Form):
    periode = forms.ModelChoiceField(label="Periode tujuan", queryset=Periode.objects.all(), empty_label=None)
    berkas = forms.FileField(label="Berkas Excel (.xlsx)", help_text="Maksimal 2 MB, gunakan template plot audit.")
