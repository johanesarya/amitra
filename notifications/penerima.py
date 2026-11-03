"""Siapa diberi tahu pada tiap peristiwa (FR-29, FR-42, FR-47). Tabel penerima disetujui 31 Okt 2026."""

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from accounts.models import User
from accounts.peran import Peran
from audits.models import Audit, Penugasan, RiwayatStatus
from audits.sinyal import batas_ser_diperpanjang, kunci_penilaian_direset, tim_audit_disimpan
from documents.sinyal import paket_final_siap
from findings.sinyal import ptk_diverifikasi

from .layanan import antre_email, beri_tahu, email_dari_template, url_penuh

S = Audit.Status
BATAS_LAMPIRAN = 15 * 1024 * 1024  # di atas ini email berisi tautan unduh saja


def _tim(audit):
    tim = list(audit.penugasan.select_related("pengguna"))
    return {
        "auditee": [p.pengguna for p in tim if p.peran == Penugasan.Peran.AUDITEE],
        "auditor": [p.pengguna for p in tim if p.peran == Penugasan.Peran.AUDITOR],
        "ketua": [p.pengguna for p in tim if p.ketua],
        "anggota": [p.pengguna for p in tim if p.peran == Penugasan.Peran.AUDITOR and not p.ketua],
    }


def _url(nama, audit):
    return reverse(nama, args=[audit.pk])


@receiver(tim_audit_disimpan, dispatch_uid="notif_diplot")
def diplot(sender, audit, **kwargs):
    t = _tim(audit)
    # `sekali`: saat tim diubah, hanya anggota baru yang diberi tahu.
    beri_tahu(
        t["auditee"], jenis="DIPLOT", audit=audit, sekali=True, email=True, kunci=f"diplot:{audit.pk}",
        judul=f"Anda ditugaskan sebagai auditee AMI {audit.unit}",
        pesan=f"{audit.periode}. Silakan isi SER sebelum batas pengisian.", tautan=_url("audits:detail", audit),
    )
    beri_tahu(
        t["auditor"], jenis="DIPLOT", audit=audit, sekali=True, email=True, kunci=f"diplot:{audit.pk}",
        judul=f"Anda ditugaskan sebagai auditor AMI {audit.unit}",
        pesan=f"{audit.periode}. Pernyataan standar unit sudah dapat dipelajari.", tautan=_url("audits:detail", audit),
    )


