import string
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from audits.models import Audit
from masterdata.models import KategoriSurat


class JenisDokumen(models.TextChoices):
    """Dokumen keluaran (BRD 8.2, FR-40)."""

    PROFIL_AUDITEE = "PROFIL_AUDITEE", "Profil Auditee"
    DAFTAR_TILIK = "DAFTAR_TILIK", "Daftar Tilik"
    TEMUAN = "TEMUAN", "Temuan AMI"
    PTK = "PTK", "PTK"
    BERITA_ACARA = "BERITA_ACARA", "Berita Acara Audit Lapangan"
    LAPORAN_AMI = "LAPORAN_AMI", "Laporan AMI"


# Keputusan 31 Okt 2026: hanya dokumen ini yang bernomor surat.
JENIS_BERNOMOR = frozenset({JenisDokumen.PTK, JenisDokumen.BERITA_ACARA, JenisDokumen.LAPORAN_AMI})

ISIAN_POLA = {
    "nomor": "nomor urut 3 digit (001, 002, …), direset tiap tahun kalender",
    "bulan_romawi": "bulan terbit dalam angka Romawi (I–XII)",
    "bulan": "bulan terbit 2 digit",
    "tahun": "tahun terbit 4 digit",
    "kode_unit": "kode unit yang diaudit",
    "kode_fakultas": "kode fakultas induk (atau kode unit bila bukan prodi)",
    "kategori": "kode kategori surat unit",
}


def periksa_pola(pola):
    try:
        isian = {nama for _, nama, _, _ in string.Formatter().parse(pola) if nama is not None}
    except ValueError as e:
        raise ValidationError(f"Pola tidak valid: {e}") from e
    asing = isian - set(ISIAN_POLA)
    if asing:
        raise ValidationError(f"Isian tidak dikenal: {', '.join('{' + a + '}' for a in sorted(asing))}.")
    if "nomor" not in isian:
        raise ValidationError("Pola wajib memuat {nomor}.")


class PolaNomorSurat(models.Model):
    """Pola nomor surat per jenis dokumen dan kategori unit (FR-39). Kategori kosong = pola umum."""

    jenis = models.CharField("jenis dokumen", max_length=20, choices=[(j.value, j.label) for j in JenisDokumen if j in JENIS_BERNOMOR])
    kategori = models.ForeignKey(
        KategoriSurat, on_delete=models.PROTECT, null=True, blank=True, related_name="pola",
        verbose_name="kategori surat", help_text="Kosongkan untuk pola umum bagi unit tanpa pola khusus.",
    )
    pola = models.CharField(
        "pola", max_length=200, validators=[periksa_pola],
        help_text="Isian: " + "; ".join(f"{{{k}}} = {v}" for k, v in ISIAN_POLA.items()),
    )

    class Meta:
        ordering = ["jenis", "kategori__nama"]
        verbose_name = "pola nomor surat"
        verbose_name_plural = "pola nomor surat"
        constraints = [
            models.UniqueConstraint(fields=["jenis", "kategori"], name="pola_unik_per_jenis_kategori"),
            models.UniqueConstraint(fields=["jenis"], condition=Q(kategori__isnull=True), name="satu_pola_umum_per_jenis"),
        ]

    def __str__(self):
        return f"{self.get_jenis_display()} · {self.kategori or 'umum'}: {self.pola}"

    def clean(self):
        # Penghitung terpisah per pola: pola identik untuk jenis lain pasti menghasilkan nomor kembar.
        kembar = PolaNomorSurat.objects.filter(pola=self.pola, kategori=self.kategori).exclude(jenis=self.jenis)
        if self.pk:
            kembar = kembar.exclude(pk=self.pk)
        if kembar.exists():
            raise ValidationError({"pola": "Pola sama dengan pola jenis dokumen lain; tambahkan pembeda, mis. PTK atau LAP."})


