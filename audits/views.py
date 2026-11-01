from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.http import require_POST

from masterdata.models import Periode

from . import impor_plot, penilaian, views_penilaian
from .akses import perlu_akses_audit
from .forms import AuditForm, FilterAuditForm, ImporPlotForm
from .layanan import beban_auditor, simpan_audit
from .models import Audit, Penugasan

KUNCI_SESI_IMPOR = "audits_impor_plot"


def _prefetch_tim():
    return Prefetch("penugasan", queryset=Penugasan.objects.select_related("pengguna"))


@login_required
def beranda(request):
    """Tugas Saya (NFR-18): audit tempat pengguna ditugaskan."""
    from accounts.peran import Peran

    if request.user.peran == Peran.VIEWER:
        return redirect("analitik:beranda")
    penugasan = (
        Penugasan.objects.filter(pengguna=request.user)
        .exclude(audit__status=Audit.Status.DITUTUP)
        .select_related("audit__periode", "audit__unit")
        .order_by("-audit__periode__tahun_akademik", "audit__unit__nama")
    )
    from notifications.tenggat import tenggat_pengguna

    tenggat = {t.audit.pk: t for t in tenggat_pengguna(request.user)}
    penugasan = list(penugasan)
    for p in penugasan:
        p.tenggat = tenggat.get(p.audit_id)
        p.aksi = _aksi_penugasan(p)
    punya_hasil_final = Penugasan.objects.filter(
        pengguna=request.user, peran=Penugasan.Peran.AUDITEE, audit__status__in=penilaian.STATUS_SETELAH_FINAL
    ).exists()
    return render(
        request,
        "audits/beranda.html",
        {
            "daftar_penugasan": penugasan,
            "punya_hasil_final": punya_hasil_final,
            "jumlah_auditee": sum(p.peran == Penugasan.Peran.AUDITEE for p in penugasan),
            "perlu_tindakan": sum(p.aksi is not None for p in penugasan),
        },
    )


def _aksi_penugasan(p):
    """Tombol tugas berikutnya di kartu Tugas Saya: (label, url), atau None bila tidak ada yang perlu dikerjakan."""
    a, S = p.audit, Audit.Status
    auditee, auditor = p.peran == Penugasan.Peran.AUDITEE, p.peran == Penugasan.Peran.AUDITOR
    if auditee and a.ser_bisa_diisi:
        return "Isi SER", reverse("audits:ser", args=[a.pk])
    if auditor and a.status == S.PENILAIAN_AUDITOR and not p.dikunci_pada:
        return "Nilai SER", reverse("audits:penilaian", args=[a.pk])
    if p.ketua and a.status == S.REKONSILIASI:
        return "Rekonsiliasi", reverse("audits:rekonsiliasi", args=[a.pk])
    if p.ketua and a.status == S.PERLU_AUDIT_LAPANGAN:
        return "Audit Lapangan", reverse("audits:audit_lapangan", args=[a.pk])
    if auditor and a.revisi_al_dibuka and not p.dikunci_pada:
        return "Revisi penilaian", reverse("audits:penilaian", args=[a.pk])
    if p.ketua and a.status == S.PERUMUSAN_TEMUAN:
        return "Rumuskan temuan", reverse("findings:perumusan", args=[a.pk])
    if auditee and a.status == S.MENUNGGU_PERSETUJUAN:
        return "Tinjau dan setujui hasil", reverse("findings:persetujuan", args=[a.pk])
    if auditee and a.status == S.FINAL:
        return "Isi rencana PTK", reverse("findings:ptk", args=[a.pk])
    return None


def _periode_terpilih(request):
    pk = request.POST.get("periode") or request.GET.get("periode")
    if pk:
        return get_object_or_404(Periode, pk=pk)
    periode = Periode.objects.filter(aktif=True).first() or Periode.objects.first()
    if periode is None:
        raise Http404("Belum ada periode. Buat periode di menu Administrasi.")
    return periode


