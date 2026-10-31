"""Data demo satu siklus AMI untuk mencoba semua halaman di development (NFR-15).

Semua data dibuat lewat layanan aplikasi (plot, SER, penilaian, temuan, PTK), sehingga
status, hasil perhitungan, notifikasi, dan audit log sama seperti pemakaian sebenarnya.
Tidak berjalan bila DEBUG=False kecuali dengan --paksa (staging).
"""

from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from accounts.peran import Peran
from audits import penilaian, ser
from audits.layanan import simpan_audit
from audits.models import Audit
from findings import layanan as temuan
from findings import tindak_lanjut
from masterdata.models import (
    KategoriSurat,
    LingkupBidang,
    PengaturanInstitusi,
    PengaturanPeriode,
    Periode,
    PernyataanStandar,
    Standar,
    TahapanPeriode,
    TipeUnit,
    Unit,
)
from masterdata.salin import salin_standar

PASSWORD = "demo-siami-2026"
DOMAIN = "demo.local"
TAUTAN = "https://drive.google.com/file/d/contoh-bukti/view"
SKOR = {1: "KTS", 2: "OB", 3: "SESUAI", 4: "PELAMPAUAN"}
URAIAN = {
    "KELEBIHAN": "Pelaksanaan butir {kode} melampaui standar: dokumen lengkap, dievaluasi rutin, dan hasilnya dipublikasikan.",
    "KTS": "Dokumen pendukung butir {kode} tidak tersedia dan pelaksanaannya belum dapat dibuktikan.",
    "OB": "Pelaksanaan butir {kode} sudah berjalan, tetapi dokumen pendukungnya belum lengkap.",
}
T = TipeUnit

STANDAR = [
    ("1", "Standar Kompetensi Lulusan", "Pendidikan", [
        ("1.1", "Prodi memiliki profil lulusan yang terdokumentasi dan ditinjau berkala.", [T.PRODI_S1, T.PRODI_S2, T.FAKULTAS]),
        ("1.2", "Capaian pembelajaran lulusan dirumuskan sesuai KKNI.", [T.PRODI_S1, T.PRODI_S2]),
        ("1.3", "Tracer study dilaksanakan setiap tahun dan hasilnya ditindaklanjuti.", [T.PRODI_S1, T.PRODI_S2, T.FAKULTAS]),
    ]),
    ("2", "Standar Proses Pembelajaran", "Pendidikan", [
        ("2.1", "RPS tersedia untuk setiap mata kuliah dan dievaluasi tiap semester.", [T.PRODI_S1, T.PRODI_S2]),
        ("2.2", "Monitoring kehadiran dosen dan mahasiswa dilakukan secara berkala.", [T.PRODI_S1, T.PRODI_S2, T.FAKULTAS]),
    ]),
    ("3", "Standar Tata Kelola", "Tata Kelola", [
        ("3.1", "Unit memiliki rencana kerja tahunan yang selaras dengan renstra.", [T.FAKULTAS, T.BIRO]),
        ("3.2", "Laporan kinerja tahunan disusun dan dipublikasikan.", [T.FAKULTAS, T.BIRO]),
        ("3.3", "SOP layanan utama tersedia dan disosialisasikan.", [T.BIRO]),
    ]),
]