@receiver(post_save, sender=RiwayatStatus, dispatch_uid="notif_status")
def status_berubah(sender, instance, created, **kwargs):
    if not created or instance.dari == instance.ke:
        return
    audit = Audit.objects.select_related("unit", "periode__cp_lpm").get(pk=instance.audit_id)
    dari, ke = instance.dari, instance.ke
    t = _tim(audit)
    k = f"status:{audit.pk}:{instance.pk}"

    if ke == S.PENILAIAN_AUDITOR and dari == S.PENGISIAN_SER:
        beri_tahu(t["auditor"], jenis="SER_DIKIRIM", audit=audit, email=True, kunci=k,
                  judul=f"SER {audit.unit} siap dinilai", pesan="Auditee telah mengirim SER. Silakan mulai penilaian.",
                  tautan=_url("audits:penilaian", audit))
        beri_tahu(t["auditee"], jenis="SER_DIKIRIM", audit=audit, judul="SER Anda terkirim",
                  pesan="SER terkunci dan sedang dinilai auditor.", tautan=_url("audits:detail", audit))
        from findings.tindak_lanjut import ringkasan_verifikasi

        r = ringkasan_verifikasi(audit)
        if r["belum_diverifikasi"]:
            # FR-37: tim audit periode ini memverifikasi PTK periode lalu.
            beri_tahu(t["auditor"], jenis="PTK_LALU", audit=audit, email=True, kunci=f"ptk-lalu:{audit.pk}",
                      judul=f"{r['belum_diverifikasi']} PTK periode lalu {audit.unit} perlu diverifikasi",
                      pesan=f"PTK dari {r['audit_lalu'].periode} diverifikasi tim audit periode ini.",
                      tautan=_url("findings:verifikasi", audit))
    elif ke == S.PENILAIAN_AUDITOR and dari == S.REKONSILIASI:
        beri_tahu(t["auditor"], jenis="KUNCI_DIRESET", audit=audit, judul=f"Penilaian {audit.unit} dibuka kembali",
                  pesan=instance.alasan, tautan=_url("audits:penilaian", audit))
    elif ke == S.PENGISIAN_SER and dari == S.PENILAIAN_AUDITOR:
        beri_tahu(t["auditee"], jenis="SER_DIBUKA", audit=audit, email=True, kunci=k,
                  judul=f"SER {audit.unit} dibuka kembali", pesan=instance.alasan, tautan=_url("audits:ser", audit))
        beri_tahu(t["auditor"], jenis="SER_DIBUKA", audit=audit, judul=f"SER {audit.unit} dibuka kembali",
                  pesan="Auditee memperbaiki SER; kunci penilaian Anda direset.", tautan=_url("audits:detail", audit))
    elif ke == S.REKONSILIASI:
        # Rekonsiliasi bisa langsung berlanjut di transaksi yang sama; beri tahu hanya bila masih tertahan butir seri.
        pk = audit.pk
        transaction.on_commit(lambda: _bila_masih_rekonsiliasi(pk))
    elif ke == S.PERLU_AUDIT_LAPANGAN:
        # FR-29: ketua, CP LPM periode, dan Master Admin (keputusan 31 Okt 2026).
        penerima = t["ketua"] + [audit.periode.cp_lpm] + list(User.objects.filter(peran=Peran.MASTER_ADMIN))
        beri_tahu(penerima, jenis="PERLU_AL", audit=audit, email=True, kunci=k,
                  judul=f"Perlu Audit Lapangan: {audit.unit}", pesan=instance.alasan,
                  tautan=_url("audits:audit_lapangan", audit))
    elif ke == S.PERUMUSAN_TEMUAN and dari == S.MENUNGGU_PERSETUJUAN:
        beri_tahu(t["ketua"], jenis="KEBERATAN", audit=audit, email=True, kunci=k,
                  judul=f"Auditee {audit.unit} mengajukan keberatan",
                  pesan="Tanggapi keberatan secara tertulis sebelum meneruskan ulang.", tautan=_url("findings:perumusan", audit))
    elif ke == S.PERUMUSAN_TEMUAN:
        beri_tahu(t["ketua"], jenis="PERUMUSAN", audit=audit, email=True, kunci=k,
                  judul=f"Rumuskan temuan {audit.unit}", pesan=instance.alasan, tautan=_url("findings:perumusan", audit))
        beri_tahu(t["anggota"], jenis="PERUMUSAN", audit=audit, judul=f"Perumusan temuan {audit.unit} dimulai",
                  pesan="Anda dapat mengirim usulan kepada ketua.", tautan=_url("findings:perumusan", audit))
    elif ke == S.MENUNGGU_PERSETUJUAN:
        beri_tahu(t["auditee"], jenis="MENUNGGU_PERSETUJUAN", audit=audit, email=True, kunci=k,
                  judul=f"Hasil AMI {audit.unit} menunggu persetujuan Anda",
                  pesan="Tinjau temuan dan kesimpulan, lalu setujui atau ajukan keberatan.",
                  tautan=_url("findings:persetujuan", audit))
    elif ke == S.DITUTUP:
        beri_tahu(t["auditee"], jenis="DITUTUP", audit=audit, judul=f"Audit {audit.unit} {audit.periode} ditutup",
                  pesan=instance.alasan, tautan=_url("findings:ptk", audit))
    elif ke == S.FINAL:
        # Email berisi PDF dikirim saat dokumen siap (paket_final_siap).
        beri_tahu(t["auditee"] + t["auditor"], jenis="FINAL", audit=audit, judul=f"Hasil AMI {audit.unit} Final",
                  pesan="Dokumen resmi sedang dibuat dan akan dikirim lewat email.", tautan=_url("findings:persetujuan", audit))


