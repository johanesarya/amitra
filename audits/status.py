"""Perpindahan status audit (BRD 6.6). Semua perubahan status lewat `ubah_status()`."""

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Audit, RiwayatStatus

S = Audit.Status

TRANSISI = {
    S.BELUM_MULAI: {S.PENGISIAN_SER},
    S.PENGISIAN_SER: {S.PENILAIAN_AUDITOR},
    # PENGISIAN_SER di sini = buka kunci SER oleh Master Admin (FR-23).
    S.PENILAIAN_AUDITOR: {S.REKONSILIASI, S.PENGISIAN_SER},
    # PENILAIAN_AUDITOR di sini = Master Admin mereset kunci auditor saat Rekonsiliasi.
    S.REKONSILIASI: {S.PERLU_AUDIT_LAPANGAN, S.PERUMUSAN_TEMUAN, S.PENILAIAN_AUDITOR},
    S.PERLU_AUDIT_LAPANGAN: {S.PERUMUSAN_TEMUAN},
    S.PERUMUSAN_TEMUAN: {S.MENUNGGU_PERSETUJUAN},
    S.MENUNGGU_PERSETUJUAN: {S.FINAL, S.PERUMUSAN_TEMUAN},
    S.FINAL: {S.TINDAK_LANJUT_PTK, S.DITUTUP},
    S.TINDAK_LANJUT_PTK: {S.DITUTUP},
    S.DITUTUP: set(),
}


@transaction.atomic
def ubah_status(audit, ke, oleh, alasan=""):
    """Pindahkan status bila transisinya sah, kunci baris audit, dan catat riwayat."""
    terkini = Audit.objects.select_for_update().get(pk=audit.pk)
    if ke not in TRANSISI[terkini.status]:
        raise ValidationError(
            f"Status audit tidak dapat berpindah dari {terkini.get_status_display()} ke {S(ke).label}."
        )
    RiwayatStatus.objects.create(audit=terkini, dari=terkini.status, ke=ke, oleh=oleh, alasan=alasan)
    Audit.objects.filter(pk=audit.pk).update(status=ke)
    audit.status = ke
    return audit


def catat(audit, oleh, alasan):
    """Catat tindakan tanpa perpindahan status (mis. perpanjangan batas SER)."""
    return RiwayatStatus.objects.create(audit=audit, dari=audit.status, ke=audit.status, oleh=oleh, alasan=alasan)
