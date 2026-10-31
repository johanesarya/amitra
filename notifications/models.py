from django.conf import settings
from django.db import models

from audits.models import Audit


class Notifikasi(models.Model):
    """Notifikasi in-app (FR-47)."""

    penerima = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifikasi", verbose_name="penerima"
    )
    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, null=True, blank=True, related_name="notifikasi")
    jenis = models.CharField("jenis", max_length=40)
    judul = models.CharField("judul", max_length=200)
    pesan = models.TextField("pesan", blank=True)
    tautan = models.CharField("tautan", max_length=500, blank=True)
    dibaca_pada = models.DateTimeField("dibaca pada", null=True, blank=True)
    dibuat_pada = models.DateTimeField("dibuat pada", auto_now_add=True)

    class Meta:
        ordering = ["-dibuat_pada", "-id"]
        verbose_name = "notifikasi"
        verbose_name_plural = "notifikasi"
        indexes = [models.Index(fields=["penerima", "dibaca_pada"], name="notif_penerima_dibaca")]

    def __str__(self):
        return self.judul


class KirimanEmail(models.Model):
    """Log setiap email; dikirim lewat antrean dengan coba ulang (NFR-04).

    `kunci` unik mencegah email ganda, mis. pengingat yang sama di hari yang sama.
    """

    class Status(models.TextChoices):
        DIANTRE = "DIANTRE", "Diantre"
        TERKIRIM = "TERKIRIM", "Terkirim"
        GAGAL = "GAGAL", "Gagal"

    penerima = models.EmailField("email penerima")
    pengguna = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    audit = models.ForeignKey(Audit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    jenis = models.CharField("jenis", max_length=40)
    subjek = models.CharField("subjek", max_length=250)
    isi_teks = models.TextField("isi teks")
    isi_html = models.TextField("isi HTML", blank=True)
    lampiran = models.JSONField("lampiran (id dokumen)", default=list, blank=True)
    kunci = models.CharField("kunci unik", max_length=200, unique=True, null=True, blank=True)
    status = models.CharField("status", max_length=10, choices=Status.choices, default=Status.DIANTRE)
    galat = models.TextField("pesan galat", blank=True)
    percobaan = models.PositiveSmallIntegerField("percobaan", default=0)
    dibuat_pada = models.DateTimeField("dibuat pada", auto_now_add=True)
    terkirim_pada = models.DateTimeField("terkirim pada", null=True, blank=True)

    class Meta:
        ordering = ["-dibuat_pada", "-id"]
        verbose_name = "kiriman email"
        verbose_name_plural = "kiriman email"

    def __str__(self):
        return f"{self.subjek} → {self.penerima}"
