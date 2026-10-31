import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from masterdata.models import LingkupBidang, Periode, PernyataanStandar, TahapanPeriode, Unit


class Audit(models.Model):
    """Satu audit = satu unit dalam satu periode (BRD 8.1)."""

    class Status(models.TextChoices):
        # BRD 6.6
        BELUM_MULAI = "BELUM_MULAI", "Belum Mulai"
        PENGISIAN_SER = "PENGISIAN_SER", "Pengisian SER"
        PENILAIAN_AUDITOR = "PENILAIAN_AUDITOR", "Penilaian Auditor"
        REKONSILIASI = "REKONSILIASI", "Rekonsiliasi"
        PERLU_AUDIT_LAPANGAN = "PERLU_AUDIT_LAPANGAN", "Perlu Audit Lapangan"
        PERUMUSAN_TEMUAN = "PERUMUSAN_TEMUAN", "Perumusan Temuan"
        MENUNGGU_PERSETUJUAN = "MENUNGGU_PERSETUJUAN", "Menunggu Persetujuan Auditee"
        FINAL = "FINAL", "Final"
        TINDAK_LANJUT_PTK = "TINDAK_LANJUT_PTK", "Tindak Lanjut PTK"
        DITUTUP = "DITUTUP", "Ditutup"

    # Setelah penilaian dimulai, tim hanya bisa diubah lewat buka kunci Master Admin.
    STATUS_TIM_BISA_DIUBAH = frozenset({Status.BELUM_MULAI, Status.PENGISIAN_SER})
    STATUS_SER_TERBUKA = frozenset({Status.BELUM_MULAI, Status.PENGISIAN_SER})

    periode = models.ForeignKey(Periode, on_delete=models.PROTECT, related_name="audit", verbose_name="periode")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="audit", verbose_name="unit")
    lingkup = models.ManyToManyField(LingkupBidang, related_name="audit", verbose_name="lingkup bidang")
    status = models.CharField("status", max_length=30, choices=Status.choices, default=Status.BELUM_MULAI)
    jadwal_audit_lapangan = models.DateTimeField("jadwal Audit Lapangan", null=True, blank=True)
    dibuat_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="dibuat oleh",
    )
    dibuat_pada = models.DateTimeField("dibuat pada", auto_now_add=True)
    diubah_pada = models.DateTimeField("diubah pada", auto_now=True)
    ser_dikirim_pada = models.DateTimeField("SER dikirim pada", null=True, blank=True)
    batas_ser_khusus = models.DateField(
        "batas pengisian SER khusus", null=True, blank=True,
        help_text="Diisi Master Admin saat membuka kunci; menggantikan deadline periode untuk audit ini.",
    )
    # Audit Lapangan (FR-30, opsi b): butir yang dibuka lagi untuk direvisi auditor.
    revisi_al_dibuka = models.BooleanField("revisi pasca Audit Lapangan dibuka", default=False)
    butir_revisi_al = models.JSONField("butir revisi pasca Audit Lapangan", default=list, blank=True)
    catatan_follow_up = models.TextField("catatan follow-up Audit Lapangan", blank=True)

    class Meta:
        ordering = ["periode", "unit__tipe__urutan", "unit__nama"]
        verbose_name = "audit"
        verbose_name_plural = "audit"
        permissions = [
            ("buka_kunci_audit", "Dapat membuka kunci / mereset status audit"),
            ("lihat_analitik", "Dapat melihat rapor, grafik, dan tren lintas unit"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["periode", "unit"],
                name="audit_unik_per_unit_periode",
                violation_error_message="Unit ini sudah memiliki audit di periode tersebut.",
            ),
        ]

    def __str__(self):
        return f"{self.unit} — {self.periode}"

    @property
    def tim_bisa_diubah(self):
        return self.status in self.STATUS_TIM_BISA_DIUBAH

    @property
    def batas_ser(self):
        """Deadline auditee: batas khusus audit, atau tanggal selesai tahap Pengisian SER."""
        if self.batas_ser_khusus:
            return self.batas_ser_khusus
        tahap = self.periode.tahapan.filter(jenis=TahapanPeriode.Jenis.PENGISIAN_SER).first()
        return tahap.tanggal_selesai if tahap else None

    def ser_bisa_diisi(self):
        """Bab 4: auditee mengisi SER sampai deadline (s.d. 23.59 waktu lokal)."""
        batas = self.batas_ser
        return self.status in self.STATUS_SER_TERBUKA and (batas is None or timezone.localdate() <= batas)

    def _tim(self):
        # Pakai hasil prefetch bila ada.
        return list(self.penugasan.all())

    @property
    def auditee(self):
        return next((p.pengguna for p in self._tim() if p.peran == Penugasan.Peran.AUDITEE), None)

    @property
    def auditor(self):
        return [p.pengguna for p in self._tim() if p.peran == Penugasan.Peran.AUDITOR]

    @property
    def ketua(self):
        return next((p.pengguna for p in self._tim() if p.ketua), None)

    def pernyataan_berlaku(self):
        return PernyataanStandar.objects.berlaku_untuk(self.unit, self.periode, self.lingkup.all())

    def hasil_tahap(self, tahap):
        return self.hasil.filter(tahap=tahap).first()

    def hasil_terakhir(self):
        return self.hasil.order_by("-dihitung_pada", "-id").first()