@permission_required("audits.view_audit", raise_exception=True)
def daftar_audit(request):
    periode = _periode_terpilih(request)
    filter_form = FilterAuditForm(request.GET or None, initial={"periode": periode})
    qs = (
        Audit.objects.filter(periode=periode)
        .select_related("unit__tipe", "unit__induk")
        .prefetch_related(_prefetch_tim())
        .annotate(jumlah_auditor=Count("penugasan", filter=Q(penugasan__peran=Penugasan.Peran.AUDITOR)))
    )
    if filter_form.is_valid():
        f = filter_form.cleaned_data
        if f.get("fakultas"):
            qs = qs.filter(Q(unit=f["fakultas"]) | Q(unit__induk=f["fakultas"]))
        if f.get("tipe"):
            qs = qs.filter(unit__tipe=f["tipe"])
        if f.get("status"):
            qs = qs.filter(status=f["status"])
    return render(
        request,
        "audits/daftar.html",
        {"periode": periode, "filter_form": filter_form, "daftar_audit": qs},
    )


def _konteks_form(request, form, periode, audit=None):
    beban = beban_auditor(periode)
    if audit is not None:
        # Beban dihitung di luar audit yang sedang diubah.
        for p in audit.penugasan.filter(peran=Penugasan.Peran.AUDITOR):
            beban[p.pengguna_id] = beban.get(p.pengguna_id, 1) - 1
    calon = [
        {
            "user": u,
            "beban": beban.get(u.pk, 0),
            "unit_konflik": [pk for pk in [u.homebase_id, *(j.pk for j in u.unit_jabatan.all())] if pk],
        }
        for u in form.fields["auditor"].queryset
    ]
    return {"form": form, "periode": periode, "audit": audit, "calon_auditor": calon}


def _simpan_dari_form(request, form, periode, audit=None):
    d = form.cleaned_data
    try:
        return simpan_audit(
            periode=periode, unit=d["unit"], lingkup=d["lingkup"], auditee=d["auditee"], auditor=d["auditor"],
            ketua=d["ketua"], jadwal_audit_lapangan=d["jadwal_audit_lapangan"], oleh=request.user, audit=audit,
        )
    except ValidationError as e:
        for pesan in e.messages:
            form.add_error(None, pesan)
        return None


@permission_required("audits.add_audit", raise_exception=True)
def buat_audit(request):
    periode = _periode_terpilih(request)
    form = AuditForm(request.POST or None, periode=periode)
    if request.method == "POST" and form.is_valid():
        audit = _simpan_dari_form(request, form, periode)
        if audit is not None:
            messages.success(request, f"Audit {audit.unit} berhasil diplot.")
            return redirect(f"{reverse('audits:daftar')}?periode={periode.pk}")
    return render(request, "audits/form.html", _konteks_form(request, form, periode))


@permission_required("audits.change_audit", raise_exception=True)
def ubah_audit(request, pk):
    audit = get_object_or_404(Audit.objects.select_related("periode", "unit").prefetch_related(_prefetch_tim()), pk=pk)
    form = AuditForm(request.POST or None, periode=audit.periode, audit=audit)
    if request.method == "POST" and form.is_valid():
        if _simpan_dari_form(request, form, audit.periode, audit) is not None:
            messages.success(request, f"Tim audit {audit.unit} berhasil diperbarui.")
            return redirect(f"{reverse('audits:daftar')}?periode={audit.periode_id}")
    return render(request, "audits/form.html", _konteks_form(request, form, audit.periode, audit))


@require_POST
@login_required
def periksa_tim_view(request):
    """Pengecekan langsung lewat HTMX sebelum disimpan (FR-14, FR-17)."""
    audit = None
    if request.POST.get("audit"):
        if not request.user.has_perm("audits.change_audit"):
            raise PermissionDenied
        audit = get_object_or_404(Audit, pk=request.POST["audit"])
        periode = audit.periode
    else:
        if not request.user.has_perm("audits.add_audit"):
            raise PermissionDenied
        periode = _periode_terpilih(request)
    form = AuditForm(request.POST, periode=periode, audit=audit)
    return render(
        request,
        "audits/_periksa_tim.html",
        {"form": form, "siap": form.is_valid(), "jumlah_auditor": len(request.POST.getlist("auditor"))},
    )


