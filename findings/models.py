from django.conf import settings
from django.db import models
from django.db.models import Q

from audits.models import Audit
from masterdata.models import PernyataanStandar, TujuanAudit


class Temuan(models.Model):
    """Temuan AMI (FR-33, BR-14). Kelebihan/KTS/OB dibuat otomatis dari kategori final."""

    class Jenis(models.TextChoices):
        KELEBIHAN = "KELEBIHAN", "Kelebihan"
        KTS = "KTS", "KTS (Ketidaksesuaian)"
        OB = "OB", "OB (Observasi)"
        PELUANG = "PELUANG", "Peluang Peningkatan"

    JENIS_PTK = frozenset({Jenis.KTS, Jenis.OB})

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="temuan", verbose_name="audit")
    jenis = models.CharField("jenis", max_length=10, choices=Jenis.choices)
    pernyataan = models.ForeignKey(
        PernyataanStandar, on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name="butir"
    )
    uraian = models.TextField("uraian temuan", blank=True)
    urutan = models.PositiveIntegerField("urutan", default=0)
    diubah_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    diubah_pada = models.DateTimeField("diubah pada", auto_now=True)

    class Meta:
        ordering = ["audit", "urutan", "id"]
        verbose_name = "temuan"
        verbose_name_plural = "temuan"
        constraints = [
            # Satu temuan otomatis per butir; Peluang Peningkatan boleh lebih dari satu.
            models.UniqueConstraint(
                fields=["audit", "pernyataan"],
                condition=~Q(jenis="PELUANG"),
                name="temuan_otomatis_unik_per_butir",
            ),
        ]

    def __str__(self):
        kode = f" {self.pernyataan.kode}" if self.pernyataan_id else ""
        return f"{self.get_jenis_display()}{kode}"

    @property
    def otomatis(self):
        return self.jenis != self.Jenis.PELUANG


class PTK(models.Model):
    """Permintaan Tindakan Koreksi, satu per temuan KTS/OB (FR-35, FR-36, BR-15)."""

    class Status(models.TextChoices):
        TERBUKA = "TERBUKA", "Terbuka"
        DIRENCANAKAN = "DIRENCANAKAN", "Rencana diisi"
        EFEKTIF = "EFEKTIF", "Terverifikasi efektif"
        TIDAK_EFEKTIF = "TIDAK_EFEKTIF", "Belum efektif"

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="ptk", verbose_name="audit")
    temuan = models.OneToOneField(Temuan, on_delete=models.CASCADE, related_name="ptk", verbose_name="temuan")
    nomor_urut = models.PositiveIntegerField("nomor urut")
    # Diisi modul documents dari pola nomor surat (FR-39).
    nomor_surat = models.CharField("nomor surat", max_length=100, blank=True)
    akar_masalah = models.TextField("akar masalah", blank=True)
    rencana_tindakan = models.TextField("rencana tindakan koreksi", blank=True)
    target_tanggal = models.DateField("target selesai", null=True, blank=True)
    pic = models.CharField("penanggung jawab (PIC)", max_length=200, blank=True)
    status = models.CharField("status", max_length=15, choices=Status.choices, default=Status.TERBUKA)
    rencana_dikirim_pada = models.DateTimeField("rencana dikirim pada", null=True, blank=True)
    realisasi = models.TextField("realisasi tindakan koreksi", blank=True)
    # FR-37: diverifikasi tim auditor audit periode berikutnya untuk unit yang sama.
    diverifikasi_di = models.ForeignKey(
        Audit, on_delete=models.SET_NULL, null=True, blank=True, related_name="ptk_diverifikasi",
        verbose_name="diverifikasi di audit",
    )
    diverifikasi_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    diverifikasi_pada = models.DateTimeField("diverifikasi pada", null=True, blank=True)
    catatan_verifikasi = models.TextField("catatan verifikasi", blank=True)
    diubah_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    diubah_pada = models.DateTimeField("diubah pada", auto_now=True)

    class Meta:
        ordering = ["audit", "nomor_urut"]
        verbose_name = "PTK"
        verbose_name_plural = "PTK"
        constraints = [
            models.UniqueConstraint(fields=["audit", "nomor_urut"], name="nomor_ptk_unik_per_audit"),
        ]

    def __str__(self):
        return self.kode

    @property
    def kode(self):
        return f"PTK No. {self.nomor_urut:03d}"

    @property
    def sudah_diverifikasi(self):
        return self.status in (self.Status.EFEKTIF, self.Status.TIDAK_EFEKTIF)

    @property
    def rencana_lengkap(self):
        return all([self.akar_masalah.strip(), self.rencana_tindakan.strip(), self.target_tanggal, self.pic.strip()])