def _bila_masih_rekonsiliasi(audit_pk):
    audit = Audit.objects.select_related("unit").get(pk=audit_pk)
    if audit.status != S.REKONSILIASI:
        return
    beri_tahu(_tim(audit)["ketua"], jenis="REKONSILIASI", audit=audit, email=True, kunci=f"rekonsiliasi:{audit.pk}:{audit.diubah_pada:%Y%m%d%H%M%S}",
              judul=f"Tetapkan kategori butir seri {audit.unit}",
              pesan="Ada butir tanpa satu kategori terbanyak; ketua perlu menetapkannya.",
              tautan=_url("audits:rekonsiliasi", audit))


@receiver(batas_ser_diperpanjang, dispatch_uid="notif_perpanjangan")
def perpanjangan(sender, audit, alasan, **kwargs):
    audit.refresh_from_db()
    beri_tahu(_tim(audit)["auditee"], jenis="PERPANJANGAN_SER", audit=audit, email=True,
              kunci=f"perpanjangan:{audit.pk}:{audit.batas_ser}",
              judul=f"Batas SER {audit.unit} diperpanjang",
              pesan=f"Batas baru: {audit.batas_ser:%d-%m-%Y}. {alasan}" if audit.batas_ser else alasan,
              tautan=_url("audits:ser", audit))


@receiver(kunci_penilaian_direset, dispatch_uid="notif_reset_kunci")
def reset_kunci(sender, audit, penugasan, alasan, **kwargs):
    beri_tahu([penugasan.pengguna], jenis="KUNCI_DIRESET", audit=audit, email=True,
              judul=f"Kunci penilaian Anda di {audit.unit} direset", pesan=alasan, tautan=_url("audits:penilaian", audit))


@receiver(paket_final_siap, dispatch_uid="notif_paket_final")
def kirim_paket_final(sender, audit, **kwargs):
    """FR-42: PDF final ke auditee dan semua auditor, sekali saja."""
    from documents.models import Dokumen, JenisDokumen

    dokumen = list(
        audit.dokumen.filter(jenis__in=[JenisDokumen.LAPORAN_AMI, JenisDokumen.PTK], status=Dokumen.Status.SIAP)
        .select_related("ptk")
    )
    total = sum(d.berkas.size for d in dokumen if d.berkas)
    lampiran = [d.pk for d in dokumen] if total <= BATAS_LAMPIRAN else []
    tautan = url_penuh(reverse("documents:daftar", args=[audit.pk]))
    t = _tim(audit)
    for user in {u.pk: u for u in t["auditee"] + t["auditor"]}.values():
        teks, html = email_dari_template(
            "final", {"pengguna": user, "audit": audit, "dokumen": dokumen, "dilampirkan": bool(lampiran), "tautan": tautan}
        )
        antre_email(
            penerima=user.email, pengguna=user, audit=audit, jenis="FINAL_PDF",
            subjek=f"[AMITRA] Dokumen final AMI {audit.unit} — {audit.periode}",
            isi_teks=teks, isi_html=html, kunci=f"final:{audit.pk}:{user.pk}", lampiran=lampiran,
        )


@receiver(ptk_diverifikasi, dispatch_uid="notif_ptk_diverifikasi")
def ptk_terverifikasi(sender, ptk, audit_baru, **kwargs):
    """Hasil verifikasi untuk auditee audit lama dan auditee audit baru (unit yang sama)."""
    lama = ptk.audit
    penerima = _tim(lama)["auditee"] + _tim(audit_baru)["auditee"]
    beri_tahu(penerima, jenis="PTK_DIVERIFIKASI", audit=lama, email=True,
              kunci=f"verifikasi:{ptk.pk}:{ptk.status}:{ptk.diverifikasi_pada:%Y%m%d%H%M%S}",
              judul=f"{ptk.kode} {lama.unit}: {ptk.get_status_display().lower()}",
              pesan=ptk.catatan_verifikasi, tautan=_url("findings:ptk", lama))
