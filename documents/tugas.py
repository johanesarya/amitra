"""Pembuatan dokumen lewat antrean Django-Q2 (FR-41, NFR-03). Tidak pernah dijalankan di request web."""

from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django_q.tasks import async_task

from audits.models import HasilPerhitungan
from audits.penilaian import STATUS_SETELAH_FINAL

from . import sinyal
from .konteks import excel_daftar_tilik, konteks
from .models import Dokumen, JenisDokumen
from .pdf import render_pdf

TEMPLATE = {
    JenisDokumen.PROFIL_AUDITEE: "documents/pdf/profil.html",
    JenisDokumen.DAFTAR_TILIK: "documents/pdf/daftar_tilik.html",
    JenisDokumen.TEMUAN: "documents/pdf/temuan.html",
    JenisDokumen.PTK: "documents/pdf/ptk.html",
    JenisDokumen.BERITA_ACARA: "documents/pdf/berita_acara.html",
    JenisDokumen.LAPORAN_AMI: "documents/pdf/laporan.html",
}


def antrekan(dokumen):
    """Tandai Diantre lalu kirim ke antrean setelah transaksi tersimpan."""
    Dokumen.objects.filter(pk=dokumen.pk).update(status=Dokumen.Status.DIANTRE, galat="", diminta_pada=timezone.now())
    dokumen.status = Dokumen.Status.DIANTRE
    pk = dokumen.pk
    transaction.on_commit(
        lambda: async_task("documents.tugas.buat_dokumen", pk, task_name=f"dokumen-{pk}", group=f"audit-{dokumen.audit_id}")
    )
    return dokumen


def pastikan_dan_antrekan(audit, jenis, ptk=None):
    dokumen, _ = Dokumen.objects.get_or_create(audit=audit, jenis=jenis, ptk=ptk)
    return antrekan(dokumen)


def antrekan_profil(audit):
    return pastikan_dan_antrekan(audit, JenisDokumen.PROFIL_AUDITEE)


def jenis_paket_final(audit):
    jenis = [JenisDokumen.DAFTAR_TILIK, JenisDokumen.TEMUAN, JenisDokumen.LAPORAN_AMI]
    if audit.hasil_tahap(HasilPerhitungan.Tahap.SETELAH_AL):
        jenis.append(JenisDokumen.BERITA_ACARA)  # hanya bila Audit Lapangan dilaksanakan
    return jenis


def antrekan_paket_final(audit):
    """Saat Final: Daftar Tilik, Temuan, Laporan AMI, Berita Acara (bila ada AL), dan satu PTK per KTS/OB."""
    hasil = [pastikan_dan_antrekan(audit, j) for j in jenis_paket_final(audit)]
    hasil += [pastikan_dan_antrekan(audit, JenisDokumen.PTK, p) for p in audit.ptk.all()]
    hasil.append(antrekan_profil(audit))
    return hasil


def buat_dokumen(dokumen_id):
    """Dijalankan worker. Galat dicatat lalu dilempar ulang agar antrean mencoba lagi (NFR-04)."""
    dokumen = Dokumen.objects.select_related("audit__unit", "audit__periode", "ptk").get(pk=dokumen_id)
    Dokumen.objects.filter(pk=dokumen.pk).update(status=Dokumen.Status.DIPROSES)
    try:
        html = render_to_string(TEMPLATE[dokumen.jenis], konteks(dokumen))
        pdf = render_pdf(html)
        # Simpan nama berkas lama dulu: FieldFile yang sama akan menunjuk berkas baru setelah save().
        lama = [(f.storage, f.name) for f in (dokumen.berkas, dokumen.berkas_excel) if f]
        dokumen.berkas.save(f"{dokumen.jenis.lower()}.pdf", ContentFile(pdf), save=False)
        if dokumen.jenis == JenisDokumen.DAFTAR_TILIK:
            dokumen.berkas_excel.save("daftar_tilik.xlsx", ContentFile(excel_daftar_tilik(dokumen.audit)), save=False)
        for storage, nama in lama:
            storage.delete(nama)
    except Exception as e:
        Dokumen.objects.filter(pk=dokumen.pk).update(status=Dokumen.Status.GAGAL, galat=str(e)[:2000])
        raise
    dokumen.status = Dokumen.Status.SIAP
    dokumen.galat = ""
    dokumen.versi += 1
    dokumen.selesai_pada = timezone.now()
    dokumen.save(update_fields=["berkas", "berkas_excel", "status", "galat", "versi", "selesai_pada"])
    _kabari_bila_paket_siap(dokumen.audit)
    return dokumen.pk


def antrekan_ekspor(ekspor):
    pk = ekspor.pk
    transaction.on_commit(lambda: async_task("documents.tugas.buat_ekspor", pk, task_name=f"ekspor-{pk}"))
    return ekspor


def buat_ekspor(ekspor_id):
    """Rapor, rekap, dan data mentah dibuat di worker (NFR-03); galat dilempar ulang untuk coba ulang."""
    from . import ekspor as pembuat
    from .models import Ekspor

    e = Ekspor.objects.get(pk=ekspor_id)
    Ekspor.objects.filter(pk=e.pk).update(status=Dokumen.Status.DIPROSES)
    pdf = None
    try:
        if e.jenis == Ekspor.Jenis.RAPOR:
            excel = pembuat.rapor(e.parameter)
        elif e.jenis == Ekspor.Jenis.REKAP_PERIODE:
            excel, pdf = pembuat.rekap_periode(e.parameter)
        elif e.jenis == Ekspor.Jenis.DATA_AUDIT:
            excel = pembuat.data_audit(e.parameter)
        elif e.jenis == Ekspor.Jenis.LOG:
            excel = pembuat.log_audit(e.parameter)
        else:
            excel = pembuat.data_periode(e.parameter)
        e.berkas.save("ekspor.xlsx", ContentFile(excel), save=False)
        if pdf is not None:
            e.berkas_pdf.save("rekap.pdf", ContentFile(pdf), save=False)
    except Exception as galat:
        Ekspor.objects.filter(pk=e.pk).update(status=Dokumen.Status.GAGAL, galat=str(galat)[:2000])
        raise
    e.status, e.galat, e.selesai_pada = Dokumen.Status.SIAP, "", timezone.now()
    e.save(update_fields=["berkas", "berkas_pdf", "status", "galat", "selesai_pada"])
    return e.pk


def _kabari_bila_paket_siap(audit):
    """FR-42: beri sinyal bila semua dokumen Final siap; modul notifications yang mengirim email."""
    if audit.status not in STATUS_SETELAH_FINAL:
        return
    dokumen = list(audit.dokumen.all())
    jenis_wajib = set(jenis_paket_final(audit))
    if jenis_wajib <= {d.jenis for d in dokumen} and all(d.status == Dokumen.Status.SIAP for d in dokumen):
        sinyal.paket_final_siap.send(sender=Dokumen, audit=audit)
