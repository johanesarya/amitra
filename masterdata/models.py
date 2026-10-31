from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models, transaction
from django.db.models import F, Q

from scoring.parameter import Kategori, ParameterPenilaian


class TipeUnit(models.Model):
    """Tipe unit (FR-06, FR-08). Barisnya diisi lewat migrasi 0002."""

    FAKULTAS = "FAKULTAS"
    PRODI_S1 = "PRODI_S1"
    PRODI_S2 = "PRODI_S2"
    PRODI_S3 = "PRODI_S3"
    PRODI_PROFESI = "PRODI_PROFESI"
    LEMBAGA = "LEMBAGA"
    BIRO = "BIRO"
    UPT = "UPT"
    TIPE_PRODI = frozenset({PRODI_S1, PRODI_S2, PRODI_S3, PRODI_PROFESI})

    kode = models.CharField("kode", max_length=20, primary_key=True)
    nama = models.CharField("nama", max_length=50, unique=True)
    urutan = models.PositiveSmallIntegerField("urutan", default=0)

    class Meta:
        ordering = ["urutan"]
        verbose_name = "tipe unit"
        verbose_name_plural = "tipe unit"

    def __str__(self):
        return self.nama

    @property
    def adalah_prodi(self):
        return self.kode in self.TIPE_PRODI


class KategoriSurat(models.Model):
    """Kategori unit untuk pola nomor surat, mis. Prodi A, Prodi B, Universitas (FR-39).

    Dikelola Master Admin dan ditetapkan per unit.
    """

    nama = models.CharField("nama", max_length=100, unique=True)
    kode = models.CharField("kode", max_length=20, unique=True, help_text="Dipakai pada isian {kategori} di pola nomor surat.")

    class Meta:
        ordering = ["nama"]
        verbose_name = "kategori surat"
        verbose_name_plural = "kategori surat"

    def __str__(self):
        return self.nama


class Unit(models.Model):
    """Unit yang diaudit (FR-06)."""

    nama = models.CharField("nama unit", max_length=200)
    kode = models.CharField("kode", max_length=30, unique=True)
    tipe = models.ForeignKey(TipeUnit, on_delete=models.PROTECT, related_name="unit", verbose_name="tipe")
    induk = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sub_unit",
        verbose_name="fakultas induk",
        help_text="Wajib untuk prodi; kosongkan untuk unit lain.",
    )
    nama_pimpinan = models.CharField("nama pimpinan", max_length=200, blank=True)
    npp_pimpinan = models.CharField("NPP pimpinan", max_length=30, blank=True)
    kategori_surat = models.ForeignKey(
        KategoriSurat, on_delete=models.PROTECT, null=True, blank=True, related_name="unit",
        verbose_name="kategori surat", help_text="Menentukan pola nomor surat dokumen unit ini.",
    )
    aktif = models.BooleanField("aktif", default=True)

    class Meta:
        ordering = ["tipe__urutan", "nama"]
        verbose_name = "unit"
        verbose_name_plural = "unit"

    def __str__(self):
        return self.nama

    def clean(self):
        if not self.tipe_id:
            return
        if self.tipe_id in TipeUnit.TIPE_PRODI:
            if not self.induk_id:
                raise ValidationError({"induk": "Prodi wajib memiliki fakultas induk."})
            if self.induk.tipe_id != TipeUnit.FAKULTAS:
                raise ValidationError({"induk": "Induk prodi harus unit bertipe Fakultas."})
        elif self.induk_id:
            raise ValidationError({"induk": "Hanya prodi yang memiliki fakultas induk."})