class Kesimpulan(models.Model):
    """Kesimpulan A/B/C dan checklist Tujuan Audit a–f oleh ketua (FR-34, BR-12)."""

    audit = models.OneToOneField(Audit, on_delete=models.CASCADE, related_name="kesimpulan", verbose_name="audit")
    skor_a = models.PositiveSmallIntegerField("A. Sistem dokumentasi", null=True, blank=True)
    skor_b = models.PositiveSmallIntegerField("B. Implementasi SPMI", null=True, blank=True)
    skor_c = models.PositiveSmallIntegerField("C. Tindak lanjut PTK periode lalu", null=True, blank=True)
    c_tidak_berlaku = models.BooleanField(
        "C tidak berlaku", default=False, help_text="Unit belum memiliki PTK periode lalu; bobot C dibagi ke A dan B."
    )
    penjelasan_a = models.TextField("penjelasan A", blank=True)
    penjelasan_b = models.TextField("penjelasan B", blank=True)
    penjelasan_c = models.TextField("penjelasan C", blank=True)
    tujuan_tercapai = models.ManyToManyField(TujuanAudit, blank=True, related_name="+", verbose_name="tujuan audit tercapai")
    diubah_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    diubah_pada = models.DateTimeField("diubah pada", auto_now=True)

    class Meta:
        verbose_name = "kesimpulan"
        verbose_name_plural = "kesimpulan"

    def __str__(self):
        return f"Kesimpulan {self.audit}"

    @property
    def kurang(self):
        kurang = []
        if self.skor_a is None or not self.penjelasan_a.strip():
            kurang.append("Kesimpulan A")
        if self.skor_b is None or not self.penjelasan_b.strip():
            kurang.append("Kesimpulan B")
        if (self.skor_c is None and not self.c_tidak_berlaku) or not self.penjelasan_c.strip():
            kurang.append("Kesimpulan C")
        return kurang


class Persetujuan(models.Model):
    """Checklist persetujuan ketua lalu auditee, termasuk keberatan (FR-38, BR-18)."""

    class Pihak(models.TextChoices):
        KETUA = "KETUA", "Ketua auditor"
        AUDITEE = "AUDITEE", "Auditee"

    class Keputusan(models.TextChoices):
        SETUJU = "SETUJU", "Setuju"
        KEBERATAN = "KEBERATAN", "Keberatan"

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="persetujuan", verbose_name="audit")
    pihak = models.CharField("pihak", max_length=10, choices=Pihak.choices)
    oleh = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="oleh")
    keputusan = models.CharField("keputusan", max_length=10, choices=Keputusan.choices)
    checklist = models.JSONField("item checklist yang dicentang", default=list)
    keberatan = models.TextField("keberatan", blank=True)
    tanggapan = models.TextField("tanggapan ketua", blank=True)
    ditanggapi_pada = models.DateTimeField("ditanggapi pada", null=True, blank=True)
    waktu = models.DateTimeField("waktu", auto_now_add=True)

    class Meta:
        ordering = ["audit", "waktu", "id"]
        verbose_name = "persetujuan"
        verbose_name_plural = "persetujuan"

    def __str__(self):
        return f"{self.get_pihak_display()}: {self.get_keputusan_display()}"


class Usulan(models.Model):
    """Usulan anggota auditor untuk temuan (Bab 4: auditor "Usul", ketua memutuskan)."""

    class Jenis(models.TextChoices):
        PELUANG = "PELUANG", "Peluang Peningkatan"
        URAIAN = "URAIAN", "Uraian temuan"

    class Status(models.TextChoices):
        DIAJUKAN = "DIAJUKAN", "Diajukan"
        DITERIMA = "DITERIMA", "Diterima"
        DITOLAK = "DITOLAK", "Ditolak"

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="usulan", verbose_name="audit")
    oleh = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="pengusul")
    jenis = models.CharField("jenis", max_length=10, choices=Jenis.choices)
    temuan = models.ForeignKey(
        Temuan, on_delete=models.CASCADE, null=True, blank=True, related_name="usulan", verbose_name="temuan"
    )
    isi = models.TextField("isi usulan")
    status = models.CharField("status", max_length=10, choices=Status.choices, default=Status.DIAJUKAN)
    ditanggapi_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    waktu = models.DateTimeField("waktu", auto_now_add=True)

    class Meta:
        ordering = ["audit", "waktu", "id"]
        verbose_name = "usulan temuan"
        verbose_name_plural = "usulan temuan"

    def __str__(self):
        return f"{self.get_jenis_display()} dari {self.oleh}"