class Penugasan(models.Model):
    """Peran seseorang dalam satu audit (FR-04, FR-13)."""

    class Peran(models.TextChoices):
        AUDITEE = "AUDITEE", "Auditee"
        AUDITOR = "AUDITOR", "Auditor"

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="penugasan", verbose_name="audit")
    pengguna = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="penugasan", verbose_name="pengguna"
    )
    peran = models.CharField("peran", max_length=10, choices=Peran.choices)
    ketua = models.BooleanField("ketua auditor", default=False)
    dikunci_pada = models.DateTimeField("penilaian dikunci pada", null=True, blank=True)

    class Meta:
        ordering = ["audit", "peran", "-ketua", "pengguna__nama"]
        verbose_name = "penugasan"
        verbose_name_plural = "penugasan"
        constraints = [
            models.UniqueConstraint(
                fields=["audit", "pengguna"],
                name="pengguna_sekali_per_audit",
                violation_error_message="Pengguna ini sudah ada di tim audit.",
            ),
            models.UniqueConstraint(
                fields=["audit"],
                condition=Q(peran="AUDITEE"),
                name="satu_auditee_per_audit",
                violation_error_message="Satu audit hanya memiliki satu auditee.",
            ),
            models.UniqueConstraint(
                fields=["audit"],
                condition=Q(ketua=True),
                name="satu_ketua_per_audit",
                violation_error_message="Satu audit hanya memiliki satu ketua auditor.",
            ),
            models.CheckConstraint(
                condition=Q(ketua=False) | Q(peran="AUDITOR"),
                name="ketua_harus_auditor",
                violation_error_message="Ketua harus berperan auditor.",
            ),
        ]

    def __str__(self):
        label = "Ketua auditor" if self.ketua else self.get_peran_display()
        return f"{label}: {self.pengguna}"


def lokasi_bukti(instance, filename):
    # Nama berkas asli hanya disimpan di field `nama`, tidak di path.
    audit_id = instance.jawaban.audit_id if instance.jawaban_id else instance.ptk.audit_id
    folder = "bukti" if instance.jawaban_id else "bukti-ptk"
    return f"{folder}/{audit_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class JawabanSER(models.Model):
    """Isian auditee per butir (FR-19). Tanpa skor (BR-01)."""

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="jawaban_ser", verbose_name="audit")
    pernyataan = models.ForeignKey(
        PernyataanStandar, on_delete=models.PROTECT, related_name="+", verbose_name="pernyataan standar"
    )
    penjelasan = models.TextField("hasil/penjelasan", blank=True)
    # Optimistic locking (NFR-05): setiap simpan menaikkan versi.
    versi = models.PositiveIntegerField("versi", default=1)
    diubah_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    diubah_pada = models.DateTimeField("diubah pada", auto_now=True)

    class Meta:
        ordering = ["audit", "pernyataan"]
        verbose_name = "jawaban SER"
        verbose_name_plural = "jawaban SER"
        constraints = [
            models.UniqueConstraint(fields=["audit", "pernyataan"], name="jawaban_ser_unik_per_butir"),
        ]

    def __str__(self):
        return f"{self.audit} — {self.pernyataan.kode}"

    @property
    def lengkap(self):
        """FR-22: penjelasan dan minimal satu bukti wajib (keputusan 31 Okt 2026)."""
        return bool(self.penjelasan.strip()) and len(self.bukti.all()) > 0


