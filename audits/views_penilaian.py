"""Halaman penilaian auditor, rekonsiliasi, dan Audit Lapangan (FR-25 s.d. FR-31). NFR-08."""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import penilaian as layanan
from .akses import ambil_audit
from .models import Audit, HasilPerhitungan, Penilaian, Penugasan, pilihan_kategori
from .views_ser import _ptk_lalu, _waktu

S = Audit.Status
STATUS_PENILAIAN_DIMULAI = frozenset(set(S) - {S.BELUM_MULAI, S.PENGISIAN_SER})


def _audit_auditor(request, pk):
    """Audit dan penugasan auditor (termasuk ketua) milik pengguna ini."""
    audit, penugasan = ambil_audit(
        request.user, pk, peran=Penugasan.Peran.AUDITOR, queryset=Audit.objects.select_related("periode", "unit__tipe")
    )
    return audit, penugasan


def _galat(e):
    return " ".join(e.messages) if isinstance(e, ValidationError) else str(e)


@login_required
def penilaian_halaman(request, pk):
    audit, penugasan = _audit_auditor(request, pk)
    if audit.status not in STATUS_PENILAIAN_DIMULAI:
        messages.info(request, "Penilaian dimulai setelah auditee mengirim SER.")
        return redirect("audits:detail", audit.pk)
    terbuka = layanan.penilaian_terbuka(audit) and penugasan.dikunci_pada is None
    if terbuka:
        layanan.pastikan_penilaian(audit, request.user)

    butir = list(audit.pernyataan_berlaku())
    if not butir:
        raise Http404("Audit ini tidak memiliki butir.")
    tidak_berlaku = layanan.id_tidak_berlaku(audit)
    milik = {p.pernyataan_id: p for p in audit.penilaian.filter(auditor=request.user)}
    daftar = [(b, milik.get(b.pk), b.pk in tidak_berlaku) for b in butir]

    dipilih = request.GET.get("butir")
    aktif = next((d for d in daftar if str(d[0].pk) == dipilih), None)
    if aktif is None:
        aktif = next((d for d in daftar if not d[2] and (d[1] is None or not d[1].lengkap)), daftar[0])
    indeks = daftar.index(aktif)
    b, pen, tb = aktif
    bisa_ubah = terbuka and not tb and layanan.butir_bisa_diubah(audit, b.pk)

    jawaban = audit.jawaban_ser.filter(pernyataan=b).prefetch_related("bukti").first()
    lihat_lain = layanan.boleh_lihat_penilaian_lain(request.user, audit, penugasan)
    penilaian_lain = (
        audit.penilaian.filter(pernyataan=b).exclude(auditor=request.user).select_related("auditor") if lihat_lain else []
    )
    konfig = {
        "bisa_ubah": bisa_ubah,
        "pk": b.pk,
        "url": reverse("audits:penilaian_simpan", args=[audit.pk, b.pk]),
        "csrf": get_token(request),
        "versi": pen.versi if pen else 0,
        "waktu": _waktu(pen.diubah_pada) if pen and (pen.kategori or pen.dasar_penilaian) else "",
        "data": {
            "kategori": pen.kategori if pen else "",
            "dasar_penilaian": pen.dasar_penilaian if pen else "",
            "kondisi_faktual": pen.kondisi_faktual if pen else "",
        },
    }
    return render(
        request,
        "audits/penilaian/halaman.html",
        {
            "audit": audit,
            "penugasan": penugasan,
            "daftar": daftar,
            "aktif": b,
            "penilaian": pen,
            "aktif_tidak_berlaku": tb,
            "kategori_final_aktif": audit.kategori_final.filter(pernyataan=b).first(),
            "jawaban": jawaban,
            "nomor": indeks + 1,
            "sebelumnya": daftar[indeks - 1][0] if indeks > 0 else None,
            "berikutnya": daftar[indeks + 1][0] if indeks + 1 < len(daftar) else None,
            "bisa_ubah": bisa_ubah,
            "terbuka": terbuka,
            "kategori_pilihan": pilihan_kategori(),
            "penilaian_lain": penilaian_lain,
            "lihat_lain": lihat_lain,
            "ketua_bisa_tandai": penugasan.ketua and audit.status == S.PENILAIAN_AUDITOR,
            "jumlah_lengkap": sum(1 for _, p, t in daftar if t or (p is not None and p.lengkap)),
            "revisi_al": audit.status == S.PERLU_AUDIT_LAPANGAN and audit.revisi_al_dibuka,
            "konfig": konfig,
            **_ptk_lalu(audit, b.pk, penugasan),
        },
    )


