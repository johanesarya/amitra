"""Tugas antrean: kirim email dan pengingat harian (FR-42, FR-46, NFR-04)."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from .layanan import beri_tahu
from .models import KirimanEmail, Notifikasi
from .tenggat import perlu_diingatkan


def kirim_email(kiriman_id):
    """Dijalankan worker. Galat dicatat lalu dilempar ulang agar antrean mencoba lagi."""
    k = KirimanEmail.objects.get(pk=kiriman_id)
    if k.status == KirimanEmail.Status.TERKIRIM:
        return k.pk  # idempoten bila tugas terulang
    msg = EmailMultiAlternatives(k.subjek, k.isi_teks, settings.DEFAULT_FROM_EMAIL, [k.penerima])
    if k.isi_html:
        msg.attach_alternative(k.isi_html, "text/html")
    try:
        if k.lampiran:
            from documents.models import Dokumen

            for d in Dokumen.objects.filter(pk__in=k.lampiran).select_related("audit__unit", "ptk"):
                if d.berkas:
                    with d.berkas.open("rb") as f:
                        msg.attach(f"{d.judul} - {d.audit.unit.kode}.pdf", f.read(), "application/pdf")
        msg.send()
    except Exception as e:
        KirimanEmail.objects.filter(pk=k.pk).update(
            status=KirimanEmail.Status.GAGAL, galat=str(e)[:2000], percobaan=k.percobaan + 1
        )
        raise
    KirimanEmail.objects.filter(pk=k.pk).update(
        status=KirimanEmail.Status.TERKIRIM, galat="", percobaan=k.percobaan + 1, terkirim_pada=timezone.now()
    )
    return k.pk


def kirim_pengingat_harian(hari_ini=None):
    """Dijadwalkan tiap pagi (lihat perintah pasang_jadwal). Satu notifikasi dan email per orang per tugas per hari."""
    hari_ini = hari_ini or timezone.localdate()
    jumlah = 0
    for user, t in perlu_diingatkan(hari_ini):
        jenis = f"PENGINGAT_{t.jenis}"
        if Notifikasi.objects.filter(penerima=user, audit=t.audit, jenis=jenis, dibuat_pada__date=hari_ini).exists():
            continue  # tugas terjalankan dua kali di hari yang sama
        beri_tahu(
            [user],
            jenis=jenis,
            judul=f"Pengingat: {t.label} {t.audit.unit} jatuh tempo {t.keterangan_sisa}",
            pesan=f"Batas {t.label.lower()} untuk {t.audit.unit} adalah {t.batas:%d-%m-%Y}. Mohon diselesaikan sebelum batas.",
            tautan=t.tautan,
            audit=t.audit,
            email=True,
            kunci=f"pengingat:{t.jenis}:{t.audit.pk}:{hari_ini:%Y%m%d}",
        )
        jumlah += 1
    return jumlah
