"""Halaman SER auditee (FR-18 s.d. FR-23). Akses diperiksa per penugasan (NFR-08)."""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import formats, timezone
from django.views.decorators.http import require_POST

from . import ser
from .akses import IZIN_LIHAT_SEMUA, ambil_audit
from .models import Audit, Bukti, Penugasan


def _akses(request, pk, ubah=False):
    """Kembalikan (audit, adalah_auditee).

    Auditee audit ini selalu boleh melihat; hanya auditee yang boleh mengubah.
    Auditor/ketua baru boleh melihat setelah SER dikirim; staf LPM kapan saja.
    """
    audit, penugasan = ambil_audit(request.user, pk, queryset=Audit.objects.select_related("periode", "unit__tipe"))
    adalah_auditee = penugasan is not None and penugasan.peran == Penugasan.Peran.AUDITEE
    if ubah:
        if not adalah_auditee:
            raise PermissionDenied("Hanya auditee yang dapat mengisi SER.")
    elif not (adalah_auditee or request.user.has_perm(IZIN_LIHAT_SEMUA) or audit.ser_dikirim_pada):
        raise PermissionDenied("SER dapat dilihat auditor setelah dikirim auditee.")
    return audit, adalah_auditee


def _waktu(dt):
    return formats.date_format(timezone.localtime(dt), "H.i")


@login_required
def ser_halaman(request, pk):
    audit, adalah_auditee = _akses(request, pk)
    bisa_ubah = adalah_auditee and audit.ser_bisa_diisi()
    if bisa_ubah:
        ser.pastikan_jawaban(audit)
    butir = ser.butir_ser(audit)
    if not butir:
        raise Http404("Audit ini belum memiliki pernyataan standar yang berlaku.")

    dipilih = request.GET.get("butir")
    aktif = next((b for b in butir if str(b[0].pk) == dipilih), None)
    if aktif is None:
        # Default: butir pertama yang belum lengkap.
        aktif = next((b for b in butir if b[1] is None or not b[1].lengkap), butir[0])
    indeks = butir.index(aktif)
    jawaban = aktif[1]
    konfig = {
        "bisa_ubah": bisa_ubah,
        "pk": aktif[0].pk,
        "url": reverse("audits:ser_simpan", args=[audit.pk, aktif[0].pk]),
        "csrf": get_token(request),
        "data": {"penjelasan": jawaban.penjelasan if jawaban else ""},
        "versi": jawaban.versi if jawaban else 0,
        "waktu": _waktu(jawaban.diubah_pada) if jawaban and jawaban.diubah_oleh_id else "",
    }

    return render(
        request,
        "audits/ser/halaman.html",
        {
            "audit": audit,
            "butir": butir,
            "aktif": aktif[0],
            "jawaban": aktif[1],
            "sebelumnya": butir[indeks - 1][0] if indeks > 0 else None,
            "berikutnya": butir[indeks + 1][0] if indeks + 1 < len(butir) else None,
            "nomor": indeks + 1,
            "bisa_ubah": bisa_ubah,
            "adalah_auditee": adalah_auditee,
            "jumlah_lengkap": sum(1 for _, j in butir if j is not None and j.lengkap),
            "konfig": konfig,
            **_ptk_lalu(audit, aktif[0].pk, None),
        },
    )


@require_POST
@login_required
def ser_simpan(request, pk, pernyataan_pk):
    """Autosave satu butir (FR-20). Balasan JSON untuk Alpine."""
    audit, _ = _akses(request, pk, ubah=True)
    try:
        versi = int(request.POST.get("versi", ""))
    except ValueError:
        return JsonResponse({"pesan": "Versi isian tidak valid. Muat ulang halaman."}, status=400)
    try:
        jawaban = ser.simpan_penjelasan(audit, pernyataan_pk, request.POST.get("penjelasan", ""), versi, request.user)
    except ser.KonflikVersi as e:
        j = e.jawaban
        return JsonResponse(
            {
                "pesan": str(e),
                "versi": j.versi,
                "data": {"penjelasan": j.penjelasan},
                "oleh": str(j.diubah_oleh or ""),
                "waktu": _waktu(j.diubah_pada),
            },
            status=409,
        )
    except ser.SERTerkunci as e:
        return JsonResponse({"pesan": str(e)}, status=423)
    except ValidationError as e:
        return JsonResponse({"pesan": " ".join(e.messages)}, status=400)
    return JsonResponse({"versi": jawaban.versi, "waktu": _waktu(jawaban.diubah_pada), "lengkap": jawaban.lengkap})


def _render_bukti(request, audit, pernyataan_pk, galat=None, status=200):
    jawaban = audit.jawaban_ser.filter(pernyataan_id=pernyataan_pk).prefetch_related("bukti").first()
    return render(
        request,
        "audits/ser/_bukti.html",
        {
            "audit": audit,
            "aktif_pk": pernyataan_pk,
            "jawaban": jawaban,
            "bisa_ubah": audit.ser_bisa_diisi(),
            "galat": galat,
            "oob": True,
        },
        status=status,
    )