class Bukti(models.Model):
    """Bukti berupa tautan Google Drive atau berkas unggahan (FR-19)."""

    class Jenis(models.TextChoices):
        TAUTAN = "TAUTAN", "Tautan Google Drive"
        BERKAS = "BERKAS", "Berkas unggahan"

    jawaban = models.ForeignKey(
        JawabanSER, on_delete=models.CASCADE, null=True, blank=True, related_name="bukti", verbose_name="jawaban SER"
    )
    # Bukti tindak lanjut PTK (BRD 8.1: bukti milik Jawaban SER atau PTK).
    ptk = models.ForeignKey(
        "findings.PTK", on_delete=models.CASCADE, null=True, blank=True, related_name="bukti", verbose_name="PTK"
    )
    jenis = models.CharField("jenis", max_length=10, choices=Jenis.choices)
    url = models.URLField("tautan", max_length=1000, blank=True)
    berkas = models.FileField("berkas", upload_to=lokasi_bukti, blank=True, max_length=300)
    nama = models.CharField("nama", max_length=255)
    ukuran = models.PositiveBigIntegerField("ukuran (byte)", null=True, blank=True)
    diunggah_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    diunggah_pada = models.DateTimeField("diunggah pada", auto_now_add=True)

    class Meta:
        ordering = ["jawaban", "diunggah_pada"]
        verbose_name = "bukti"
        verbose_name_plural = "bukti"
        constraints = [
            models.CheckConstraint(
                condition=(Q(jenis="TAUTAN") & ~Q(url="") & Q(berkas=""))
                | (Q(jenis="BERKAS") & ~Q(berkas="") & Q(url="")),
                name="bukti_tautan_atau_berkas",
            ),
            models.CheckConstraint(
                condition=(Q(jawaban__isnull=False) & Q(ptk__isnull=True)) | (Q(jawaban__isnull=True) & Q(ptk__isnull=False)),
                name="bukti_milik_jawaban_atau_ptk",
            ),
        ]

    def __str__(self):
        return self.nama


class RiwayatStatus(models.Model):
    """Jejak perpindahan status audit, termasuk buka kunci beserta alasan (FR-23).

    Hanya bisa ditambah; baris yang sudah ada tidak bisa diubah atau dihapus.
    """

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="riwayat_status", verbose_name="audit")
    dari = models.CharField("dari status", max_length=30, choices=Audit.Status.choices)
    ke = models.CharField("ke status", max_length=30, choices=Audit.Status.choices)
    oleh = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    alasan = models.TextField("alasan", blank=True)
    waktu = models.DateTimeField("waktu", auto_now_add=True)

    class Meta:
        ordering = ["audit", "waktu", "id"]
        verbose_name = "riwayat status"
        verbose_name_plural = "riwayat status"

    def __str__(self):
        return f"{self.get_dari_display()} → {self.get_ke_display()}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Riwayat status tidak dapat diubah.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Riwayat status tidak dapat dihapus.")


class Penilaian(models.Model):
    """Penilaian satu auditor untuk satu butir (FR-26). Skor angka diambil dari skala Pengaturan."""

    class Kategori(models.TextChoices):
        # Nilai sama dengan scoring.parameter.Kategori.
        KTS = "KTS", "KTS (Ketidaksesuaian)"
        OB = "OB", "OB (Observasi)"
        SESUAI = "SESUAI", "Sesuai"
        PELAMPAUAN = "PELAMPAUAN", "Pelampauan"

    PERLU_KONDISI_FAKTUAL = frozenset({Kategori.KTS, Kategori.OB})

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="penilaian", verbose_name="audit")
    pernyataan = models.ForeignKey(PernyataanStandar, on_delete=models.PROTECT, related_name="+", verbose_name="butir")
    auditor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="auditor"
    )
    kategori = models.CharField("kategori", max_length=12, choices=Kategori.choices, blank=True)
    dasar_penilaian = models.TextField("dasar penilaian", blank=True)
    kondisi_faktual = models.TextField("kondisi faktual", blank=True)
    versi = models.PositiveIntegerField("versi", default=1)
    diubah_pada = models.DateTimeField("diubah pada", auto_now=True)

    class Meta:
        ordering = ["audit", "pernyataan", "auditor"]
        verbose_name = "penilaian"
        verbose_name_plural = "penilaian"
        constraints = [
            models.UniqueConstraint(
                fields=["audit", "pernyataan", "auditor"], name="penilaian_unik_per_auditor_butir"
            ),
        ]

    def __str__(self):
        return f"{self.pernyataan.kode} — {self.auditor}: {self.get_kategori_display() or 'belum dinilai'}"

    @property
    def kurang(self):
        """BR-02: kategori dan dasar penilaian wajib; kondisi faktual wajib untuk KTS/OB."""
        kurang = []
        if not self.kategori:
            kurang.append("kategori")
        if not self.dasar_penilaian.strip():
            kurang.append("dasar penilaian")
        if self.kategori in self.PERLU_KONDISI_FAKTUAL and not self.kondisi_faktual.strip():
            kurang.append("kondisi faktual")
        return kurang

    @property
    def lengkap(self):
        return not self.kurang


