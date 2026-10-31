from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager, Group
from django.db import models
from django.utils import timezone

from .peran import GRUP_PERAN, PERAN_STAF, Peran


class PenggunaManager(BaseUserManager):
    use_in_migrations = True

    def _buat(self, email, password, **extra):
        if not email:
            raise ValueError("Email wajib diisi.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()  # login lewat Google
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_superuser", False)
        return self._buat(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_superuser", True)
        extra.setdefault("peran", Peran.MASTER_ADMIN)
        return self._buat(email, password, **extra)


class User(AbstractUser):
    """Pengguna SI-AMI; login dengan email kampus (FR-01).

    `is_staff`, `is_active`, dan keanggotaan grup diturunkan dari `peran`
    setiap kali disimpan, jadi jangan diubah langsung.
    """

    username = None
    first_name = None
    last_name = None

    email = models.EmailField("email", unique=True)
    nama = models.CharField("nama lengkap", max_length=200, blank=True)
    npp = models.CharField("NPP", max_length=30, unique=True, null=True, blank=True)
    telepon = models.CharField("telepon", max_length=30, blank=True)
    homebase = models.ForeignKey(
        "masterdata.Unit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pengguna_homebase",
        verbose_name="unit homebase",
    )
    unit_jabatan = models.ManyToManyField(
        "masterdata.Unit",
        blank=True,
        related_name="pejabat",
        verbose_name="unit tempat menjabat",
        help_text="Dipakai untuk mencegah auditor mengaudit unitnya sendiri (FR-14).",
    )
    peran = models.CharField("peran", max_length=20, choices=Peran.choices, default=Peran.MENUNGGU)
    akun_tamu = models.BooleanField(
        "akun tamu", default=False,
        help_text="FR-02: hanya akun tamu yang dapat masuk dengan email dan password. Akun kampus masuk lewat Google.",
    )

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = PenggunaManager()

    class Meta:
        ordering = ["nama", "email"]
        verbose_name = "pengguna"
        verbose_name_plural = "pengguna"
        permissions = [("tetapkan_peran", "Dapat menetapkan peran pengguna")]

    def __str__(self):
        return self.nama or self.email

    def get_full_name(self):
        return self.nama or self.email

    def get_short_name(self):
        return self.nama.split(" ")[0] if self.nama else self.email

    @property
    def menunggu_peran(self):
        return self.peran == Peran.MENUNGGU and not self.is_superuser

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        sinkron = update_fields is None or "peran" in update_fields
        if sinkron:
            self.email = (self.email or "").strip().lower()
            self.npp = self.npp or None
            self.is_staff = self.is_superuser or self.peran in PERAN_STAF
            self.is_active = self.peran != Peran.NONAKTIF
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "is_staff", "is_active"}
        super().save(*args, **kwargs)
        if sinkron:
            self._sinkronkan_grup()

    def _sinkronkan_grup(self):
        dikelola = Group.objects.filter(name__in=GRUP_PERAN.values())
        self.groups.remove(*dikelola)
        nama_grup = GRUP_PERAN.get(self.peran)
        if nama_grup:
            grup, _ = Group.objects.get_or_create(name=nama_grup)
            self.groups.add(grup)



class LogAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Log audit tidak dapat diubah.")

    def delete(self):
        raise ValueError("Log audit tidak dapat dihapus.")


class LogAudit(models.Model):
    """Audit log tak terhapus (NFR-10). Hanya bisa ditambah.

    Penolakan ubah/hapus ada di kode dan di trigger database (migrasi 0004).
    `hash_isi` dihitung saat ditulis; rantai hash dibuat tugas `segel` (SegelLog)
    agar penulisan tetap satu INSERT tanpa penguncian.
    """

    class Aksi(models.TextChoices):
        LOGIN = "LOGIN", "Login berhasil"
        LOGIN_GAGAL = "LOGIN_GAGAL", "Login gagal"
        LOGOUT = "LOGOUT", "Logout"
        PENGGUNA_DIBUAT = "PENGGUNA_DIBUAT", "Pengguna dibuat"
        PERAN_DIUBAH = "PERAN_DIUBAH", "Peran/status pengguna diubah"
        STATUS_AUDIT = "STATUS_AUDIT", "Status audit berpindah"
        CATATAN_AUDIT = "CATATAN_AUDIT", "Tindakan pada audit"
        SKOR_DIUBAH = "SKOR_DIUBAH", "Kategori penilaian diubah"
        KATEGORI_FINAL = "KATEGORI_FINAL", "Kategori final ditetapkan"
        HASIL_DIHITUNG = "HASIL_DIHITUNG", "Hasil perhitungan dibuat"
        PENGATURAN_DIUBAH = "PENGATURAN_DIUBAH", "Pengaturan periode diubah"
        TIM_DISIMPAN = "TIM_DISIMPAN", "Tim audit disimpan"
        AUDIT_DIHAPUS = "AUDIT_DIHAPUS", "Audit dihapus"
        NOMOR_DIKOREKSI = "NOMOR_DIKOREKSI", "Nomor surat dikoreksi"
        PTK_DIVERIFIKASI = "PTK_DIVERIFIKASI", "PTK diverifikasi"

    waktu = models.DateTimeField("waktu", default=timezone.now, db_index=True)
    aktor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name="aktor"
    )
    aktor_email = models.CharField("email aktor", max_length=254, blank=True)
    aksi = models.CharField("aksi", max_length=30, choices=Aksi.choices, db_index=True)
    objek_jenis = models.CharField("jenis objek", max_length=60, blank=True)
    objek_id = models.CharField("id objek", max_length=40, blank=True)
    objek_nama = models.CharField("objek", max_length=250, blank=True)
    audit_id = models.PositiveBigIntegerField("id audit", null=True, blank=True, db_index=True)
    data = models.JSONField("data", default=dict, blank=True)
    alasan = models.TextField("alasan", blank=True)
    ip = models.GenericIPAddressField("alamat IP", null=True, blank=True)
    peramban = models.CharField("peramban", max_length=250, blank=True)
    hash_isi = models.CharField("hash isi", max_length=64, editable=False)

    objects = LogAuditQuerySet.as_manager()

    class Meta:
        ordering = ["-waktu", "-id"]
        verbose_name = "log audit"
        verbose_name_plural = "log audit"
        permissions = [("ekspor_log", "Dapat mengekspor log audit")]

    def __str__(self):
        return f"{self.waktu:%d-%m-%Y %H:%M} {self.get_aksi_display()} — {self.aktor_email or 'sistem'}"

    def isi_kanonik(self):
        import json

        return json.dumps(
            {
                "waktu": self.waktu.isoformat(), "aktor": self.aktor_id, "aktor_email": self.aktor_email,
                "aksi": self.aksi, "objek_jenis": self.objek_jenis, "objek_id": self.objek_id,
                "objek_nama": self.objek_nama, "audit": self.audit_id, "data": self.data,
                "alasan": self.alasan, "ip": self.ip, "peramban": self.peramban,
            },
            sort_keys=True, ensure_ascii=False, default=str,
        )

    def hitung_hash(self):
        import hashlib

        return hashlib.sha256(self.isi_kanonik().encode()).hexdigest()

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Log audit tidak dapat diubah.")
        self.hash_isi = self.hitung_hash()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Log audit tidak dapat dihapus.")


class SegelLog(models.Model):
    """Rantai hash atas LogAudit, dibuat berkala (lihat accounts.jejak.segel); juga tak dapat diubah/dihapus."""

    log = models.OneToOneField(LogAudit, on_delete=models.PROTECT, related_name="segel")
    hash_rantai = models.CharField("hash rantai", max_length=64)
    disegel_pada = models.DateTimeField("disegel pada", auto_now_add=True)

    objects = LogAuditQuerySet.as_manager()

    class Meta:
        ordering = ["log_id"]
        verbose_name = "segel log"
        verbose_name_plural = "segel log"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Segel log tidak dapat diubah.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Segel log tidak dapat dihapus.")
