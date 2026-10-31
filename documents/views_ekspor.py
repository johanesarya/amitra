"""Permintaan dan unduhan rapor/rekap/data mentah (FR-44, FR-48, FR-51). Berkas dibuat di antrean."""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from audits import analitik
from audits.models import Audit
from masterdata.models import Periode, TipeUnit, Unit

from . import tugas
from .models import Ekspor


def _bangun_permintaan(request):
    """Validasi jenis, parameter, dan hak akses; kembalikan (jenis, judul, parameter)."""
    user = request.user
    jenis = request.POST.get("jenis")
    if jenis == Ekspor.Jenis.LOG:
        if not user.has_perm("accounts.ekspor_log"):
            raise PermissionDenied("Ekspor log audit khusus Master Admin.")
        dari, sampai = request.POST.get("dari", ""), request.POST.get("sampai", "")
        try:
            if date.fromisoformat(dari) > date.fromisoformat(sampai):
                raise ValueError
        except ValueError:
            raise Http404("Rentang tanggal tidak valid.") from None
        return jenis, f"Log audit {dari} s.d. {sampai}", {"dari": dari, "sampai": sampai}
    terlihat = analitik.unit_terlihat(user)
    if jenis in (Ekspor.Jenis.DATA_AUDIT, Ekspor.Jenis.DATA_PERIODE):
        if not user.has_perm("audits.view_audit"):
            raise PermissionDenied("Data mentah hanya untuk Admin LPM.")
        if jenis == Ekspor.Jenis.DATA_AUDIT:
            a = get_object_or_404(Audit.objects.select_related("unit", "periode"), pk=request.POST.get("audit"))
            return jenis, f"Data mentah {a.unit} — {a.periode}", {"audit": a.pk}
        p = get_object_or_404(Periode, pk=request.POST.get("periode"))
        return jenis, f"Data mentah {p}", {"periode": p.pk}

    periode = get_object_or_404(Periode, pk=request.POST.get("periode"))
    if jenis == Ekspor.Jenis.REKAP_PERIODE:
        if terlihat is not None:
            raise PermissionDenied("Rekap seluruh unit untuk LPM dan Rektorat.")
        return jenis, f"Rekap AMI {periode}", {"periode": periode.pk}
    if jenis != Ekspor.Jenis.RAPOR:
        raise Http404("Jenis unduhan tidak dikenal.")
    if request.POST.get("unit"):
        unit = get_object_or_404(Unit, pk=request.POST["unit"])
        if terlihat is not None and unit.pk not in terlihat:
            raise PermissionDenied("Anda hanya dapat mengunduh rapor unit Anda.")
        return jenis, f"Rapor {unit} — {periode}", {"periode": periode.pk, "unit": unit.pk}
    if terlihat is not None:
        raise PermissionDenied("Rapor lintas unit untuk LPM dan Rektorat.")
    if request.POST.get("fakultas"):
        f = get_object_or_404(Unit, pk=request.POST["fakultas"], tipe_id=TipeUnit.FAKULTAS)
        return jenis, f"Rapor {f} — {periode}", {"periode": periode.pk, "fakultas": f.pk}
    if request.POST.get("tipe"):
        t = get_object_or_404(TipeUnit, pk=request.POST["tipe"], kode__in=TipeUnit.TIPE_PRODI)
        return jenis, f"Rapor {t} — {periode}", {"periode": periode.pk, "tipe": t.pk}
    raise Http404("Pilih fakultas, jenjang, atau unit.")


@require_POST
@login_required
def minta(request):
    if not (analitik.boleh_analitik(request.user) or request.user.has_perm("accounts.ekspor_log")):
        raise PermissionDenied
    jenis, judul, parameter = _bangun_permintaan(request)
    e = Ekspor.objects.create(jenis=jenis, judul=judul, parameter=parameter, diminta_oleh=request.user)
    tugas.antrekan_ekspor(e)
    messages.success(request, f"{judul} sedang dibuat. Halaman ini diperbarui otomatis.")
    return redirect("ekspor:daftar")


@login_required
def daftar(request):
    item = list(request.user.ekspor.all()[:30])
    konteks = {"daftar": item, "masih_diproses": any(e.sedang_dibuat for e in item)}
    if request.headers.get("HX-Request"):
        return render(request, "documents/_ekspor.html", konteks)
    return render(request, "documents/ekspor.html", konteks)


@login_required
def unduh(request, pk, bentuk):
    e = get_object_or_404(Ekspor, pk=pk)
    if e.diminta_oleh_id != request.user.pk and not request.user.has_perm("audits.view_audit"):
        raise Http404  # tidak membocorkan keberadaan berkas orang lain
    berkas = {"excel": e.berkas, "pdf": e.berkas_pdf}.get(bentuk)
    if not berkas:
        raise Http404("Berkas belum tersedia.")
    akhiran = ".xlsx" if bentuk == "excel" else ".pdf"
    return FileResponse(berkas.open("rb"), as_attachment=True, filename=f"{slugify(e.judul)}{akhiran}")
