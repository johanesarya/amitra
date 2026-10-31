"""Penerima sinyal: dokumen dibuat mengikuti peristiwa audit, tanpa audits/findings bergantung pada documents."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from audits.models import Audit, RiwayatStatus
from audits.sinyal import tim_audit_disimpan
from findings.sinyal import ptk_diperbarui

from . import nomor, tugas
from .models import JenisDokumen


@receiver(tim_audit_disimpan, dispatch_uid="documents_profil_saat_plot")
def profil_saat_plot(sender, audit, **kwargs):
    # BRD 8.2: Profil Auditee dibuat saat audit diplot (dan saat tim/jadwal berubah).
    tugas.antrekan_profil(audit)


@receiver(post_save, sender=RiwayatStatus, dispatch_uid="documents_saat_status_berubah")
def saat_status_berubah(sender, instance, created, **kwargs):
    if not created or instance.dari == instance.ke:
        return
    audit = Audit.objects.select_related("unit__induk", "unit__kategori_surat").get(pk=instance.audit_id)
    if instance.ke == Audit.Status.MENUNGGU_PERSETUJUAN:
        nomor.terbitkan_untuk_audit(audit)
    elif instance.ke == Audit.Status.FINAL:
        tugas.antrekan_paket_final(audit)


@receiver(ptk_diperbarui, dispatch_uid="documents_ptk_diperbarui")
def ptk_diperbarui_buat_ulang(sender, ptk, **kwargs):
    # Dokumen PTK diperbarui saat auditee mengisi rencana tindak lanjut (BRD 8.2).
    tugas.pastikan_dan_antrekan(ptk.audit, JenisDokumen.PTK, ptk)
