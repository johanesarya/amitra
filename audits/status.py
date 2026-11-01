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


# --- Stepper progres (NFR-20) ----------------------------------------------------------------
# Enam langkah yang dilihat pengguna; beberapa status berbagi satu langkah.
LANGKAH = [
    ("Persiapan", {S.BELUM_MULAI}),
    ("SER", {S.PENGISIAN_SER}),
    ("Penilaian", {S.PENILAIAN_AUDITOR, S.REKONSILIASI, S.PERLU_AUDIT_LAPANGAN}),
    ("Temuan", {S.PERUMUSAN_TEMUAN}),
    ("Persetujuan", {S.MENUNGGU_PERSETUJUAN}),
    ("Selesai", {S.FINAL, S.TINDAK_LANJUT_PTK, S.DITUTUP}),
]

LANGKAH_BERIKUTNYA = {
    S.BELUM_MULAI: "Audit sudah diplot. Auditee mulai mengisi SER: kategori evaluasi diri, penjelasan, dan bukti per butir.",
    S.PENGISIAN_SER: "Auditee melengkapi semua butir SER, lalu menekan Tinjau dan kirim SER sebelum batas pengisian.",
    S.PENILAIAN_AUDITOR: "Setiap auditor menilai semua butir secara mandiri berdasarkan bukti, lalu mengunci penilaiannya.",
    S.REKONSILIASI: "Ketua auditor menetapkan kategori final untuk butir tanpa kategori terbanyak.",
    S.PERLU_AUDIT_LAPANGAN: "Ketua auditor melaksanakan Audit Lapangan, membuka revisi butir bila perlu, lalu menyelesaikannya.",
    S.PERUMUSAN_TEMUAN: "Ketua auditor merumuskan temuan dan kesimpulan A/B/C, lalu meneruskan hasil kepada auditee.",
    S.MENUNGGU_PERSETUJUAN: "Auditee meninjau hasil AMI, lalu menyetujui atau mengajukan keberatan (satu kali).",
    S.FINAL: "Auditee mengisi rencana PTK untuk setiap temuan KTS/OB, lalu mengirim rencana.",
    S.TINDAK_LANJUT_PTK: "Auditee mencatat realisasi dan bukti PTK; efektivitasnya diverifikasi pada siklus berikutnya.",
    S.DITUTUP: "Siklus audit ini sudah ditutup.",
}


def stepper(audit):
    """Langkah stepper untuk satu audit: [{nomor, label, keadaan}] dengan keadaan selesai/aktif/menunggu."""
    aktif = next(i for i, (_, isi) in enumerate(LANGKAH) if audit.status in isi)
    hasil = []
    for i, (label, _) in enumerate(LANGKAH):
        if i < aktif or audit.status == S.DITUTUP:
            keadaan = "selesai"
        elif i == aktif:
            keadaan = "aktif"
        else:
            keadaan = "menunggu"
        hasil.append({"nomor": i + 1, "label": label, "keadaan": keadaan})
    return hasil