class Command(BaseCommand):
    help = "Isi data demo satu siklus AMI (semua peran, berbagai status). Hanya untuk development/staging."

    def add_arguments(self, parser):
        parser.add_argument("--paksa", action="store_true", help="Jalankan walau DEBUG=False (staging).")
        parser.add_argument("--tanpa-dokumen", action="store_true", help="Lewati pembuatan PDF/Excel dokumen demo.")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["paksa"]:
            raise CommandError("DEBUG=False. Data demo tidak boleh masuk produksi; pakai --paksa hanya di staging.")
        if User.objects.filter(email=f"master@{DOMAIN}").exists():
            # Audit log tak terhapus membuat data demo tidak bisa dihapus; isi ulang butuh database baru.
            self.stdout.write(self.style.WARNING("Data demo sudah ada; hanya dokumen yang belum Siap yang dibuat ulang."))
        else:
            call_command("isi_data_contoh", paksa=True, stdout=self.stdout)
            with transaction.atomic():
                self._isi()
        if not options["tanpa_dokumen"]:
            self._buat_dokumen()
        self._ringkas()

    def _buat_dokumen(self):
        """Buat dokumen demo langsung (perintah ini bukan request web), agar tidak bergantung pada qcluster."""
        from documents.models import Dokumen
        from documents.tugas import buat_dokumen

        siap, gagal = 0, []
        for d in Dokumen.objects.filter(audit__unit__kode__startswith="DEMO-").exclude(status=Dokumen.Status.SIAP):
            try:
                buat_dokumen(d.pk)
                siap += 1
            except Exception as e:  # dicatat di Dokumen.galat oleh buat_dokumen
                gagal.append(str(e))
        self.stdout.write(self.style.SUCCESS(f"Dokumen demo dibuat: {siap}."))
        if gagal:
            self.stdout.write(self.style.ERROR(f"{len(gagal)} dokumen gagal: {gagal[0]}"))

    # --- bantuan -----------------------------------------------------------------------

    def _pengguna(self, kode, nama, peran=Peran.PENGGUNA, homebase=None, jabatan=None):
        # Demo masuk dengan password; akun asli masuk lewat Google.
        u = User.objects.create_user(f"{kode}@{DOMAIN}", password=PASSWORD, nama=nama, peran=peran, homebase=homebase, akun_tamu=True)
        if jabatan:
            u.unit_jabatan.add(jabatan)
        return u

    def _tahapan(self, periode, ser_selesai):
        for jenis, mulai, selesai in [
            (TahapanPeriode.Jenis.PENGISIAN_SER, -14, 0),
            (TahapanPeriode.Jenis.REVIEW_AUDITOR, 1, 10),
            (TahapanPeriode.Jenis.AUDIT_LAPANGAN, 11, 15),
            (TahapanPeriode.Jenis.FINALISASI, 16, 25),
            (TahapanPeriode.Jenis.TINDAK_LANJUT_PTK, 26, 120),
        ]:
            TahapanPeriode.objects.create(
                periode=periode, jenis=jenis,
                tanggal_mulai=ser_selesai + timedelta(days=mulai), tanggal_selesai=ser_selesai + timedelta(days=selesai),
            )

    def _isi_ser(self, audit, auditee, jumlah=None, kirim=True):
        audit = Audit.objects.get(pk=audit.pk)
        ser.pastikan_jawaban(audit)
        for i, b in enumerate(audit.pernyataan_berlaku()):
            if jumlah is not None and i >= jumlah:
                break
            j = audit.jawaban_ser.get(pernyataan=b)
            ser.simpan_penjelasan(audit, b.pk, f"Pelaksanaan butir {b.kode} dijelaskan pada dokumen bukti terlampir beserta notulen rapat unit.", j.versi, auditee)
            ser.tambah_tautan(audit, b.pk, TAUTAN, auditee, nama=f"Bukti butir {b.kode}")
        if kirim:
            ser.kirim(Audit.objects.get(pk=audit.pk), auditee)
        return Audit.objects.get(pk=audit.pk)

    def _nilai(self, audit, skor_per_auditor, kunci=True):
        audit = Audit.objects.get(pk=audit.pk)
        butir = list(audit.pernyataan_berlaku())
        for t, skor in zip(penilaian.tim_auditor(audit), skor_per_auditor):
            penilaian.pastikan_penilaian(audit, t.pengguna)
            for b, s in zip(butir, skor):
                if s is None:
                    continue
                p = audit.penilaian.get(auditor=t.pengguna, pernyataan=b)
                kondisi = f"Bukti butir {b.kode} belum lengkap." if s in (1, 2) else ""
                penilaian.simpan_penilaian(audit, t, b.pk, SKOR[s], f"Sesuai dokumen dan wawancara butir {b.kode}.", kondisi, p.versi)
            if kunci and None not in skor:
                t.refresh_from_db()
                penilaian.kunci(Audit.objects.get(pk=audit.pk), t, t.pengguna)
        return Audit.objects.get(pk=audit.pk)

    def _rumuskan(self, audit, ajukan=True, setujui=False):
        audit = Audit.objects.get(pk=audit.pk)
        ketua = audit.penugasan.get(ketua=True)
        temuan.sinkron_temuan(audit)
        for t in audit.temuan.select_related("pernyataan"):
            temuan.simpan_uraian(audit, ketua, t, URAIAN[t.jenis].format(kode=t.pernyataan.kode))
        temuan.tambah_peluang(audit, ketua, "Digitalisasi arsip dokumen mutu agar mudah ditelusuri.")
        from masterdata.models import TujuanAudit

        temuan.simpan_kesimpulan(
            audit, ketua,
            {"skor_a": 3, "skor_b": 3, "skor_c": 2, "penjelasan_a": "Dokumen SPMI lengkap.",
             "penjelasan_b": "Implementasi berjalan, sebagian belum terdokumentasi.", "penjelasan_c": "Tindak lanjut PTK lalu sebagian."},
            list(TujuanAudit.objects.values_list("pk", flat=True)),
        )
        if ajukan:
            temuan.ajukan_ke_auditee(audit, ketua, {k for k, _ in temuan.CHECKLIST_KETUA})
        if setujui:
            auditee = Audit.objects.get(pk=audit.pk).penugasan.get(peran="AUDITEE")
            temuan.setujui(Audit.objects.get(pk=audit.pk), auditee, {k for k, _ in temuan.CHECKLIST_AUDITEE})
        return Audit.objects.get(pk=audit.pk)

    # --- data --------------------------------------------------------------------------

    def _isi(self):
        hari_ini = timezone.localdate()
        institusi = PengaturanInstitusi.muat()
        if not institusi.nama_institusi:
            institusi.nama_institusi = "Universitas Demo SI-AMI"
            institusi.kop = "Jl. Contoh No. 1, Kota Demo · lpm@demo.local"
            institusi.save()

        lingkup = {n: LingkupBidang.objects.get_or_create(nama=n, defaults={"urutan": i})[0] for i, n in enumerate(["Pendidikan", "Tata Kelola"])}
        ft = Unit.objects.create(nama="Fakultas Teknik (Demo)", kode="DEMO-FT", tipe_id=T.FAKULTAS, nama_pimpinan="Dekan Demo")
        fh = Unit.objects.create(nama="Fakultas Hukum (Demo)", kode="DEMO-FH", tipe_id=T.FAKULTAS, nama_pimpinan="Dekan FH Demo")
        te = Unit.objects.create(nama="Teknik Elektro (Demo)", kode="DEMO-TE", tipe_id=T.PRODI_S1, induk=ft, nama_pimpinan="Kaprodi TE")
        ts = Unit.objects.create(nama="Teknik Sipil (Demo)", kode="DEMO-TS", tipe_id=T.PRODI_S1, induk=ft, nama_pimpinan="Kaprodi TS")
        mt = Unit.objects.create(nama="Magister Teknik (Demo)", kode="DEMO-MT", tipe_id=T.PRODI_S2, induk=ft, nama_pimpinan="Kaprodi MT")
        ih = Unit.objects.create(nama="Ilmu Hukum (Demo)", kode="DEMO-IH", tipe_id=T.PRODI_S1, induk=fh, nama_pimpinan="Kaprodi IH")
        biro = Unit.objects.create(nama="Biro Akademik (Demo)", kode="DEMO-BAK", tipe_id=T.BIRO, nama_pimpinan="Kepala Biro Akademik")
        # Kategori surat agar nomor surat demo lengkap, mis. 001/PTK/LPM/PA/X/2026 (FR-39).
        kategori = {k.kode: k for k in KategoriSurat.objects.all()}
        for unit, kode in ((te, "PA"), (ts, "PB"), (mt, "PA"), (ih, "PA"), (ft, "UNIV"), (fh, "UNIV"), (biro, "UNIV")):
            unit.kategori_surat = kategori.get(kode)
            unit.save(update_fields=["kategori_surat"])

        master = self._pengguna("master", "Kepala LPM (Demo)", Peran.MASTER_ADMIN)
        admin = self._pengguna("admin", "Staf LPM (Demo)", Peran.ADMIN)
        self._pengguna("rektor", "Rektorat (Demo)", Peran.VIEWER)
        auditee = {
            u: self._pengguna(f"kaprodi.{u.kode[5:].lower()}", f"Pimpinan {u.nama}", homebase=u, jabatan=u)
            for u in (ft, te, ts, mt, ih, biro)
        }
        # Pimpinan TE periode lalu berbeda (riwayat berbasis unit, FR-24).
        kaprodi_lama = self._pengguna("kaprodi.te.lama", "Kaprodi TE Periode Lalu", homebase=te)
        # Homebase di luar unit yang mereka audit (FR-14); Dosen 4 ber-homebase Biro dan tidak mengaudit Biro.
        dosen = [self._pengguna(f"dosen{i}", f"Dosen Auditor {i}", homebase=biro if i == 4 else fh) for i in range(1, 8)]

        lalu = Periode.objects.create(nama="AMI Demo", tahun_akademik="2024/2025", cp_lpm=admin)
        PengaturanPeriode.pastikan_ada(lalu)
        for kode, nama, ling, butir in STANDAR:
            s = Standar.objects.create(periode=lalu, kode=kode, nama=nama, lingkup=lingkup[ling], urutan=int(kode))
            for i, (kp, teks, tipe) in enumerate(butir, start=1):
                p = PernyataanStandar.objects.create(standar=s, kode=kp, pernyataan=teks, urutan=i,
                                                     pertanyaan_panduan="Tunjukkan dokumen dan bukti pelaksanaannya.")
                p.tipe_unit.set(tipe)
        sekarang = Periode.objects.create(nama="AMI Demo", tahun_akademik="2025/2026", cp_lpm=admin)
        PengaturanPeriode.pastikan_ada(sekarang)
        salin_standar(lalu, sekarang)
        sekarang.aktifkan()

        semua_lingkup = list(lingkup.values())
        plot = lambda periode, unit, aud, ketua, pemimpin=None: simpan_audit(  # noqa: E731
            periode=periode, unit=unit, lingkup=semua_lingkup, auditee=pemimpin or auditee[unit],
            auditor=aud, ketua=ketua, oleh=admin, jadwal_audit_lapangan=timezone.now() + timedelta(days=12),
        )

        # Periode lalu: TE Final dengan 2 PTK, rencana dikirim (Tindak Lanjut PTK).
        a = plot(lalu, te, dosen[0:3], dosen[0], kaprodi_lama)
        a = self._isi_ser(a, kaprodi_lama)
        a = self._nilai(a, [[3, 4, 1, 2, 3]] * 3)
        a = self._rumuskan(a, setujui=True)
        pengisi = a.penugasan.get(peran="AUDITEE")
        for p in a.ptk.all():
            temuan.isi_ptk(a, pengisi, p, {"akar_masalah": "Belum ada SOP baku.", "rencana_tindakan": "Menyusun dan menetapkan SOP.",
                                          "target_tanggal": hari_ini - timedelta(days=60), "pic": "Kaprodi TE"})
        tindak_lanjut.kirim_rencana(Audit.objects.get(pk=a.pk), pengisi)
        a = Audit.objects.get(pk=a.pk)
        for p in a.ptk.all():
            tindak_lanjut.simpan_realisasi(a, pengisi, p, "SOP telah disusun dan disahkan dekan.")
            tindak_lanjut.tambah_bukti(a, pengisi, p, url=TAUTAN, nama="SK penetapan SOP")
        self._tahapan(lalu, hari_ini - timedelta(days=365))

        # Periode aktif, berbagai status.
        self._tahapan(sekarang, hari_ini + timedelta(days=2))  # deadline SER H-2 → banner pengingat
        plot(sekarang, biro, dosen[0:3], dosen[1])                                    # Belum Mulai
        b = plot(sekarang, ts, dosen[0:3], dosen[0])
        self._isi_ser(b, auditee[ts], jumlah=2, kirim=False)                          # Pengisian SER
        c = plot(sekarang, te, dosen[3:6], dosen[3])
        c = self._isi_ser(c, auditee[te])
        self._nilai(c, [[3, 3, 3, 3, 3], [3, 4, None, None, None], [3, 3, 3, 3, 3]])  # Penilaian (+ verifikasi PTK lalu)
        d = plot(sekarang, mt, dosen[0:3], dosen[2])
        d = self._isi_ser(d, auditee[mt])
        self._nilai(d, [[3, 3, 4, 2, 3], [3, 4, 4, 3, 4], [3, 3, 3, 2, 3]])          # D 20, NE 78,28 → Perlu Audit Lapangan
        e = plot(sekarang, ih, dosen[3:6], dosen[4])
        e = self._isi_ser(e, auditee[ih])
        e = self._nilai(e, [[3, 3, 2, 3, 4]] * 3)
        self._rumuskan(e)                                                             # Menunggu Persetujuan
        f = plot(sekarang, ft, [dosen[0], dosen[3], dosen[6]], dosen[6])
        f = self._isi_ser(f, auditee[ft])
        f = self._nilai(f, [[4, 3, 3, 4, 3, 3]] * 3)
        self._rumuskan(f, setujui=True)                                               # Final tanpa KTS/OB → Ditutup

    def _ringkas(self):
        self.stdout.write(self.style.SUCCESS("Data demo siap. Masuk di /akun/login/, pilih \"Masuk sebagai tamu\"."))
        self.stdout.write(f"Password semua akun: {PASSWORD}")
        for email, ket in [
            (f"master@{DOMAIN}", "Master Admin"), (f"admin@{DOMAIN}", "Admin LPM"), (f"rektor@{DOMAIN}", "Viewer (Rektorat)"),
            (f"kaprodi.ts@{DOMAIN}", "Auditee, SER sedang diisi (banner tenggat)"),
            (f"kaprodi.ih@{DOMAIN}", "Auditee, menunggu persetujuan hasil"),
            (f"kaprodi.te@{DOMAIN}", "Auditee TE baru (riwayat periode lalu)"),
            (f"kaprodi.te.lama@{DOMAIN}", "Auditee TE periode lalu (realisasi PTK)"),
            (f"dosen4@{DOMAIN}", "Ketua auditor TE: penilaian dan verifikasi PTK lalu"),
            (f"dosen5@{DOMAIN}", "Auditor TE (belum mengunci); ketua IH"),
            (f"dosen3@{DOMAIN}", "Ketua auditor Magister Teknik: Audit Lapangan"),
        ]:
            self.stdout.write(f"  {email:34} {ket}")
        for a in Audit.objects.filter(unit__kode__startswith="DEMO-").select_related("unit", "periode").order_by("periode__tahun_akademik", "unit__nama"):
            self.stdout.write(f"  [{a.periode.tahun_akademik}] {a.unit}: {a.get_status_display()}")