@permission_required("audits.delete_audit", raise_exception=True)
def hapus_audit(request, pk):
    audit = get_object_or_404(Audit, pk=pk)
    if audit.status != Audit.Status.BELUM_MULAI:
        messages.error(request, "Audit hanya dapat dihapus selama berstatus Belum Mulai.")
        return redirect(f"{reverse('audits:daftar')}?periode={audit.periode_id}")
    if request.method == "POST":
        periode_id, unit = audit.periode_id, audit.unit
        audit.delete()
        messages.success(request, f"Audit {unit} dihapus.")
        return redirect(f"{reverse('audits:daftar')}?periode={periode_id}")
    return render(request, "audits/hapus.html", {"audit": audit})


STATUS_PERUMUSAN_DST = frozenset({
    Audit.Status.PERUMUSAN_TEMUAN, Audit.Status.MENUNGGU_PERSETUJUAN, Audit.Status.FINAL,
    Audit.Status.TINDAK_LANJUT_PTK, Audit.Status.DITUTUP,
})
STATUS_TERLIHAT_AUDITEE = STATUS_PERUMUSAN_DST - {Audit.Status.PERUMUSAN_TEMUAN}


@perlu_akses_audit()
def detail_audit(request, pk):
    """FR-16: tim audit dan pernyataan standar berlaku, terlihat sejak audit diplot."""
    audit = request.audit
    p = request.penugasan
    adalah_auditee = p is not None and p.peran == Penugasan.Peran.AUDITEE
    pernyataan = audit.pernyataan_berlaku().prefetch_related("tipe_unit")
    adalah_auditor = p is not None and p.peran == Penugasan.Peran.AUDITOR
    adalah_ketua = p is not None and p.ketua
    staf = request.user.has_perm("audits.view_audit")
    tim_auditor = penilaian.tim_auditor(audit)
    # FR-28: hasil perhitungan ditampilkan ke ketua dan Admin.
    hasil = []
    if adalah_ketua or staf:
        for h in audit.hasil.all():
            nilai = [(t.pengguna, h.nilai_auditor.get(str(t.pengguna_id))) for t in tim_auditor]
            hasil.append({"obj": h, "nilai": nilai})
    return render(
        request,
        "audits/detail.html",
        {
            "audit": audit,
            "penugasan_saya": p,
            "tim": audit.penugasan.select_related("pengguna"),
            "pernyataan": pernyataan,
            "adalah_auditor": adalah_auditor,
            "adalah_ketua_atau_staf": adalah_ketua or staf,
            "penilaian_dimulai": audit.status in views_penilaian.STATUS_PENILAIAN_DIMULAI,
            "penilaian_terbuka_saya": adalah_auditor and penilaian.penilaian_terbuka(audit) and p.dikunci_pada is None,
            "lihat_perbedaan": penilaian.boleh_lihat_penilaian_lain(request.user, audit, p) and audit.penilaian.exists(),
            "tim_auditor": tim_auditor,
            "hasil": hasil,
            "verifikasi_lalu": _ringkasan_verifikasi(audit) if (adalah_auditor or staf) else None,
            "bisa_perumusan": (adalah_auditor or staf) and audit.status in STATUS_PERUMUSAN_DST,
            "bisa_lihat_hasil": audit.status in STATUS_TERLIHAT_AUDITEE
            and (adalah_auditee or adalah_auditor or staf),
            "bisa_reset_kunci": request.user.has_perm("audits.buka_kunci_audit")
            and audit.status in (Audit.Status.PENILAIAN_AUDITOR, Audit.Status.REKONSILIASI),
            "jumlah_seri": len(penilaian.butir_seri(audit)) if audit.status in (Audit.Status.REKONSILIASI, Audit.Status.PERLU_AUDIT_LAPANGAN) else 0,
            "bisa_isi_ser": adalah_auditee and audit.ser_bisa_diisi(),
            # Sama dengan aturan di views_ser._akses.
            "bisa_lihat_ser": adalah_auditee or request.user.has_perm("audits.view_audit") or bool(audit.ser_dikirim_pada),
            "riwayat": audit.riwayat_status.select_related("oleh"),
            "bisa_buka_kunci": request.user.has_perm("audits.buka_kunci_audit")
            and (audit.status in Audit.STATUS_SER_TERBUKA or audit.status == Audit.Status.PENILAIAN_AUDITOR),
        },
    )


