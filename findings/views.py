"""Halaman Perumusan Temuan, Persetujuan, dan PTK. Akses per penugasan (NFR-08)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from audits import penilaian as penilaian_layanan
from audits.akses import ambil_audit
from audits.models import Audit, Bukti, HasilPerhitungan, Penilaian, Penugasan
from masterdata.models import TujuanAudit

from . import layanan, tindak_lanjut
from .models import PTK, Kesimpulan, Temuan, Usulan

S = Audit.Status
STATUS_PERUMUSAN_DST = frozenset(
    {S.PERUMUSAN_TEMUAN, S.MENUNGGU_PERSETUJUAN, S.FINAL, S.TINDAK_LANJUT_PTK, S.DITUTUP}
)
STATUS_TERLIHAT_AUDITEE = STATUS_PERUMUSAN_DST - {S.PERUMUSAN_TEMUAN}


def _galat(e):
    return " ".join(e.messages) if isinstance(e, ValidationError) else str(e)


def _ambil(request, pk):
    audit, penugasan = ambil_audit(
        request.user, pk, queryset=Audit.objects.select_related("periode__pengaturan", "unit__tipe")
    )
    return audit, penugasan


def _kelompok_temuan(audit):
    temuan = list(audit.temuan.select_related("pernyataan__standar", "ptk").prefetch_related("usulan__oleh"))
    return {
        "kelebihan": [t for t in temuan if t.jenis == Temuan.Jenis.KELEBIHAN],
        "kts_ob": [t for t in temuan if t.jenis in Temuan.JENIS_PTK],
        "peluang": [t for t in temuan if t.jenis == Temuan.Jenis.PELUANG],
    }


@login_required
def perumusan(request, pk):
    """FR-32 s.d. FR-34: ketua merumuskan; anggota mengusulkan; Admin LPM melihat."""
    audit, penugasan = _ambil(request, pk)
    adalah_auditor = penugasan is not None and penugasan.peran == Penugasan.Peran.AUDITOR
    if not (adalah_auditor or request.user.has_perm("audits.view_audit")):
        raise PermissionDenied("Halaman ini untuk tim auditor dan Admin LPM.")
    if audit.status not in STATUS_PERUMUSAN_DST:
        messages.info(request, "Perumusan temuan dimulai setelah rekonsiliasi atau Audit Lapangan selesai.")
        return redirect("audits:detail", audit.pk)

    if request.method == "POST":
        return _aksi_perumusan(request, audit, penugasan)

    if audit.status == S.PERUMUSAN_TEMUAN:
        layanan.sinkron_temuan(audit)
    adalah_ketua = penugasan is not None and penugasan.ketua
    bisa_ubah = adalah_ketua and audit.status == S.PERUMUSAN_TEMUAN
    auditor, baris = penilaian_layanan.tabel_perbedaan(audit)
    kelompok = _kelompok_temuan(audit)
    for t in kelompok["kelebihan"] + kelompok["kts_ob"]:
        t.saran = layanan.usulan_uraian(audit, t) if bisa_ubah else []
    return render(
        request,
        "findings/perumusan.html",
        {
            "audit": audit,
            "penugasan": penugasan,
            "adalah_ketua": adalah_ketua,
            "bisa_ubah": bisa_ubah,
            "bisa_usul": adalah_auditor and not adalah_ketua and audit.status == S.PERUMUSAN_TEMUAN,
            "auditor": auditor,
            "baris": [b for b in baris if not b["tidak_berlaku"]],
            "kategori_pilihan": Penilaian.Kategori.choices,
            **kelompok,
            "usulan": audit.usulan.select_related("oleh", "temuan__pernyataan"),
            "kesimpulan": Kesimpulan.objects.filter(audit=audit).prefetch_related("tujuan_tercapai").first(),
            "opsi_kesimpulan": audit.periode.pengaturan.opsi_kesimpulan(),
            "tujuan": TujuanAudit.objects.filter(aktif=True),
            "keberatan": layanan.keberatan_belum_ditanggapi(audit),
            "riwayat_keberatan": audit.persetujuan.filter(keputusan="KEBERATAN"),
            "verifikasi_lalu": tindak_lanjut.ringkasan_verifikasi(audit),
            "syarat": layanan.syarat_ketua(audit) if audit.status == S.PERUMUSAN_TEMUAN else [],
            "checklist": layanan.CHECKLIST_KETUA,
        },
    )


def _aksi_perumusan(request, audit, penugasan):
    aksi = request.POST.get("aksi", "")
    jangkar = ""
    try:
        if aksi == "kategori":
            layanan.ubah_kategori_final(
                audit, penugasan, int(request.POST["pernyataan"]), request.POST.get("kategori"), request.POST.get("alasan")
            )
            jangkar = "kategori"
            messages.success(request, "Kategori final diperbarui.")
        elif aksi == "uraian":
            t = get_object_or_404(Temuan, pk=request.POST.get("temuan"), audit=audit)
            layanan.simpan_uraian(audit, penugasan, t, request.POST.get("uraian"))
            jangkar = f"temuan-{t.pk}"
            messages.success(request, "Uraian temuan disimpan.")
        elif aksi == "peluang_tambah":
            layanan.tambah_peluang(audit, penugasan, request.POST.get("uraian"))
            jangkar = "peluang"
            messages.success(request, "Peluang Peningkatan ditambahkan.")
        elif aksi == "peluang_hapus":
            t = get_object_or_404(Temuan, pk=request.POST.get("temuan"), audit=audit)
            layanan.hapus_peluang(audit, penugasan, t)
            jangkar = "peluang"
            messages.success(request, "Peluang Peningkatan dihapus.")
        elif aksi == "usulan":
            temuan = None
            if request.POST.get("temuan"):
                temuan = get_object_or_404(Temuan, pk=request.POST["temuan"], audit=audit)
            layanan.ajukan_usulan(audit, penugasan, request.POST.get("jenis"), request.POST.get("isi"), temuan)
            jangkar = "usulan"
            messages.success(request, "Usulan dikirim ke ketua.")
        elif aksi in ("usulan_terima", "usulan_tolak"):
            u = get_object_or_404(Usulan, pk=request.POST.get("usulan"), audit=audit)
            layanan.tanggapi_usulan(audit, penugasan, u, aksi == "usulan_terima")
            jangkar = "usulan"
            messages.success(request, "Usulan ditanggapi.")
        elif aksi == "kesimpulan":
            layanan.simpan_kesimpulan(audit, penugasan, request.POST, request.POST.getlist("tujuan"))
            jangkar = "kesimpulan"
            messages.success(request, "Kesimpulan disimpan.")
        elif aksi == "tanggapan":
            layanan.tanggapi_keberatan(audit, penugasan, request.POST.get("tanggapan"))
            jangkar = "keberatan"
            messages.success(request, "Tanggapan atas keberatan disimpan.")
        elif aksi == "ajukan":
            layanan.ajukan_ke_auditee(audit, penugasan, set(request.POST.getlist("checklist")))
            messages.success(request, "Hasil audit diteruskan kepada auditee untuk disetujui.")
            return redirect("audits:detail", audit.pk)
        else:
            messages.error(request, "Aksi tidak dikenal.")
    except PermissionError as e:
        raise PermissionDenied(str(e)) from e
    except (ValidationError, ValueError, KeyError) as e:
        messages.error(request, _galat(e) if isinstance(e, ValidationError) else "Isian tidak valid.")
        jangkar = jangkar or "checklist"
    url = reverse("findings:perumusan", args=[audit.pk])
    return redirect(f"{url}#{jangkar}" if jangkar else url)


def _hasil_untuk(audit, auditee_final):
    final = audit.hasil_tahap(HasilPerhitungan.Tahap.FINAL)
    nilai = []
    if final and auditee_final:
        nilai = [(t.pengguna, final.nilai_auditor.get(str(t.pengguna_id))) for t in penilaian_layanan.tim_auditor(audit)]
    return final, nilai


@login_required
def persetujuan(request, pk):
    """FR-38, BR-18: ringkasan hasil, checklist auditee, atau keberatan sekali."""
    audit, penugasan = _ambil(request, pk)
    adalah_auditee = penugasan is not None and penugasan.peran == Penugasan.Peran.AUDITEE
    if adalah_auditee and audit.status not in STATUS_TERLIHAT_AUDITEE:
        raise PermissionDenied("Hasil audit dapat dilihat auditee setelah ketua menyelesaikan perumusan.")
    if not adalah_auditee and audit.status not in STATUS_PERUMUSAN_DST:
        return redirect("audits:detail", audit.pk)

    if request.method == "POST":
        try:
            if request.POST.get("aksi") == "setuju":
                layanan.setujui(audit, penugasan, set(request.POST.getlist("checklist")))
                messages.success(request, "Terima kasih. Hasil AMI kini Final; silakan isi rencana tindak lanjut PTK.")
            elif request.POST.get("aksi") == "keberatan":
                layanan.ajukan_keberatan(audit, penugasan, request.POST.get("keberatan"))
                messages.success(request, "Keberatan Anda dikirim ke ketua auditor.")
            return redirect("findings:persetujuan", audit.pk)
        except PermissionError as e:
            raise PermissionDenied(str(e)) from e
        except ValidationError as e:
            messages.error(request, _galat(e))
            return redirect("findings:persetujuan", audit.pk)

    final_terbuka = audit.status in penilaian_layanan.STATUS_SETELAH_FINAL
    hasil, nilai = _hasil_untuk(audit, final_terbuka or not adalah_auditee)
    return render(
        request,
        "findings/persetujuan.html",
        {
            "audit": audit,
            "adalah_auditee": adalah_auditee,
            **_kelompok_temuan(audit),
            "kesimpulan": Kesimpulan.objects.filter(audit=audit).prefetch_related("tujuan_tercapai").first(),
            "opsi_kesimpulan": dict(audit.periode.pengaturan.opsi_kesimpulan()),
            "tujuan": TujuanAudit.objects.filter(aktif=True),
            "hasil": hasil,
            "nilai_auditor": nilai,
            "bisa_putuskan": adalah_auditee and audit.status == S.MENUNGGU_PERSETUJUAN,
            "sudah_keberatan": layanan.sudah_keberatan(audit),
            "riwayat_persetujuan": audit.persetujuan.select_related("oleh"),
            "checklist": layanan.CHECKLIST_AUDITEE,
            "final_terbuka": final_terbuka,
        },
    )


@login_required
def ptk(request, pk):
    """FR-36: auditee mengisi akar masalah, rencana, target, dan PIC per PTK setelah Final."""
    audit, penugasan = _ambil(request, pk)
    adalah_auditee = penugasan is not None and penugasan.peran == Penugasan.Peran.AUDITEE
    if audit.status not in STATUS_TERLIHAT_AUDITEE:
        raise PermissionDenied("PTK tersedia setelah ketua menyelesaikan perumusan.")
    if request.method == "POST":
        return _aksi_ptk(request, audit, penugasan)
    daftar = list(audit.ptk.select_related("temuan__pernyataan__standar", "diverifikasi_oleh", "diverifikasi_di__periode").prefetch_related("bukti"))
    return render(
        request,
        "findings/ptk.html",
        {
            "audit": audit,
            "daftar_ptk": daftar,
            "bisa_isi": adalah_auditee and audit.status == S.FINAL,
            "bisa_kirim": adalah_auditee and audit.status == S.FINAL and daftar and all(p.rencana_lengkap for p in daftar),
            "bisa_realisasi": adalah_auditee and audit.status == S.TINDAK_LANJUT_PTK,
        },
    )


def _aksi_ptk(request, audit, penugasan):
    aksi = request.POST.get("aksi", "rencana")
    jangkar = ""
    try:
        if aksi == "kirim_rencana":
            tindak_lanjut.kirim_rencana(audit, penugasan)
            messages.success(request, "Rencana PTK dikirim. Silakan laksanakan dan catat realisasinya.")
        elif aksi == "bukti_hapus":
            b = get_object_or_404(Bukti.objects.select_related("ptk"), pk=request.POST.get("bukti"), ptk__audit=audit)
            jangkar = f"ptk-{b.ptk_id}"
            tindak_lanjut.hapus_bukti(audit, penugasan, b)
            messages.success(request, "Bukti dihapus.")
        else:
            item = get_object_or_404(PTK, pk=request.POST.get("ptk"), audit=audit)
            jangkar = f"ptk-{item.pk}"
            if aksi == "realisasi":
                tindak_lanjut.simpan_realisasi(audit, penugasan, item, request.POST.get("realisasi"))
                messages.success(request, f"Realisasi {item.kode} disimpan.")
            elif aksi == "bukti_tautan":
                tindak_lanjut.tambah_bukti(audit, penugasan, item, url=request.POST.get("url"), nama=request.POST.get("nama"))
                messages.success(request, "Bukti tindak lanjut ditambahkan.")
            elif aksi == "bukti_unggah":
                berkas = request.FILES.get("berkas")
                if berkas is None:
                    raise ValidationError("Pilih berkas yang akan diunggah.")
                tindak_lanjut.tambah_bukti(audit, penugasan, item, berkas=berkas)
                messages.success(request, "Bukti tindak lanjut diunggah.")
            else:
                item = layanan.isi_ptk(audit, penugasan, item, request.POST)
                if item.rencana_lengkap:
                    messages.success(request, f"Rencana {item.kode} disimpan.")
                else:
                    messages.info(request, f"{item.kode} disimpan sebagai draf; lengkapi semua kolom.")
    except PermissionError as e:
        raise PermissionDenied(str(e)) from e
    except ValidationError as e:
        messages.error(request, _galat(e))
    url = reverse("findings:ptk", args=[audit.pk])
    return redirect(f"{url}#{jangkar}" if jangkar else url)


@login_required
def ptk_bukti(request, pk, bukti_pk):
    """Unduh bukti tindak lanjut PTK; tanpa URL publik."""
    audit, _ = _ambil(request, pk)
    b = get_object_or_404(Bukti, pk=bukti_pk, ptk__audit=audit, jenis=Bukti.Jenis.BERKAS)
    return FileResponse(b.berkas.open("rb"), as_attachment=True, filename=b.nama)


@login_required
def verifikasi(request, pk):
    """FR-37: tim auditor audit ini memverifikasi PTK periode lalu unit yang sama."""
    audit, penugasan = _ambil(request, pk)
    if request.method == "POST":
        ptk_lalu = get_object_or_404(PTK, pk=request.POST.get("ptk"))
        try:
            tindak_lanjut.verifikasi(audit, penugasan, ptk_lalu, request.POST.get("hasil"), request.POST.get("catatan"))
        except PermissionError as e:
            raise PermissionDenied(str(e)) from e
        except ValidationError as e:
            messages.error(request, _galat(e))
        else:
            messages.success(request, f"Verifikasi {ptk_lalu.kode} disimpan.")
        return redirect(f"{reverse('findings:verifikasi', args=[audit.pk])}#ptk-{ptk_lalu.pk}")
    return render(
        request,
        "findings/verifikasi.html",
        {
            "audit": audit,
            "daftar": tindak_lanjut.ptk_periode_lalu(audit),
            "ringkasan": tindak_lanjut.ringkasan_verifikasi(audit),
            "bisa_verifikasi": tindak_lanjut.boleh_verifikasi(audit, penugasan),
        },
    )


@login_required
def verifikasi_bukti(request, pk, bukti_pk):
    """Bukti PTK periode lalu dibuka tim audit periode ini (mereka tidak ditugaskan di audit lama)."""
    audit, _ = _ambil(request, pk)
    lalu = tindak_lanjut.audit_periode_lalu(audit)
    if lalu is None:
        raise Http404
    b = get_object_or_404(Bukti, pk=bukti_pk, ptk__audit=lalu, jenis=Bukti.Jenis.BERKAS)
    return FileResponse(b.berkas.open("rb"), as_attachment=True, filename=b.nama)
