"""Halaman dokumen per audit: status pembuatan, unduhan, scan bertanda tangan, nomor surat (FR-39 s.d. FR-43)."""

from pathlib import Path

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from audits.akses import ambil_audit
from audits.models import Audit
from audits.ser import UKURAN_BERKAS_MAKS

from . import nomor as layanan_nomor
from . import tugas
from .models import Dokumen, NomorSurat

S = Audit.Status
STATUS_NOMOR_TERBIT = frozenset({S.MENUNGGU_PERSETUJUAN, S.FINAL, S.TINDAK_LANJUT_PTK, S.DITUTUP})


def _akses(request, pk):
    """Bab 4: auditee unitnya, auditor/ketua unit yang ditugaskan, Admin semua; Viewer tidak."""
    return ambil_audit(request.user, pk, queryset=Audit.objects.select_related("unit__kategori_surat", "periode"))


def _bisa_scan(request, penugasan):
    # Keputusan 31 Okt 2026: scan diunggah Admin LPM dan ketua auditor.
    return request.user.has_perm("documents.change_dokumen") or (penugasan is not None and penugasan.ketua)


@login_required
def daftar(request, pk):
    audit, penugasan = _akses(request, pk)
    dokumen = list(audit.dokumen.select_related("ptk", "scan_oleh"))
    konteks = {
        "audit": audit,
        "dokumen": dokumen,
        "masih_diproses": any(d.sedang_dibuat for d in dokumen),
        "bisa_kelola": request.user.has_perm("documents.change_dokumen"),
        "bisa_scan": _bisa_scan(request, penugasan),
        "bisa_nomor": request.user.has_perm("documents.change_nomorsurat"),
        "nomor_terkunci": layanan_nomor.nomor_terkunci(audit),
        "nomor_surat": audit.nomor_surat.select_related("ptk", "dikoreksi_oleh") if request.user.has_perm("documents.view_nomorsurat") else [],
        "nomor_bisa_terbit": audit.status in STATUS_NOMOR_TERBIT,
    }
    if request.headers.get("HX-Request"):
        return render(request, "documents/_daftar.html", konteks)
    return render(request, "documents/daftar.html", konteks)


@login_required
def unduh(request, pk, dokumen_pk, bentuk):
    audit, _ = _akses(request, pk)
    d = get_object_or_404(Dokumen.objects.select_related("ptk"), pk=dokumen_pk, audit=audit)
    berkas = {"pdf": d.berkas, "excel": d.berkas_excel, "scan": d.scan}.get(bentuk)
    if not berkas:
        raise Http404("Berkas belum tersedia.")
    akhiran = {"pdf": ".pdf", "excel": ".xlsx", "scan": "-ttd.pdf"}[bentuk]
    nama = f"{slugify(d.judul)}-{slugify(audit.unit.kode)}{akhiran}"
    return FileResponse(berkas.open("rb"), as_attachment=True, filename=nama)


@require_POST
@permission_required("documents.change_dokumen", raise_exception=True)
def buat_ulang(request, pk, dokumen_pk):
    audit, _ = _akses(request, pk)
    d = get_object_or_404(Dokumen, pk=dokumen_pk, audit=audit)
    tugas.antrekan(d)
    messages.success(request, f"{d.judul} sedang dibuat ulang.")
    return redirect("documents:daftar", audit.pk)


@require_POST
@login_required
def unggah_scan(request, pk, dokumen_pk):
    audit, penugasan = _akses(request, pk)
    if not _bisa_scan(request, penugasan):
        raise PermissionDenied("Scan diunggah oleh Admin LPM atau ketua auditor.")
    d = get_object_or_404(Dokumen, pk=dokumen_pk, audit=audit)
    berkas = request.FILES.get("scan")
    try:
        periksa_scan(berkas)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
        return redirect("documents:daftar", audit.pk)
    lama = d.scan.name if d.scan else None
    d.scan.save(berkas.name, berkas, save=False)
    d.scan_oleh, d.scan_pada = request.user, timezone.now()
    d.save(update_fields=["scan", "scan_oleh", "scan_pada"])
    if lama:
        d.scan.storage.delete(lama)
    messages.success(request, f"Scan bertanda tangan {d.judul} diunggah.")
    return redirect("documents:daftar", audit.pk)


def periksa_scan(berkas):
    """FR-43: hanya PDF, maks. 20 MB, isi benar-benar PDF (NFR-09)."""
    if berkas is None:
        raise ValidationError("Pilih berkas scan.")
    if Path(berkas.name).suffix.lower() != ".pdf":
        raise ValidationError("Scan harus berformat PDF.")
    if berkas.size > UKURAN_BERKAS_MAKS:
        raise ValidationError("Ukuran scan maksimal 20 MB.")
    awal = berkas.read(5)
    berkas.seek(0)
    if not awal.startswith(b"%PDF"):
        raise ValidationError("Isi berkas bukan PDF.")


@require_POST
@permission_required("documents.change_nomorsurat", raise_exception=True)
def terbitkan_nomor(request, pk):
    audit, _ = _akses(request, pk)
    if audit.status not in STATUS_NOMOR_TERBIT:
        messages.error(request, "Nomor surat diterbitkan setelah ketua meneruskan hasil kepada auditee.")
        return redirect("documents:daftar", audit.pk)
    belum = layanan_nomor.terbitkan_untuk_audit(audit)
    if belum:
        messages.error(request, f"Pola nomor surat belum diatur untuk: {', '.join(belum)}.")
    else:
        messages.success(request, "Nomor surat diterbitkan.")
    return redirect("documents:daftar", audit.pk)


class KoreksiForm(forms.Form):
    teks = forms.CharField(label="Nomor surat", max_length=200, widget=forms.TextInput(attrs={"class": "isian"}))
    alasan = forms.CharField(label="Alasan koreksi", widget=forms.Textarea(attrs={"rows": 2, "class": "isian"}))


@permission_required("documents.change_nomorsurat", raise_exception=True)
def koreksi_nomor(request, pk, nomor_pk):
    audit, _ = _akses(request, pk)
    n = get_object_or_404(NomorSurat, pk=nomor_pk, audit=audit)
    form = KoreksiForm(request.POST or None, initial={"teks": n.teks})
    if request.method == "POST" and form.is_valid():
        try:
            layanan_nomor.koreksi(n, form.cleaned_data["teks"], form.cleaned_data["alasan"], request.user)
        except ValidationError as e:
            for pesan in e.messages:
                form.add_error(None, pesan)
        else:
            messages.success(request, "Nomor surat dikoreksi.")
            return redirect("documents:daftar", audit.pk)
    return render(request, "documents/koreksi.html", {"audit": audit, "nomor": n, "form": form})