@permission_required("audits.add_audit", raise_exception=True)
def impor_plot_view(request):
    """FR-15: unggah → pratinjau dengan galat per baris → simpan."""
    konteks = {"template_url": static("audits/template_plot_audit.xlsx"), "kolom": impor_plot.KOLOM}
    aksi = request.POST.get("aksi")

    if request.method == "POST" and aksi == "simpan":
        tersimpan = request.session.get(KUNCI_SESI_IMPOR)
        if not tersimpan:
            messages.error(request, "Sesi pratinjau sudah berakhir. Unggah ulang berkas.")
            return redirect("audits:impor")
        periode = get_object_or_404(Periode, pk=tersimpan["periode"])
        hasil = impor_plot.validasi(tersimpan["baris"], periode)
        if not hasil.ada_galat:
            try:
                jumlah = impor_plot.simpan(hasil, periode, request.user)
            except ValidationError as e:
                messages.error(request, "Data berubah sejak pratinjau: " + " ".join(e.messages))
            else:
                del request.session[KUNCI_SESI_IMPOR]
                messages.success(request, f"{jumlah} audit berhasil diplot.")
                return redirect(f"{reverse('audits:daftar')}?periode={periode.pk}")
        konteks.update(form=ImporPlotForm(initial={"periode": periode}), hasil=hasil, periode=periode)
        return render(request, "audits/impor.html", konteks)

    if request.method == "POST":
        form = ImporPlotForm(request.POST, request.FILES)
        if form.is_valid():
            periode = form.cleaned_data["periode"]
            try:
                baris = impor_plot.baca_berkas(form.cleaned_data["berkas"])
            except impor_plot.GalatImpor as e:
                form.add_error("berkas", str(e))
            else:
                hasil = impor_plot.validasi(baris, periode)
                request.session[KUNCI_SESI_IMPOR] = {"periode": periode.pk, "baris": baris}
                konteks.update(hasil=hasil, periode=periode)
    else:
        form = ImporPlotForm(initial={"periode": Periode.objects.filter(aktif=True).first()})
    konteks["form"] = form
    return render(request, "audits/impor.html", konteks)


def _ringkasan_verifikasi(audit):
    from findings import tindak_lanjut

    r = tindak_lanjut.ringkasan_verifikasi(audit)
    return r if r["total"] else None


@login_required
def riwayat(request):
    """FR-24: audit Final unit tempat pengguna pernah/sedang menjadi auditee (hanya-baca)."""
    unit_ids = Penugasan.objects.filter(pengguna=request.user, peran=Penugasan.Peran.AUDITEE).values("audit__unit_id")
    daftar = (
        Audit.objects.filter(unit_id__in=unit_ids, status__in=penilaian.STATUS_SETELAH_FINAL)
        .select_related("unit", "periode")
        .prefetch_related("hasil")
        .order_by("unit__nama", "-periode__tahun_akademik")
    )
    for a in daftar:
        a.hasil_final = next((h for h in a.hasil.all() if h.tahap == "FINAL"), None)
    return render(request, "audits/riwayat.html", {"daftar": daftar})


@permission_required("audits.buka_kunci_audit", raise_exception=True)
def arsip_periode(request, periode_pk):
    """Bab 6.6: Master Admin mengarsipkan periode; audit Final/Tindak Lanjut PTK ditutup dengan alasan."""
    from findings import tindak_lanjut

    periode = get_object_or_404(Periode, pk=periode_pk)
    terbuka = Audit.objects.filter(periode=periode, status__in=(Audit.Status.FINAL, Audit.Status.TINDAK_LANJUT_PTK))
    belum_final = Audit.objects.filter(periode=periode).exclude(status__in=penilaian.STATUS_SETELAH_FINAL).count()
    if request.method == "POST":
        try:
            jumlah = tindak_lanjut.arsipkan_periode(periode, request.user, request.POST.get("alasan"))
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        else:
            messages.success(request, f"{jumlah} audit {periode} ditutup.")
            return redirect(f"{reverse('audits:dashboard')}?periode={periode.pk}")
    return render(
        request, "audits/arsip_periode.html", {"periode": periode, "terbuka": terbuka.select_related("unit"), "belum_final": belum_final}
    )