class PenghitungNomor(models.Model):
    """Nomor urut terakhir per pola per tahun kalender (FR-39: urut terpisah per pola)."""

    pola = models.ForeignKey(PolaNomorSurat, on_delete=models.CASCADE, related_name="penghitung")
    tahun = models.PositiveSmallIntegerField("tahun")
    terakhir = models.PositiveIntegerField("nomor terakhir", default=0)

    class Meta:
        verbose_name = "penghitung nomor"
        verbose_name_plural = "penghitung nomor"
        constraints = [models.UniqueConstraint(fields=["pola", "tahun"], name="penghitung_unik_per_pola_tahun")]


class NomorSurat(models.Model):
    """Setiap nomor surat yang pernah diterbitkan. Nomor batal tidak dipakai ulang."""

    class Status(models.TextChoices):
        AKTIF = "AKTIF", "Aktif"
        BATAL = "BATAL", "Batal"

    audit = models.ForeignKey(Audit, on_delete=models.PROTECT, related_name="nomor_surat", verbose_name="audit")
    jenis = models.CharField("jenis dokumen", max_length=20, choices=JenisDokumen.choices)
    ptk = models.ForeignKey(
        "findings.PTK", on_delete=models.SET_NULL, null=True, blank=True, related_name="nomor_surat_set", verbose_name="PTK"
    )
    pola = models.ForeignKey(PolaNomorSurat, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    tahun = models.PositiveSmallIntegerField("tahun")
    nomor_urut = models.PositiveIntegerField("nomor urut", null=True, blank=True)
    teks = models.CharField("nomor surat", max_length=200)
    status = models.CharField("status", max_length=10, choices=Status.choices, default=Status.AKTIF)
    dikoreksi_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    alasan_koreksi = models.TextField("alasan koreksi", blank=True)
    dibuat_pada = models.DateTimeField("diterbitkan pada", auto_now_add=True)

    class Meta:
        ordering = ["audit", "jenis", "dibuat_pada"]
        verbose_name = "nomor surat"
        verbose_name_plural = "nomor surat"
        constraints = [
            models.UniqueConstraint(
                fields=["teks"], condition=Q(status="AKTIF"), name="nomor_surat_aktif_unik",
                violation_error_message="Nomor surat ini sudah dipakai.",
            ),
        ]

    def __str__(self):
        return self.teks


class PengaturanDokumen(models.Model):
    """Judul dan nomor formulir LPM per jenis dokumen (BRD 8.2), diatur lewat Administrasi."""

    jenis = models.CharField("jenis dokumen", max_length=20, choices=JenisDokumen.choices, unique=True)
    judul = models.CharField("judul dokumen", max_length=200)
    nomor_formulir = models.CharField("nomor formulir LPM", max_length=100, blank=True, help_text="Contoh: 064-00/Unika/LPM/R-Q")

    class Meta:
        ordering = ["jenis"]
        verbose_name = "pengaturan dokumen"
        verbose_name_plural = "pengaturan dokumen"

    def __str__(self):
        return self.judul

    @classmethod
    def untuk(cls, jenis):
        obj, _ = cls.objects.get_or_create(jenis=jenis, defaults={"judul": JenisDokumen(jenis).label})
        return obj


def lokasi_dokumen(instance, filename):
    return f"dokumen/{instance.audit_id}/{uuid.uuid4().hex}{filename[filename.rfind('.'):].lower()}"


class Dokumen(models.Model):
    """Dokumen PDF (dan Excel untuk Daftar Tilik) yang dibuat di antrean (FR-40, FR-41, FR-43)."""

    class Status(models.TextChoices):
        DIANTRE = "DIANTRE", "Diantre"
        DIPROSES = "DIPROSES", "Diproses"
        SIAP = "SIAP", "Siap"
        GAGAL = "GAGAL", "Gagal"

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="dokumen", verbose_name="audit")
    jenis = models.CharField("jenis", max_length=20, choices=JenisDokumen.choices)
    ptk = models.ForeignKey("findings.PTK", on_delete=models.CASCADE, null=True, blank=True, related_name="dokumen")
    berkas = models.FileField("PDF", upload_to=lokasi_dokumen, blank=True, max_length=300)
    berkas_excel = models.FileField("Excel", upload_to=lokasi_dokumen, blank=True, max_length=300)
    status = models.CharField("status", max_length=10, choices=Status.choices, default=Status.DIANTRE)
    galat = models.TextField("pesan galat", blank=True)
    versi = models.PositiveIntegerField("versi", default=0)
    diminta_pada = models.DateTimeField("diminta pada", null=True, blank=True)
    selesai_pada = models.DateTimeField("selesai pada", null=True, blank=True)
    scan = models.FileField("scan bertanda tangan", upload_to=lokasi_dokumen, blank=True, max_length=300)
    scan_oleh = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    scan_pada = models.DateTimeField("scan diunggah pada", null=True, blank=True)

    class Meta:
        ordering = ["audit", "jenis", "ptk__nomor_urut"]
        verbose_name = "dokumen"
        verbose_name_plural = "dokumen"
        constraints = [
            models.UniqueConstraint(fields=["audit", "jenis"], condition=Q(ptk__isnull=True), name="dokumen_unik_per_jenis"),
            models.UniqueConstraint(fields=["ptk"], condition=Q(ptk__isnull=False), name="dokumen_unik_per_ptk"),
        ]

    def __str__(self):
        return f"{self.judul} — {self.audit}"

    @property
    def judul(self):
        label = JenisDokumen(self.jenis).label
        return f"{label} {self.ptk.kode}" if self.ptk_id else label

    @property
    def sedang_dibuat(self):
        return self.status in (self.Status.DIANTRE, self.Status.DIPROSES)

    def nomor_aktif(self):
        qs = self.audit.nomor_surat.filter(jenis=self.jenis, status=NomorSurat.Status.AKTIF)
        if self.ptk_id:
            qs = qs.filter(ptk_id=self.ptk_id)
        return qs.first()