def _aksi_bukti(request, pk, pernyataan_pk, aksi):
    audit, _ = _akses(request, pk, ubah=True)
    try:
        aksi(audit)
    except (ValidationError, ser.SERTerkunci) as e:
        pesan = " ".join(e.messages) if isinstance(e, ValidationError) else str(e)
        # 200 agar HTMX tetap menukar isi dan menampilkan pesan galat.
        return _render_bukti(request, audit, pernyataan_pk, galat=pesan)
    return _render_bukti(request, audit, pernyataan_pk)


@require_POST
@login_required
def bukti_tautan(request, pk, pernyataan_pk):
    return _aksi_bukti(
        request, pk, pernyataan_pk,
        lambda audit: ser.tambah_tautan(audit, pernyataan_pk, request.POST.get("url"), request.user, request.POST.get("nama")),
    )


@require_POST
@login_required
def bukti_unggah(request, pk, pernyataan_pk):
    def unggah(audit):
        berkas = request.FILES.get("berkas")
        if berkas is None:
            raise ValidationError("Pilih berkas yang akan diunggah.")
        ser.tambah_berkas(audit, pernyataan_pk, berkas, request.user)

    return _aksi_bukti(request, pk, pernyataan_pk, unggah)


@require_POST
@login_required
def bukti_hapus(request, pk, bukti_pk):
    audit, _ = _akses(request, pk, ubah=True)
    bukti = get_object_or_404(Bukti.objects.select_related("jawaban"), pk=bukti_pk, jawaban__audit=audit)
    pernyataan_pk = bukti.jawaban.pernyataan_id
    return _aksi_bukti(request, pk, pernyataan_pk, lambda a: ser.hapus_bukti(a, bukti))


@login_required
def bukti_unduh(request, pk, bukti_pk):
    """Berkas bukti tidak pernah punya URL publik; unduhan selalu lewat pemeriksaan akses."""
    audit, _ = _akses(request, pk)
    bukti = get_object_or_404(Bukti, pk=bukti_pk, jawaban__audit=audit, jenis=Bukti.Jenis.BERKAS)
    return FileResponse(bukti.berkas.open("rb"), as_attachment=True, filename=bukti.nama)


@login_required
def ser_kirim(request, pk):
    """FR-22, NFR-21: ringkasan sebelum kirim; tombol aktif hanya bila lengkap."""
    audit, _ = _akses(request, pk, ubah=True)
    if request.method == "POST":
        try:
            ser.kirim(audit, request.user)
        except (ValidationError, ser.SERTerkunci) as e:
            messages.error(request, " ".join(e.messages) if isinstance(e, ValidationError) else str(e))
        else:
            messages.success(request, "SER berhasil dikirim dan kini terkunci. Auditor akan mulai menilai.")
            return redirect("audits:detail", audit.pk)
    return render(
        request,
        "audits/ser/kirim.html",
        {"audit": audit, "ringkasan": ser.ringkasan(audit), "bisa_ubah": audit.ser_bisa_diisi()},
    )


class BukaKunciForm(forms.Form):
    alasan = forms.CharField(label="Alasan", widget=forms.Textarea(attrs={"rows": 3, "class": "isian"}))
    batas_baru = forms.DateField(
        label="Batas pengisian SER baru",
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "isian"}, format="%Y-%m-%d"),
        help_text="Wajib bila batas periode sudah lewat.",
    )


@permission_required("audits.buka_kunci_audit", raise_exception=True)
def ser_buka_kunci(request, pk):
    audit = get_object_or_404(Audit.objects.select_related("periode", "unit"), pk=pk)
    form = BukaKunciForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            ser.buka_kunci(audit, request.user, form.cleaned_data["alasan"], form.cleaned_data["batas_baru"])
        except ValidationError as e:
            for pesan in e.messages:
                form.add_error(None, pesan)
        else:
            messages.success(request, f"SER {audit.unit} dapat diisi kembali oleh auditee.")
            return redirect("audits:detail", audit.pk)
    return render(request, "audits/ser/buka_kunci.html", {"audit": audit, "form": form})


def _ptk_lalu(audit, butir_pk, penugasan):
    """FR-21, BR-17: PTK periode lalu pada butir yang sama, untuk kotak di samping butir."""
    from findings import tindak_lanjut

    return {
        "ptk_lalu": tindak_lanjut.padanan_butir(audit, tindak_lanjut.ptk_periode_lalu(audit)).get(butir_pk, []),
        "bisa_verifikasi": tindak_lanjut.boleh_verifikasi(audit, penugasan),
    }