class KategoriFinal(models.Model):
    """Kategori per butir untuk audit (BR-03, BR-13; disepakati final di FR-32)."""

    class Cara(models.TextChoices):
        MAYORITAS = "MAYORITAS", "Mayoritas auditor"
        KETUA = "KETUA", "Ditetapkan ketua"
        TIDAK_BERLAKU = "TIDAK_BERLAKU", "Tidak berlaku"

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="kategori_final", verbose_name="audit")
    pernyataan = models.ForeignKey(PernyataanStandar, on_delete=models.PROTECT, related_name="+", verbose_name="butir")
    kategori = models.CharField("kategori", max_length=12, choices=Penilaian.Kategori.choices, blank=True)
    cara = models.CharField("cara penetapan", max_length=15, choices=Cara.choices)
    alasan = models.TextField("alasan", blank=True)
    ditetapkan_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    diubah_pada = models.DateTimeField("diubah pada", auto_now=True)

    class Meta:
        ordering = ["audit", "pernyataan"]
        verbose_name = "kategori final"
        verbose_name_plural = "kategori final"
        constraints = [
            models.UniqueConstraint(fields=["audit", "pernyataan"], name="kategori_final_unik_per_butir"),
        ]

    def __str__(self):
        return f"{self.pernyataan.kode}: {self.get_kategori_display() or self.get_cara_display()}"

    @property
    def tidak_berlaku(self):
        return self.cara == self.Cara.TIDAK_BERLAKU

    @property
    def seri(self):
        """Belum ada kategori terbanyak dan belum ditetapkan ketua."""
        return not self.tidak_berlaku and not self.kategori


class HasilPerhitungan(models.Model):
    """Hasil rumus Bab 6 beserta salinan parameter dan penilaian saat dihitung.

    BR-12: NE awal tetap tersimpan walau ada hasil setelah Audit Lapangan.
    """

    class Tahap(models.TextChoices):
        AWAL = "AWAL", "Awal (setelah semua auditor mengunci)"
        SETELAH_AL = "SETELAH_AL", "Setelah Audit Lapangan"
        FINAL = "FINAL", "Final (kategori final dan kesimpulan)"

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="hasil", verbose_name="audit")
    tahap = models.CharField("tahap", max_length=12, choices=Tahap.choices)
    nilai_auditor = models.JSONField("nilai per auditor")  # {id pengguna: "75.00"}
    rata_rata = models.DecimalField("rata-rata nilai auditor", max_digits=6, decimal_places=2)
    deviasi = models.DecimalField("deviasi (D)", max_digits=6, decimal_places=2)
    ne = models.DecimalField("nilai efektif (NE)", max_digits=6, decimal_places=2)
    memenuhi_kkm = models.BooleanField("memenuhi KKM")
    perlu_audit_lapangan = models.BooleanField("perlu Audit Lapangan")
    deviasi_tinggi = models.BooleanField("deviasi di atas ambang")
    jumlah_kts = models.PositiveIntegerField("jumlah KTS")
    jumlah_ob = models.PositiveIntegerField("jumlah OB")
    jumlah_kelebihan = models.PositiveIntegerField("jumlah Kelebihan")
    jumlah_butir = models.PositiveIntegerField("jumlah butir berlaku")
    nk = models.DecimalField("nilai kesimpulan (NK)", max_digits=6, decimal_places=2, null=True, blank=True)
    # Kosong selama proporsi NE/NK belum ditetapkan LPM (BRD 10.6).
    hasil_akhir = models.DecimalField("hasil akhir", max_digits=6, decimal_places=2, null=True, blank=True)
    parameter = models.JSONField("parameter saat dihitung")
    penilaian = models.JSONField("salinan penilaian")  # {id pengguna: {id butir: kategori}}
    dihitung_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    dihitung_pada = models.DateTimeField("dihitung pada", auto_now_add=True)

    class Meta:
        ordering = ["audit", "dihitung_pada"]
        verbose_name = "hasil perhitungan"
        verbose_name_plural = "hasil perhitungan"
        constraints = [
            models.UniqueConstraint(fields=["audit", "tahap"], name="hasil_unik_per_tahap"),
        ]

    def __str__(self):
        return f"{self.audit} — {self.get_tahap_display()}: NE {self.ne}"