@require_POST
@login_required
def penilaian_simpan(request, pk, pernyataan_pk):
    audit, penugasan = _audit_auditor(request, pk)
    try:
        versi = int(request.POST.get("versi", ""))
    except ValueError:
        return JsonResponse({"pesan": "Versi isian tidak valid. Muat ulang halaman."}, status=400)
    try:
        p = layanan.simpan_penilaian(
            audit, penugasan, pernyataan_pk, request.POST.get("kategori", ""),
            request.POST.get("dasar_penilaian", ""), request.POST.get("kondisi_faktual", ""), versi,
        )
    except layanan.KonflikVersi as e:
        p = e.penilaian
        return JsonResponse(
            {
                "pesan": str(e), "versi": p.versi, "waktu": _waktu(p.diubah_pada), "oleh": "",
                "data": {"kategori": p.kategori, "dasar_penilaian": p.dasar_penilaian, "kondisi_faktual": p.kondisi_faktual},
            },
            status=409,
        )
    except layanan.PenilaianTerkunci as e:
        return JsonResponse({"pesan": str(e)}, status=423)
    except ValidationError as e:
        return JsonResponse({"pesan": _galat(e)}, status=400)
    return JsonResponse({"versi": p.versi, "waktu": _waktu(p.diubah_pada), "lengkap": p.lengkap})


@login_required
def penilaian_kunci(request, pk):
    """FR-27, NFR-21: ringkasan lalu kunci penilaian."""
    audit, penugasan = _audit_auditor(request, pk)
    if request.method == "POST":
        try:
            layanan.kunci(audit, penugasan, request.user)
        except (ValidationError, layanan.PenilaianTerkunci) as e:
            messages.error(request, _galat(e))
        else:
            audit.refresh_from_db()
            messages.success(request, "Penilaian Anda telah dikunci.")
            return redirect("audits:detail", audit.pk)
    return render(
        request,
        "audits/penilaian/kunci.html",
        {
            "audit": audit,
            "penugasan": penugasan,
            "belum": layanan.ringkasan(audit, penugasan),
            "terbuka": layanan.penilaian_terbuka(audit) and penugasan.dikunci_pada is None,
        },
    )


@require_POST
@login_required
def tidak_berlaku(request, pk, pernyataan_pk):
    """BR-03: ketua menandai atau membatalkan tanda butir tidak berlaku."""
    audit, penugasan = _audit_auditor(request, pk)
    try:
        if request.POST.get("aksi") == "batal":
            layanan.batal_tidak_berlaku(audit, penugasan, pernyataan_pk)
            messages.success(request, "Butir kembali berlaku dan wajib dinilai.")
        else:
            layanan.tandai_tidak_berlaku(audit, penugasan, pernyataan_pk, request.POST.get("alasan"))
            messages.success(request, "Butir ditandai tidak berlaku dan dikeluarkan dari perhitungan.")
    except PermissionError as e:
        raise PermissionDenied(str(e)) from e
    except ValidationError as e:
        messages.error(request, _galat(e))
    return redirect(f"{reverse('audits:penilaian', args=[audit.pk])}?butir={pernyataan_pk}")


@login_required
def perbedaan(request, pk):
    """FR-31, BR-09: tabel perbedaan penilaian per butir."""
    audit, penugasan = ambil_audit(request.user, pk, queryset=Audit.objects.select_related("periode", "unit"))
    if not layanan.boleh_lihat_penilaian_lain(request.user, audit, penugasan):
        raise PermissionDenied("Penilaian auditor lain dapat dilihat setelah Anda mengunci penilaian.")
    auditor, baris = layanan.tabel_perbedaan(audit)
    berlaku = [r for r in baris if not r["tidak_berlaku"]]
    ringkasan = {
        "total": len(baris),
        "sama": sum(not r["berbeda"] for r in berlaku),
        "berbeda": sum(r["berbeda"] for r in berlaku),
        "seri": sum(bool(r["final"]) and not r["final"].kategori for r in berlaku),
        "tidak_berlaku": len(baris) - len(berlaku),
    }
    return render(
        request,
        "audits/penilaian/perbedaan.html",
        {
            "audit": audit,
            "auditor": auditor,
            "baris": baris,
            "ringkasan": ringkasan,
            "hasil": audit.hasil_tahap(HasilPerhitungan.Tahap.AWAL),
            "adalah_ketua": penugasan is not None and penugasan.ketua,
        },
    )


def _audit_ketua_atau_staf(request, pk):
    audit, penugasan = ambil_audit(request.user, pk, queryset=Audit.objects.select_related("periode__cp_lpm", "unit"))
    adalah_ketua = penugasan is not None and penugasan.ketua
    if not (adalah_ketua or request.user.has_perm("audits.view_audit")):
        raise PermissionDenied("Halaman ini untuk ketua auditor dan Admin LPM.")
    return audit, penugasan, adalah_ketua


