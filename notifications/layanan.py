"""Membuat notifikasi in-app dan mengantrekan email (FR-47, NFR-04). Email tidak pernah dikirim di request web."""

from django.conf import settings
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django_q.tasks import async_task

from .models import KirimanEmail, Notifikasi


def url_penuh(tautan):
    if not tautan or tautan.startswith("http"):
        return tautan
    return settings.SITUS_URL.rstrip("/") + tautan


def antre_email(*, penerima, subjek, isi_teks, isi_html="", jenis, pengguna=None, audit=None, kunci=None, lampiran=()):
    """Catat email lalu kirim lewat antrean setelah transaksi tersimpan. Kunci yang sama tidak dikirim dua kali."""
    if kunci and KirimanEmail.objects.filter(kunci=kunci).exists():
        return None
    try:
        with transaction.atomic():
            kiriman = KirimanEmail.objects.create(
                penerima=penerima, pengguna=pengguna, audit=audit, jenis=jenis, subjek=subjek[:250],
                isi_teks=isi_teks, isi_html=isi_html, kunci=kunci, lampiran=list(lampiran),
            )
    except IntegrityError:
        return None  # kunci sudah dipakai oleh proses lain bersamaan
    pk = kiriman.pk
    transaction.on_commit(lambda: async_task("notifications.tugas.kirim_email", pk, task_name=f"email-{pk}"))
    return kiriman


def email_dari_template(nama, konteks):
    """Render subjek/teks/HTML dari notifications/email/<nama>.{txt,html}."""
    konteks = {"situs": settings.SITUS_URL, **konteks}
    return (
        render_to_string(f"notifications/email/{nama}.txt", konteks).strip(),
        render_to_string(f"notifications/email/{nama}.html", konteks).strip(),
    )


def beri_tahu(penerima, *, jenis, judul, pesan="", tautan="", audit=None, email=False, kunci=None, sekali=False):
    """Notifikasi in-app untuk setiap penerima unik, dan email bila diminta.

    `sekali=True`: lewati penerima yang sudah punya notifikasi jenis ini untuk audit ini.
    `kunci`: dasar kunci email unik; ditambah id pengguna.
    """
    hasil = []
    sudah = set()
    if sekali and audit is not None:
        sudah = set(Notifikasi.objects.filter(audit=audit, jenis=jenis).values_list("penerima_id", flat=True))
    for user in {u.pk: u for u in penerima if u is not None and u.is_active}.values():
        if user.pk in sudah:
            continue
        hasil.append(Notifikasi.objects.create(penerima=user, audit=audit, jenis=jenis, judul=judul, pesan=pesan, tautan=tautan))
        if email and user.email:
            teks, html = email_dari_template(
                "umum", {"pengguna": user, "judul": judul, "pesan": pesan, "tautan": url_penuh(tautan), "audit": audit}
            )
            antre_email(
                penerima=user.email, pengguna=user, audit=audit, jenis=jenis, subjek=f"[AMITRA] {judul}",
                isi_teks=teks, isi_html=html, kunci=f"{kunci}:{user.pk}" if kunci else None,
            )
    return hasil
