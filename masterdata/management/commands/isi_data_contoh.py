from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from documents.models import JENIS_BERNOMOR, JenisDokumen, PengaturanDokumen, PolaNomorSurat
from masterdata.models import KategoriSurat, TujuanAudit

# Teks CONTOH untuk development; LPM menggantinya lewat Administrasi → Tujuan Audit.
TUJUAN_CONTOH = [
    ("a", "[CONTOH] Memeriksa kesesuaian pelaksanaan SPMI unit dengan standar yang ditetapkan."),
    ("b", "[CONTOH] Mengevaluasi efektivitas pelaksanaan standar di unit."),
    ("c", "[CONTOH] Mengidentifikasi Kelebihan, KTS/OB, dan Peluang Peningkatan."),
    ("d", "[CONTOH] Memverifikasi tindak lanjut PTK periode sebelumnya."),
    ("e", "[CONTOH] Memberikan rekomendasi perbaikan berkelanjutan."),
    ("f", "[CONTOH] Menyiapkan unit menghadapi akreditasi dan audit eksternal."),
]


KATEGORI_CONTOH = [("Prodi A", "PA"), ("Prodi B", "PB"), ("Universitas", "UNIV")]
# Pola contoh per jenis harus berbeda: penghitung terpisah per pola.
POLA_CONTOH = {"PTK": "{nomor}/PTK/LPM/{kategori}/{bulan_romawi}/{tahun}", "BERITA_ACARA": "{nomor}/BA/LPM/{kategori}/{bulan_romawi}/{tahun}", "LAPORAN_AMI": "{nomor}/LAP/LPM/{kategori}/{bulan_romawi}/{tahun}"}
# Contoh nomor formulir dari BRD 8.2; selebihnya diisi LPM.
FORMULIR_CONTOH = {JenisDokumen.PROFIL_AUDITEE: "064-00/Unika/LPM/R-Q", JenisDokumen.DAFTAR_TILIK: "009-02"}


class Command(BaseCommand):
    help = "Isi data contoh untuk development (Tujuan Audit, kategori surat, pola nomor surat, nomor formulir). Tidak berjalan bila DEBUG=False."

    def add_arguments(self, parser):
        parser.add_argument("--paksa", action="store_true", help="Jalankan walau DEBUG=False (mis. staging).")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["paksa"]:
            raise CommandError("DEBUG=False. Data contoh tidak boleh masuk produksi; pakai --paksa hanya di staging.")
        dibuat = 0
        for urutan, (kode, teks) in enumerate(TUJUAN_CONTOH, start=1):
            _, baru = TujuanAudit.objects.get_or_create(kode=kode, defaults={"teks": teks, "urutan": urutan})
            dibuat += baru
        self.stdout.write(self.style.SUCCESS(f"Tujuan Audit contoh: {dibuat} dibuat, {len(TUJUAN_CONTOH) - dibuat} sudah ada."))

        for nama, kode in KATEGORI_CONTOH:
            KategoriSurat.objects.get_or_create(kode=kode, defaults={"nama": nama})
        for jenis in JENIS_BERNOMOR:
            PolaNomorSurat.objects.get_or_create(jenis=jenis, kategori=None, defaults={"pola": POLA_CONTOH[jenis]})
        for jenis in JenisDokumen:
            pengaturan = PengaturanDokumen.untuk(jenis)
            if not pengaturan.nomor_formulir and jenis in FORMULIR_CONTOH:
                pengaturan.nomor_formulir = FORMULIR_CONTOH[jenis]
                pengaturan.save(update_fields=["nomor_formulir"])
        self.stdout.write(self.style.SUCCESS("Kategori surat, pola nomor surat umum, dan nomor formulir contoh siap."))