class Periode(models.Model):
    """Periode AMI (FR-05). Hanya satu periode yang boleh aktif."""

    nama = models.CharField("nama periode", max_length=100)
    tahun_akademik = models.CharField("tahun akademik", max_length=9, help_text="Contoh: 2025/2026")
    aktif = models.BooleanField("aktif", default=False)
    cp_lpm = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="CP LPM",
        help_text="Ditampilkan ke ketua dan Admin saat audit perlu Audit Lapangan (BR-08).",
    )

    class Meta:
        ordering = ["-tahun_akademik", "-id"]
        verbose_name = "periode"
        verbose_name_plural = "periode"
        constraints = [
            models.UniqueConstraint(
                fields=["aktif"],
                condition=Q(aktif=True),
                name="satu_periode_aktif",
                violation_error_message="Sudah ada periode aktif. Gunakan aksi \"Aktifkan periode\".",
            ),
        ]

    def __str__(self):
        return f"{self.nama} ({self.tahun_akademik})"

    @transaction.atomic
    def aktifkan(self):
        Periode.objects.filter(aktif=True).exclude(pk=self.pk).update(aktif=False)
        self.aktif = True
        self.save(update_fields=["aktif"])

    def parameter(self):
        return self.pengaturan.ke_parameter()


class TahapanPeriode(models.Model):
    """Tahapan bertanggal per periode (FR-05). Tanggal diatur saat membuat jadwal."""

    class Jenis(models.TextChoices):
        PENGISIAN_SER = "PENGISIAN_SER", "Pengisian SER"
        REVIEW_AUDITOR = "REVIEW_AUDITOR", "Review Auditor"
        AUDIT_LAPANGAN = "AUDIT_LAPANGAN", "Audit Lapangan"
        FINALISASI = "FINALISASI", "Finalisasi"
        TINDAK_LANJUT_PTK = "TINDAK_LANJUT_PTK", "Tindak Lanjut PTK"

    periode = models.ForeignKey(Periode, on_delete=models.CASCADE, related_name="tahapan", verbose_name="periode")
    jenis = models.CharField("tahap", max_length=30, choices=Jenis.choices)
    tanggal_mulai = models.DateField("tanggal mulai")
    tanggal_selesai = models.DateField("tanggal selesai (deadline)")

    class Meta:
        ordering = ["periode", "tanggal_mulai"]
        verbose_name = "tahapan periode"
        verbose_name_plural = "tahapan periode"
        constraints = [
            models.UniqueConstraint(
                fields=["periode", "jenis"],
                name="tahapan_unik_per_periode",
                violation_error_message="Tahap ini sudah ada di periode tersebut.",
            ),
            models.CheckConstraint(
                condition=Q(tanggal_selesai__gte=F("tanggal_mulai")),
                name="tahapan_selesai_setelah_mulai",
                violation_error_message="Tanggal selesai tidak boleh sebelum tanggal mulai.",
            ),
        ]

    def __str__(self):
        return f"{self.get_jenis_display()}: {self.tanggal_mulai:%d-%m-%Y} s.d. {self.tanggal_selesai:%d-%m-%Y}"


