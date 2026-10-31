"""Halaman analitik: grafik per butir dan tren per unit (FR-49, FR-50). Bab 4: Admin, Master Admin,
Viewer (baca saja) untuk semua unit; auditee hanya unitnya. Hanya audit Final."""

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from masterdata.models import TipeUnit, Unit

from . import analitik, grafik


class FilterAnalitikForm(forms.Form):
    periode = forms.ModelChoiceField(label="Periode", queryset=None, required=False, empty_label=None)
    fakultas = forms.ModelChoiceField(
        label="Fakultas", queryset=Unit.objects.filter(tipe_id=TipeUnit.FAKULTAS), required=False, empty_label="Semua fakultas"
    )
    tipe = forms.ModelChoiceField(label="Tipe unit", queryset=TipeUnit.objects.all(), required=False, empty_label="Semua tipe")
    unit = forms.ModelChoiceField(label="Unit", queryset=Unit.objects.filter(aktif=True), required=False, empty_label="Semua unit")

    def __init__(self, *args, periode_qs, unit_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["periode"].queryset = periode_qs
        if unit_ids is not None:
            # Auditee: hanya unitnya sendiri.
            self.fields["unit"].queryset = Unit.objects.filter(pk__in=unit_ids)
            self.fields["unit"].empty_label = None
            del self.fields["fakultas"], self.fields["tipe"]
        for f in self.fields.values():
            f.widget.attrs["class"] = "isian"


def _pastikan_boleh(user):
    if not analitik.boleh_analitik(user):
        raise PermissionDenied("Analitik tersedia untuk LPM, Rektorat, dan auditee untuk unitnya.")
    return analitik.unit_terlihat(user)


@login_required
def beranda(request):
    unit_ids = _pastikan_boleh(request.user)
    periode_qs = analitik.periode_dengan_hasil(unit_ids)
    form = FilterAnalitikForm(request.GET or None, periode_qs=periode_qs, unit_ids=unit_ids)
    data = form.cleaned_data if form.is_valid() else {}
    periode = data.get("periode") or periode_qs.first()
    konteks = {"form": form, "periode": periode, "boleh_semua": unit_ids is None, "unit_ids": unit_ids}
    if periode is not None:
        audits = analitik.audit_final(
            periode, unit_ids=unit_ids, fakultas=data.get("fakultas"), tipe=data.get("tipe"), unit=data.get("unit")
        )
        butir = analitik.per_butir(audits, periode)
        konteks.update(
            butir=butir,
            svg_butir=grafik.batang_per_butir(butir["baris"], butir["skor_maks"], butir["skor_sesuai"]),
            unit_final=Unit.objects.filter(pk__in=audits.values("unit_id")).select_related("tipe").order_by("nama"),
            jumlah_audit=audits.count(),
            fakultas=Unit.objects.filter(tipe_id=TipeUnit.FAKULTAS),
            tipe_prodi=TipeUnit.objects.filter(kode__in=TipeUnit.TIPE_PRODI),
        )
    return render(request, "audits/analitik/beranda.html", konteks)


@login_required
def tren(request, unit_pk):
    unit_ids = _pastikan_boleh(request.user)
    unit = get_object_or_404(Unit.objects.select_related("tipe", "induk"), pk=unit_pk)
    if unit_ids is not None and unit.pk not in unit_ids:
        raise PermissionDenied("Anda hanya dapat melihat tren unit Anda.")
    baris = analitik.tren_unit(unit)
    if not baris and unit_ids is not None:
        raise Http404("Belum ada audit Final untuk unit ini.")
    return render(request, "audits/analitik/tren.html", {"unit": unit, "baris": baris, "svg": grafik.tren(baris)})