@login_required
def rekonsiliasi(request, pk):
    """BR-13: ketua menetapkan kategori butir seri; sistem lalu menghitung dan memutuskan."""
    audit, penugasan, adalah_ketua = _audit_ketua_atau_staf(request, pk)
    if request.method == "POST":
        if not adalah_ketua:
            raise PermissionDenied
        try:
            layanan.tetapkan_seri(
                audit, penugasan, int(request.POST.get("pernyataan", 0)), request.POST.get("kategori"),
                request.POST.get("alasan"),
            )
        except (ValidationError, ValueError) as e:
            messages.error(request, _galat(e) if isinstance(e, ValidationError) else "Butir tidak valid.")
        else:
            audit.refresh_from_db()
            messages.success(request, "Kategori butir ditetapkan.")
            if audit.status not in (S.REKONSILIASI, S.PERLU_AUDIT_LAPANGAN):
                return redirect("audits:detail", audit.pk)
        return redirect("audits:rekonsiliasi", audit.pk)
    auditor, baris = layanan.tabel_perbedaan(audit)
    seri_ids = {k.pernyataan_id for k in layanan.butir_seri(audit)}
    return render(
        request,
        "audits/penilaian/rekonsiliasi.html",
        {
            "audit": audit,
            "adalah_ketua": adalah_ketua,
            "auditor": auditor,
            "baris_seri": [b for b in baris if b["butir"].pk in seri_ids],
            "kategori_pilihan": Penilaian.Kategori.choices,
        },
    )


@login_required
def audit_lapangan(request, pk):
    """FR-29, FR-30: CP LPM, butir penyumbang deviasi, revisi penilaian, dan catatan follow-up."""
    audit, penugasan, adalah_ketua = _audit_ketua_atau_staf(request, pk)
    if audit.status != S.PERLU_AUDIT_LAPANGAN and not audit.hasil_tahap(HasilPerhitungan.Tahap.SETELAH_AL):
        raise Http404("Audit ini tidak memerlukan Audit Lapangan.")
    if request.method == "POST":
        if not adalah_ketua:
            raise PermissionDenied
        aksi = request.POST.get("aksi")
        try:
            if aksi == "buka_revisi":
                layanan.buka_revisi_al(audit, penugasan, request.POST.getlist("butir"))
                messages.success(request, "Revisi penilaian dibuka. Semua auditor perlu mengunci ulang penilaiannya.")
            elif aksi == "selesai":
                layanan.selesaikan_al(audit, penugasan, request.POST.get("catatan"))
                messages.success(request, "Audit Lapangan selesai. Lanjut ke Perumusan Temuan.")
                return redirect("audits:detail", audit.pk)
        except (ValidationError, ValueError) as e:
            messages.error(request, _galat(e) if isinstance(e, ValidationError) else "Isian tidak valid.")
        return redirect("audits:audit_lapangan", audit.pk)
    tim = layanan.tim_auditor(audit)
    return render(
        request,
        "audits/penilaian/audit_lapangan.html",
        {
            "audit": audit,
            "adalah_ketua": adalah_ketua,
            "cp": audit.periode.cp_lpm,
            "hasil_awal": audit.hasil_tahap(HasilPerhitungan.Tahap.AWAL),
            "hasil_al": audit.hasil_tahap(HasilPerhitungan.Tahap.SETELAH_AL),
            "penyumbang": layanan.butir_penyumbang(audit),
            "tim": tim,
            "semua_terkunci": all(p.dikunci_pada for p in tim),
            "ada_seri": bool(layanan.butir_seri(audit)),
        },
    )


class ResetKunciForm(forms.Form):
    alasan = forms.CharField(label="Alasan", widget=forms.Textarea(attrs={"rows": 3, "class": "isian"}))


@permission_required("audits.buka_kunci_audit", raise_exception=True)
def reset_kunci(request, pk, penugasan_pk):
    audit = get_object_or_404(Audit.objects.select_related("unit", "periode"), pk=pk)
    penugasan = get_object_or_404(Penugasan.objects.select_related("pengguna"), pk=penugasan_pk, audit=audit)
    form = ResetKunciForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            layanan.reset_kunci(audit, penugasan, request.user, form.cleaned_data["alasan"])
        except ValidationError as e:
            for pesan in e.messages:
                form.add_error(None, pesan)
        else:
            messages.success(request, f"Kunci penilaian {penugasan.pengguna} direset.")
            return redirect("audits:detail", audit.pk)
    return render(request, "audits/penilaian/reset_kunci.html", {"audit": audit, "penugasan": penugasan, "form": form})