class PengaturanPeriode(models.Model):
    """Parameter rumus Bab 6 per periode (FR-12, BR-12a).

    Nilai awal field = keputusan klien 31 Okt 2026 (BRD 10.6); periode baru
    menyalin pengaturan periode sebelumnya lewat `nilai_awal()`.
    """

    periode = models.OneToOneField(Periode, on_delete=models.CASCADE, related_name="pengaturan", verbose_name="periode")

    skor_kts = models.PositiveSmallIntegerField("skor KTS", default=1)
    skor_ob = models.PositiveSmallIntegerField("skor OB", default=2)
    skor_sesuai = models.PositiveSmallIntegerField("skor Sesuai", default=3)
    skor_pelampauan = models.PositiveSmallIntegerField("skor Pelampauan", default=4)

    kkm = models.DecimalField("KKM", max_digits=5, decimal_places=2, default=Decimal("75"))
    ambang_deviasi = models.DecimalField("ambang deviasi", max_digits=5, decimal_places=2, default=Decimal("10"))
    minimal_auditor = models.PositiveSmallIntegerField("minimal auditor", default=3)

    penyesuaian_kts = models.DecimalField(
        "penyesuaian per KTS", max_digits=5, decimal_places=2, default=Decimal("-0.50"),
        help_text="Bertanda: negatif mengurangi nilai efektif.",
    )
    penyesuaian_ob = models.DecimalField(
        "penyesuaian per OB", max_digits=5, decimal_places=2, default=Decimal("-0.30"),
        help_text="Bertanda: negatif mengurangi nilai efektif.",
    )
    penyesuaian_kelebihan = models.DecimalField(
        "penyesuaian per Kelebihan", max_digits=5, decimal_places=2, default=Decimal("0.25"),
        help_text="Bertanda: positif menambah nilai efektif.",
    )

    bobot_a = models.DecimalField("bobot Kesimpulan A (%)", max_digits=5, decimal_places=2, default=Decimal("60"))
    bobot_b = models.DecimalField("bobot Kesimpulan B (%)", max_digits=5, decimal_places=2, default=Decimal("30"))
    bobot_c = models.DecimalField("bobot Kesimpulan C (%)", max_digits=5, decimal_places=2, default=Decimal("10"))

    # BRD 10.6: proporsi NE/NK masih menunggu keputusan LPM.
    proporsi_ne = models.DecimalField(
        "proporsi NE dalam hasil akhir (%)", max_digits=5, decimal_places=2, null=True, blank=True
    )
    proporsi_nk = models.DecimalField(
        "proporsi NK dalam hasil akhir (%)", max_digits=5, decimal_places=2, null=True, blank=True
    )

    # Label opsi baku Kesimpulan A/B/C untuk skor 1–4 (FR-34; usulan BR-12, dapat diganti LPM).
    label_kesimpulan_1 = models.CharField("label skor 1", max_length=50, default="Kurang")
    label_kesimpulan_2 = models.CharField("label skor 2", max_length=50, default="Cukup")
    label_kesimpulan_3 = models.CharField("label skor 3", max_length=50, default="Baik")
    label_kesimpulan_4 = models.CharField("label skor 4", max_length=50, default="Sangat Baik")

    FIELD_LABEL = ["label_kesimpulan_1", "label_kesimpulan_2", "label_kesimpulan_3", "label_kesimpulan_4"]

    FIELD_PARAMETER = [
        "skor_kts", "skor_ob", "skor_sesuai", "skor_pelampauan",
        "kkm", "ambang_deviasi", "minimal_auditor",
        "penyesuaian_kts", "penyesuaian_ob", "penyesuaian_kelebihan",
        "bobot_a", "bobot_b", "bobot_c", "proporsi_ne", "proporsi_nk",
    ]

    class Meta:
        verbose_name = "pengaturan periode"
        verbose_name_plural = "pengaturan periode"

    def __str__(self):
        return f"Pengaturan {self.periode}"

    def ke_parameter(self):
        return ParameterPenilaian(
            skor_kategori={
                Kategori.KTS: self.skor_kts,
                Kategori.OB: self.skor_ob,
                Kategori.SESUAI: self.skor_sesuai,
                Kategori.PELAMPAUAN: self.skor_pelampauan,
            },
            kkm=self.kkm,
            ambang_deviasi=self.ambang_deviasi,
            minimal_auditor=self.minimal_auditor,
            penyesuaian_kts=self.penyesuaian_kts,
            penyesuaian_ob=self.penyesuaian_ob,
            penyesuaian_kelebihan=self.penyesuaian_kelebihan,
            bobot_a=self.bobot_a,
            bobot_b=self.bobot_b,
            bobot_c=self.bobot_c,
            proporsi_ne=self.proporsi_ne,
            proporsi_nk=self.proporsi_nk,
        )

    def clean(self):
        if any(getattr(self, f) is None for f in self.FIELD_PARAMETER if not f.startswith("proporsi")):
            return  # field kosong sudah dilaporkan validasi field
        try:
            self.ke_parameter()
        except ValueError as e:
            raise ValidationError(str(e)) from e

    @classmethod
    def nilai_awal(cls, kecuali_periode=None):
        """Nilai pengaturan periode terakhir, atau nilai awal field bila belum ada."""
        terakhir = cls.objects.order_by("-periode__tahun_akademik", "-periode_id")
        if kecuali_periode is not None:
            terakhir = terakhir.exclude(periode=kecuali_periode)
        terakhir = terakhir.first()
        kolom = cls.FIELD_PARAMETER + cls.FIELD_LABEL
        if terakhir is None:
            return {f: cls._meta.get_field(f).get_default() for f in kolom}
        return {f: getattr(terakhir, f) for f in kolom}

    def opsi_kesimpulan(self):
        """[(skor, label)] untuk Kesimpulan A/B/C, mengikuti skala penilaian periode."""
        skala = sorted({self.skor_kts, self.skor_ob, self.skor_sesuai, self.skor_pelampauan})
        label = [getattr(self, f) for f in self.FIELD_LABEL]
        return list(zip(skala, label))

    @classmethod
    def pastikan_ada(cls, periode):
        pengaturan, _ = cls.objects.get_or_create(
            periode=periode, defaults=cls.nilai_awal(kecuali_periode=periode)
        )
        return pengaturan


