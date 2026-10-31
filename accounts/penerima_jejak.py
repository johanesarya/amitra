"""Penerima sinyal yang mengisi audit log (NFR-10). Disetujui 31 Okt 2026 (sementara)."""

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from audits.models import Audit, HasilPerhitungan, RiwayatStatus
from audits.sinyal import tim_audit_disimpan
from findings.sinyal import ptk_diverifikasi
from masterdata.models import PengaturanPeriode

from .jejak import catat
from .models import LogAudit, User

A = LogAudit.Aksi
KOLOM_PENGGUNA = ["peran", "akun_tamu", "is_active", "is_superuser"]


# --- Login (NFR-10) --------------------------------------------------------------------

@receiver(user_logged_in, dispatch_uid="jejak_login")
def login(sender, request, user, **kwargs):
    backend = getattr(user, "backend", "") or ""
    catat(A.LOGIN, objek=user, aktor=user, request=request, data={"cara": "google" if "allauth" in backend and not request.POST.get("password") else "password"})


@receiver(user_logged_out, dispatch_uid="jejak_logout")
def logout(sender, request, user, **kwargs):
    if user is not None:
        catat(A.LOGOUT, objek=user, aktor=user, request=request)


@receiver(user_login_failed, dispatch_uid="jejak_login_gagal")
def login_gagal(sender, credentials, request=None, **kwargs):
    # Password tidak pernah dicatat; Django sudah menyamarkannya di `credentials`.
    email = str(credentials.get("email") or credentials.get("username") or credentials.get("login") or "")[:254]
    catat(A.LOGIN_GAGAL, aktor_email=email, request=request, data={"email": email})


# --- Peran dan status pengguna (NFR-10) ------------------------------------------------------

@receiver(pre_save, sender=User, dispatch_uid="jejak_pengguna_sebelum")
def pengguna_sebelum(sender, instance, update_fields=None, **kwargs):
    if instance.pk is None or (update_fields is not None and not set(update_fields) & set(KOLOM_PENGGUNA)):
        instance._jejak_lama = None
        return
    instance._jejak_lama = User.objects.filter(pk=instance.pk).values(*KOLOM_PENGGUNA).first()


@receiver(post_save, sender=User, dispatch_uid="jejak_pengguna")
def pengguna_sesudah(sender, instance, created, **kwargs):
    if created:
        catat(A.PENGGUNA_DIBUAT, objek=instance, data={k: getattr(instance, k) for k in KOLOM_PENGGUNA + ["email"]})
        return
    lama = getattr(instance, "_jejak_lama", None)
    if not lama:
        return
    berubah = {k: {"dari": lama[k], "ke": getattr(instance, k)} for k in KOLOM_PENGGUNA if lama[k] != getattr(instance, k)}
    if berubah:
        catat(A.PERAN_DIUBAH, objek=instance, data=berubah)


# --- Audit: status, buka kunci, reset, dan semua tindakan yang tercatat di riwayat ------------

@receiver(post_save, sender=RiwayatStatus, dispatch_uid="jejak_riwayat_status")
def riwayat_status(sender, instance, created, **kwargs):
    if not created:
        return
    pindah = instance.dari != instance.ke
    catat(
        A.STATUS_AUDIT if pindah else A.CATATAN_AUDIT,
        objek=instance.audit, audit_id=instance.audit_id, aktor=instance.oleh,
        data={"dari": instance.dari, "ke": instance.ke}, alasan=instance.alasan,
    )


@receiver(post_save, sender=HasilPerhitungan, dispatch_uid="jejak_hasil")
def hasil_dihitung(sender, instance, **kwargs):
    catat(
        A.HASIL_DIHITUNG, objek=instance.audit, audit_id=instance.audit_id, aktor=instance.dihitung_oleh,
        data={
            "tahap": instance.tahap, "nilai_auditor": instance.nilai_auditor, "deviasi": instance.deviasi,
            "ne": instance.ne, "nk": instance.nk, "hasil_akhir": instance.hasil_akhir, "parameter": instance.parameter,
        },
    )


@receiver(tim_audit_disimpan, dispatch_uid="jejak_tim")
def tim_disimpan(sender, audit, **kwargs):
    tim = [
        {"email": p.pengguna.email, "peran": p.peran, "ketua": p.ketua}
        for p in audit.penugasan.select_related("pengguna")
    ]
    catat(A.TIM_DISIMPAN, objek=audit, audit_id=audit.pk, data={"tim": tim, "lingkup": [str(l) for l in audit.lingkup.all()]})


@receiver(pre_delete, sender=Audit, dispatch_uid="jejak_audit_dihapus")
def audit_dihapus(sender, instance, **kwargs):
    catat(A.AUDIT_DIHAPUS, objek=instance, audit_id=instance.pk, data={"unit": str(instance.unit), "periode": str(instance.periode)})


@receiver(ptk_diverifikasi, dispatch_uid="jejak_verifikasi_ptk")
def verifikasi_ptk(sender, ptk, audit_baru, **kwargs):
    catat(
        A.PTK_DIVERIFIKASI, objek=ptk, audit_id=ptk.audit_id, aktor=ptk.diverifikasi_oleh,
        data={"hasil": ptk.status, "diverifikasi_di_audit": audit_baru.pk}, alasan=ptk.catatan_verifikasi,
    )


# --- Pengaturan periode: parameter rumus Bab 6 -------------------------------------------------

@receiver(pre_save, sender=PengaturanPeriode, dispatch_uid="jejak_pengaturan_sebelum")
def pengaturan_sebelum(sender, instance, **kwargs):
    kolom = PengaturanPeriode.FIELD_PARAMETER + PengaturanPeriode.FIELD_LABEL
    instance._jejak_lama = PengaturanPeriode.objects.filter(pk=instance.pk).values(*kolom).first() if instance.pk else None


@receiver(post_save, sender=PengaturanPeriode, dispatch_uid="jejak_pengaturan")
def pengaturan_sesudah(sender, instance, created, **kwargs):
    kolom = PengaturanPeriode.FIELD_PARAMETER + PengaturanPeriode.FIELD_LABEL
    lama = getattr(instance, "_jejak_lama", None) or {}
    berubah = {
        k: {"dari": lama.get(k), "ke": getattr(instance, k)}
        for k in kolom
        if created or str(lama.get(k)) != str(getattr(instance, k))
    }
    if berubah:
        catat(A.PENGATURAN_DIUBAH, objek=instance, data={"periode": str(instance.periode), "baru": created, "kolom": berubah})
