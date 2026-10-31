"""Dashboard Admin (FR-45, BR-07): progres semua audit dalam satu periode, langsung dan tanpa query per audit (NFR-02)."""

from collections import Counter, defaultdict

from django import forms
from django.contrib.auth.decorators import permission_required
from django.db.models import Count, Prefetch, Q
from django.db.models.functions import Trim
from django.shortcuts import render

from masterdata.models import PernyataanStandar, Standar, TahapanPeriode

from .forms import FilterAuditForm
from .models import Audit, HasilPerhitungan, JawabanSER, Penilaian, Penugasan

S = Audit.Status


class FilterDashboardForm(FilterAuditForm):
    deviasi_tinggi = forms.BooleanField(label="Hanya deviasi di atas ambang", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["deviasi_tinggi"].widget.attrs["class"] = "size-4"


def jumlah_butir_per_audit(audits, periode):
    """Jumlah butir berlaku per audit dengan satu query pernyataan (sama dengan berlaku_untuk)."""
    data = defaultdict(lambda: {"tipe": set()})
    for pid, lingkup, sumber, pengusul, tipe in PernyataanStandar.objects.filter(
        aktif=True, standar__periode=periode, standar__status=Standar.Status.DISETUJUI
    ).values_list("pk", "standar__lingkup_id", "standar__sumber", "standar__unit_pengusul_id", "tipe_unit"):
        d = data[pid]
        d.update(lingkup=lingkup, sumber=sumber, pengusul=pengusul)
        d["tipe"].add(tipe)
    hasil = {}
    for a in audits:
        lingkup = {l.pk for l in a.lingkup.all()}
        pengusul_boleh = {a.unit_id, a.unit.induk_id}
        hasil[a.pk] = sum(
            1
            for d in data.values()
            if a.unit.tipe_id in d["tipe"]
            and d["lingkup"] in lingkup
            and (d["sumber"] == Standar.Sumber.LPM or d["pengusul"] in pengusul_boleh)
        )
    return hasil


def _ringkasan(baris):
    status = Counter(b["audit"].status for b in baris)
    total = len(baris)
    ser_terkirim = sum(1 for b in baris if b["audit"].ser_dikirim_pada)
    return {
        "total": total,
        "per_status": [(s, s.label, status.get(s, 0)) for s in S if status.get(s, 0)],
        "persen_ser": round(ser_terkirim * 100 / total) if total else 0,
        "ser_terkirim": ser_terkirim,
        "perlu_al": status.get(S.PERLU_AUDIT_LAPANGAN, 0),
        "deviasi_tinggi": sum(1 for b in baris if b["hasil"] and b["hasil"].deviasi_tinggi),
    }


@permission_required("audits.view_audit", raise_exception=True)
def dashboard(request):
    from .views import _periode_terpilih

    periode = _periode_terpilih(request)
    form = FilterDashboardForm(request.GET or None, initial={"periode": periode})
    audits = Audit.objects.filter(periode=periode).select_related("unit__tipe", "unit__induk").prefetch_related(
        "lingkup",
        Prefetch("penugasan", queryset=Penugasan.objects.select_related("pengguna").order_by("-ketua", "pengguna__nama")),
        Prefetch("hasil", queryset=HasilPerhitungan.objects.order_by("dihitung_pada", "id")),
    )
    hanya_deviasi = False
    if form.is_valid():
        f = form.cleaned_data
        if f.get("fakultas"):
            audits = audits.filter(Q(unit=f["fakultas"]) | Q(unit__induk=f["fakultas"]))
        if f.get("tipe"):
            audits = audits.filter(unit__tipe=f["tipe"])
        if f.get("status"):
            audits = audits.filter(status=f["status"])
        hanya_deviasi = f.get("deviasi_tinggi")
    audits = list(audits.order_by("unit__induk__nama", "unit__tipe__urutan", "unit__nama"))
    ids = [a.pk for a in audits]

    total_butir = jumlah_butir_per_audit(audits, periode)
    ser_lengkap = dict(
        JawabanSER.objects.filter(audit_id__in=ids)
        .annotate(isi=Trim("penjelasan"), jumlah_bukti=Count("bukti"))
        .exclude(isi="")
        .filter(jumlah_bukti__gt=0)
        .values("audit_id")
        .annotate(n=Count("id"))
        .values_list("audit_id", "n")
    )
    dinilai = {
        (r["audit_id"], r["auditor_id"]): r["n"]
        for r in Penilaian.objects.filter(audit_id__in=ids)
        .exclude(kategori="")
        .annotate(dasar=Trim("dasar_penilaian"))
        .exclude(dasar="")
        .values("audit_id", "auditor_id")
        .annotate(n=Count("id"))
    }
    tahap = {t.jenis: t.tanggal_selesai for t in TahapanPeriode.objects.filter(periode=periode)}

    baris = []
    for a in audits:
        hasil = list(a.hasil.all())
        terakhir = hasil[-1] if hasil else None
        if hanya_deviasi and not (terakhir and terakhir.deviasi_tinggi):
            continue
        tim = list(a.penugasan.all())
        n = total_butir.get(a.pk, 0)
        if a.status in Audit.STATUS_SER_TERBUKA:
            tenggat = ("SER", a.batas_ser_khusus or tahap.get(TahapanPeriode.Jenis.PENGISIAN_SER))
        elif a.status == S.PENILAIAN_AUDITOR:
            tenggat = ("Penilaian", tahap.get(TahapanPeriode.Jenis.REVIEW_AUDITOR))
        else:
            tenggat = None
        baris.append({
            "audit": a,
            "auditee": next((p.pengguna for p in tim if p.peran == Penugasan.Peran.AUDITEE), None),
            "total_butir": n,
            "ser_lengkap": ser_lengkap.get(a.pk, 0),
            "auditor": [
                {"penugasan": p, "dinilai": dinilai.get((a.pk, p.pengguna_id), 0)}
                for p in tim
                if p.peran == Penugasan.Peran.AUDITOR
            ],
            "hasil": terakhir,
            "tenggat": tenggat if tenggat and tenggat[1] else None,
        })
    return render(
        request,
        "audits/dashboard.html",
        {"periode": periode, "form": form, "baris": baris, "ringkasan": _ringkasan(baris)},
    )