UKURAN_LOGO_MAKS = 2 * 1024 * 1024


def validasi_ukuran_logo(berkas):
    if berkas.size > UKURAN_LOGO_MAKS:
        raise ValidationError("Ukuran logo maksimal 2 MB.")


class PengaturanInstitusi(models.Model):
    """Identitas institusi untuk kop dokumen (FR-12). Hanya satu baris."""

    nama_institusi = models.CharField("nama institusi", max_length=200, blank=True)
    logo = models.FileField(
        "logo",
        upload_to="institusi/",
        blank=True,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg"]), validasi_ukuran_logo],
        help_text="PNG atau JPG, maksimal 2 MB.",
    )
    kop = models.TextField("teks kop", blank=True, help_text="Baris alamat dan kontak di kop dokumen.")

    class Meta:
        verbose_name = "pengaturan institusi"
        verbose_name_plural = "pengaturan institusi"

    def __str__(self):
        return self.nama_institusi or "Pengaturan institusi"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def muat(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class TujuanAudit(models.Model):
    """Tujuan Audit a–f di Laporan AMI (FR-34); teks diisi LPM lewat Administrasi."""

    kode = models.CharField("kode", max_length=5, unique=True, help_text="Contoh: a")
    teks = models.TextField("tujuan")
    urutan = models.PositiveSmallIntegerField("urutan", default=0)
    aktif = models.BooleanField("aktif", default=True)

    class Meta:
        ordering = ["urutan", "kode"]
        verbose_name = "tujuan audit"
        verbose_name_plural = "tujuan audit"

    def __str__(self):
        return f"{self.kode}. {self.teks[:60]}"


class LingkupBidang(models.Model):
    """Lingkup bidang standar; dipilih saat membuat audit (FR-13, FR-18)."""

    nama = models.CharField("nama", max_length=100, unique=True)
    urutan = models.PositiveSmallIntegerField("urutan", default=0)

    class Meta:
        ordering = ["urutan", "nama"]
        verbose_name = "lingkup bidang"
        verbose_name_plural = "lingkup bidang"

    def __str__(self):
        return self.nama


class Standar(models.Model):
    """Standar per periode (FR-07, FR-10)."""

    class Sumber(models.TextChoices):
        LPM = "LPM", "Standar LPM"
        TURUNAN = "TURUNAN", "Standar turunan unit"

    class Status(models.TextChoices):
        DIAJUKAN = "DIAJUKAN", "Diajukan"
        DISETUJUI = "DISETUJUI", "Disetujui"
        DITOLAK = "DITOLAK", "Ditolak"

    periode = models.ForeignKey(Periode, on_delete=models.CASCADE, related_name="standar", verbose_name="periode")
    kode = models.CharField("kode", max_length=30)
    nama = models.CharField("nama standar", max_length=300)
    lingkup = models.ForeignKey(LingkupBidang, on_delete=models.PROTECT, related_name="standar", verbose_name="lingkup bidang")
    bobot = models.DecimalField(
        "bobot", max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Hanya disimpan; tidak dipakai di rumus Bab 6.",
    )
    urutan = models.PositiveIntegerField("urutan", default=0)
    sumber = models.CharField("sumber", max_length=10, choices=Sumber.choices, default=Sumber.LPM)
    unit_pengusul = models.ForeignKey(
        Unit, on_delete=models.PROTECT, null=True, blank=True, related_name="standar_turunan",
        verbose_name="unit pengusul", help_text="Wajib untuk standar turunan.",
    )
    status = models.CharField("status", max_length=10, choices=Status.choices, default=Status.DISETUJUI)

    class Meta:
        ordering = ["periode", "urutan", "kode"]
        verbose_name = "standar"
        verbose_name_plural = "standar"
        constraints = [
            models.UniqueConstraint(
                fields=["periode", "kode"],
                name="kode_standar_unik_per_periode",
                violation_error_message="Kode standar sudah dipakai di periode ini.",
            ),
        ]

    def __str__(self):
        return f"{self.kode} {self.nama}"

    def clean(self):
        if self.sumber == self.Sumber.TURUNAN and not self.unit_pengusul_id:
            raise ValidationError({"unit_pengusul": "Standar turunan wajib memiliki unit pengusul."})
        if self.sumber == self.Sumber.LPM and self.unit_pengusul_id:
            raise ValidationError({"unit_pengusul": "Standar LPM tidak memiliki unit pengusul."})


class PernyataanStandarQuerySet(models.QuerySet):
    def berlaku_untuk(self, unit, periode, lingkup=None):
        """FR-18: butir aktif yang berlaku bagi tipe unit dan lingkup audit.

        Standar turunan hanya berlaku bagi unit pengusul dan prodi di bawahnya.
        """
        pengusul = [unit.pk] + ([unit.induk_id] if unit.induk_id else [])
        qs = self.filter(
            aktif=True,
            tipe_unit=unit.tipe_id,
            standar__periode=periode,
            standar__status=Standar.Status.DISETUJUI,
        ).filter(Q(standar__sumber=Standar.Sumber.LPM) | Q(standar__unit_pengusul__in=pengusul))
        if lingkup is not None:
            qs = qs.filter(standar__lingkup__in=lingkup)
        return qs.select_related("standar").order_by("standar__urutan", "standar__kode", "urutan", "kode")


class PernyataanStandar(models.Model):
    """Butir pernyataan standar (FR-07, FR-08)."""

    standar = models.ForeignKey(Standar, on_delete=models.CASCADE, related_name="pernyataan", verbose_name="standar")
    kode = models.CharField("kode", max_length=30, help_text="Contoh: 2.4*")
    pernyataan = models.TextField("pernyataan standar")
    pertanyaan_panduan = models.TextField("pertanyaan panduan", blank=True)
    tipe_unit = models.ManyToManyField(TipeUnit, related_name="pernyataan_standar", verbose_name="berlaku untuk tipe unit")
    urutan = models.PositiveIntegerField("urutan", default=0)
    aktif = models.BooleanField("aktif", default=True)
    asal = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salinan",
        verbose_name="butir asal (periode lalu)",
        help_text="Diisi otomatis saat standar disalin; menghubungkan butir yang sama antarperiode (FR-21, BR-17).",
    )

    objects = PernyataanStandarQuerySet.as_manager()

    class Meta:
        ordering = ["standar", "urutan", "kode"]
        verbose_name = "pernyataan standar"
        verbose_name_plural = "pernyataan standar"
        constraints = [
            models.UniqueConstraint(
                fields=["standar", "kode"],
                name="kode_pernyataan_unik_per_standar",
                violation_error_message="Kode pernyataan sudah dipakai di standar ini.",
            ),
        ]

    def __str__(self):
        return f"{self.kode} {self.pernyataan[:60]}"