def lokasi_ekspor(instance, filename):
    return f"ekspor/{instance.diminta_oleh_id}/{uuid.uuid4().hex}{filename[filename.rfind('.'):].lower()}"


class Ekspor(models.Model):
    """Rapor, rekap periode, dan data mentah yang dibuat di antrean (FR-44, FR-48, FR-51, NFR-03)."""

    class Jenis(models.TextChoices):
        RAPOR = "RAPOR", "Rapor"
        REKAP_PERIODE = "REKAP_PERIODE", "Rekap periode"
        DATA_AUDIT = "DATA_AUDIT", "Data mentah audit"
        DATA_PERIODE = "DATA_PERIODE", "Data mentah periode"
        LOG = "LOG", "Log audit"

    jenis = models.CharField("jenis", max_length=20, choices=Jenis.choices)
    judul = models.CharField("judul", max_length=250)
    parameter = models.JSONField("parameter", default=dict)
    diminta_oleh = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ekspor")
    status = models.CharField("status", max_length=10, choices=Dokumen.Status.choices, default=Dokumen.Status.DIANTRE)
    berkas = models.FileField("Excel", upload_to=lokasi_ekspor, blank=True, max_length=300)
    berkas_pdf = models.FileField("PDF", upload_to=lokasi_ekspor, blank=True, max_length=300)
    galat = models.TextField("pesan galat", blank=True)
    diminta_pada = models.DateTimeField("diminta pada", auto_now_add=True)
    selesai_pada = models.DateTimeField("selesai pada", null=True, blank=True)

    class Meta:
        ordering = ["-diminta_pada", "-id"]
        verbose_name = "ekspor"
        verbose_name_plural = "ekspor"

    def __str__(self):
        return self.judul

    @property
    def sedang_dibuat(self):
        return self.status in (Dokumen.Status.DIANTRE, Dokumen.Status.DIPROSES)
