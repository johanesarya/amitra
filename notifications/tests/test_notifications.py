"""Notifikasi in-app, email lewat antrean, pengingat H-3 s.d. H, dan login tamu.

FR-02, FR-29, FR-42, FR-46, FR-47, NFR-04, NFR-08.
"""

from datetime import timedelta
from smtplib import SMTPException
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from django_q.models import Schedule

from accounts.peran import Peran
from audits import ser
from audits.layanan import simpan_audit
from audits.models import Audit
from audits.tests.conftest import buat_pengguna
from findings import layanan as findings
from findings.tests.conftest import nilai_semua
from masterdata.models import TahapanPeriode
from notifications import penerima, tugas
from notifications.models import KirimanEmail, Notifikasi
from notifications.tenggat import tenggat_pengguna

pytestmark = pytest.mark.django_db
S = Audit.Status
CHECKLIST_KETUA = {k for k, _ in findings.CHECKLIST_KETUA}
CHECKLIST_AUDITEE = {k for k, _ in findings.CHECKLIST_AUDITEE}


def notif(jenis, **filter_):
    return Notifikasi.objects.filter(jenis=jenis, **filter_)


def penerima_notif(jenis):
    return set(notif(jenis).values_list("penerima__nama", flat=True))


def tahap(periode, jenis, selesai):
    TahapanPeriode.objects.update_or_create(
        periode=periode, jenis=jenis, defaults={"tanggal_mulai": selesai - timedelta(days=14), "tanggal_selesai": selesai}
    )


def segarkan(audit):
    return Audit.objects.get(pk=audit.pk)


def ajukan(audit, ketua):
    findings.sinkron_temuan(audit)
    for t in audit.temuan.all():
        findings.simpan_uraian(audit, ketua, t, "Uraian")
    findings.simpan_kesimpulan(audit, ketua, {"skor_a": 3, "skor_b": 3, "skor_c": 3, "penjelasan_a": "a",
                                              "penjelasan_b": "b", "penjelasan_c": "c"}, [])
    findings.ajukan_ke_auditee(audit, ketua, CHECKLIST_KETUA)
    return segarkan(audit)


# --- Peristiwa → penerima (FR-47) -------------------------------------------------------------

def test_diplot_memberi_tahu_tim_sekali(tim, admin_lpm, standar, auditor):
    audit = simpan_audit(**tim, oleh=admin_lpm)
    assert penerima_notif("DIPLOT") == {"Kaprodi", "Ani", "Budi", "Citra"}
    assert KirimanEmail.objects.filter(jenis="DIPLOT").count() == 4
    # Tim diubah: hanya anggota baru yang diberi tahu.
    simpan_audit(**{**tim, "auditor": [auditor[0], auditor[1], auditor[3]]}, oleh=admin_lpm, audit=audit)
    assert notif("DIPLOT").count() == 5 and notif("DIPLOT", penerima=auditor[3]).exists()


def test_ser_dikirim_memberi_tahu_auditor_dengan_email(audit_dinilai):
    assert penerima_notif("SER_DIKIRIM") == {"Ani", "Budi", "Citra", "Kaprodi"}
    emails = set(KirimanEmail.objects.filter(jenis="SER_DIKIRIM").values_list("penerima", flat=True))
    assert emails == {"ani@unika.ac.id", "budi@unika.ac.id", "citra@unika.ac.id"}  # auditee cukup in-app


def test_perlu_audit_lapangan_ke_ketua_cp_dan_master_admin(audit_dinilai, periode):
    periode.cp_lpm = buat_pengguna("CPLPM", peran=Peran.ADMIN)
    periode.save()
    buat_pengguna("Kepala", peran=Peran.MASTER_ADMIN)
    buat_pengguna("StafLain", peran=Peran.ADMIN)
    nilai_semua(audit_dinilai, [[3, 3, 4, 2], [3, 4, 4, 3], [3, 3, 3, 2]])  # contoh BRD: D 18,75; NE 77,03
    assert segarkan(audit_dinilai).status == S.PERLU_AUDIT_LAPANGAN
    assert penerima_notif("PERLU_AL") == {"Ani", "CPLPM", "Kepala"}  # Admin lain tidak (keputusan 31 Okt 2026)
    assert KirimanEmail.objects.filter(jenis="PERLU_AL").count() == 3


def test_rekonsiliasi_hanya_diberitahukan_bila_ada_butir_seri(audit_dinilai, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        nilai_semua(audit_dinilai, [[1, 3, 3, 3], [2, 3, 3, 3], [3, 3, 3, 3]])
    assert segarkan(audit_dinilai).status == S.REKONSILIASI
    assert penerima_notif("REKONSILIASI") == {"Ani"}


def test_rekonsiliasi_langsung_selesai_tanpa_notifikasi_rekonsiliasi(audit_dinilai, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        nilai_semua(audit_dinilai, [[3, 3, 3, 3]] * 3)
    assert not notif("REKONSILIASI").exists()
    assert penerima_notif("PERUMUSAN") == {"Ani", "Budi", "Citra"}
    assert set(KirimanEmail.objects.filter(jenis="PERUMUSAN").values_list("penerima", flat=True)) == {"ani@unika.ac.id"}


def test_persetujuan_dan_keberatan(audit, ketua, penugasan_auditee):
    audit = ajukan(audit, ketua)
    assert penerima_notif("MENUNGGU_PERSETUJUAN") == {"Kaprodi"}
    findings.ajukan_keberatan(audit, penugasan_auditee, "Tidak setuju 1.4")
    assert penerima_notif("KEBERATAN") == {"Ani"}


def test_buka_kunci_dan_perpanjangan_ser(audit_dinilai, django_capture_on_commit_callbacks):
    master = buat_pengguna("Kepala", peran=Peran.MASTER_ADMIN)
    ser.buka_kunci(audit_dinilai, master, "Bukti salah")
    assert penerima_notif("SER_DIBUKA") == {"Kaprodi", "Ani", "Budi", "Citra"}
    with django_capture_on_commit_callbacks(execute=True):
        ser.buka_kunci(segarkan(audit_dinilai), master, "Sakit", batas_baru=timezone.localdate() + timedelta(days=5))
    assert penerima_notif("PERPANJANGAN_SER") == {"Kaprodi"}


# --- Email Final berisi PDF (FR-42) -------------------------------------------------------------

def test_email_final_dengan_lampiran_terkirim_sekali(audit, ketua, penugasan_auditee, pdf_palsu, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        audit = ajukan(audit, ketua)
        findings.setujui(audit, penugasan_auditee, CHECKLIST_AUDITEE)
    kiriman = KirimanEmail.objects.filter(jenis="FINAL_PDF")
    assert set(kiriman.values_list("penerima", flat=True)) == {"kaprodi@unika.ac.id", "ani@unika.ac.id", "budi@unika.ac.id", "citra@unika.ac.id"}
    assert all(k.status == KirimanEmail.Status.TERKIRIM and len(k.lampiran) == 3 for k in kiriman)  # Laporan + 2 PTK
    email_final = [m for m in mail.outbox if "Dokumen final" in m.subject]
    assert len(email_final) == 4 and len(email_final[0].attachments) == 3
    # Dokumen dibuat ulang → sinyal terkirim lagi, tetapi email tidak dobel.
    penerima.kirim_paket_final(sender=None, audit=segarkan(audit))
    assert KirimanEmail.objects.filter(jenis="FINAL_PDF").count() == 4


def test_email_final_tanpa_lampiran_bila_terlalu_besar(audit, ketua, penugasan_auditee, pdf_palsu, django_capture_on_commit_callbacks, monkeypatch):
    monkeypatch.setattr(penerima, "BATAS_LAMPIRAN", 1)
    with django_capture_on_commit_callbacks(execute=True):
        audit = ajukan(audit, ketua)
        findings.setujui(audit, penugasan_auditee, CHECKLIST_AUDITEE)
    k = KirimanEmail.objects.filter(jenis="FINAL_PDF").first()
    assert k.lampiran == [] and "terlalu besar" in k.isi_teks and f"/audit/{audit.pk}/dokumen/" in k.isi_teks


# --- Kirim email dan coba ulang (NFR-04) -------------------------------------------------------

def test_email_gagal_dicatat_lalu_berhasil_saat_dicoba_ulang(audit_dinilai):
    k = KirimanEmail.objects.filter(jenis="SER_DIKIRIM").first()
    with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=SMTPException("SMTP mati")):
        with pytest.raises(SMTPException):
            tugas.kirim_email(k.pk)
    k.refresh_from_db()
    assert (k.status, k.percobaan) == (KirimanEmail.Status.GAGAL, 1) and "SMTP mati" in k.galat
    tugas.kirim_email(k.pk)
    k.refresh_from_db()
    assert (k.status, k.percobaan) == (KirimanEmail.Status.TERKIRIM, 2)
    tugas.kirim_email(k.pk)  # idempoten
    assert len([m for m in mail.outbox if m.to == [k.penerima]]) == 1


def test_email_tidak_dikirim_di_request_web(audit_dinilai):
    # Aturan proyek: email selalu lewat antrean. Tanpa on_commit dijalankan, belum ada yang terkirim.
    assert KirimanEmail.objects.filter(status=KirimanEmail.Status.DIANTRE).exists()
    assert mail.outbox == []


# --- Pengingat H-3 s.d. H (FR-46) ----------------------------------------------------------------

@pytest.fixture
def audit_baru(tim, admin_lpm):
    return simpan_audit(**tim, oleh=admin_lpm)


@pytest.mark.parametrize("sisa, diingatkan", [(4, False), (3, True), (1, True), (0, True), (-1, False)])
def test_pengingat_ser_hanya_h3_sampai_h(audit_baru, periode, sisa, diingatkan):
    tahap(periode, TahapanPeriode.Jenis.PENGISIAN_SER, timezone.localdate() + timedelta(days=sisa))
    tugas.kirim_pengingat_harian()
    assert notif("PENGINGAT_SER").exists() is diingatkan


def test_pengingat_tidak_dobel_di_hari_yang_sama(audit_baru, periode):
    tahap(periode, TahapanPeriode.Jenis.PENGISIAN_SER, timezone.localdate() + timedelta(days=2))
    tugas.kirim_pengingat_harian()
    tugas.kirim_pengingat_harian()
    assert notif("PENGINGAT_SER").count() == 1
    assert KirimanEmail.objects.filter(jenis="PENGINGAT_SER").count() == 1
    assert "jatuh tempo 2 hari lagi" in notif("PENGINGAT_SER").get().judul


def test_pengingat_mengikuti_batas_khusus(audit_baru, periode):
    tahap(periode, TahapanPeriode.Jenis.PENGISIAN_SER, timezone.localdate() - timedelta(days=5))
    audit_baru.batas_ser_khusus = timezone.localdate() + timedelta(days=1)
    audit_baru.save()
    tugas.kirim_pengingat_harian()
    assert notif("PENGINGAT_SER").exists()


def test_pengingat_penilaian_hanya_auditor_yang_belum_mengunci(audit_dinilai, periode):
    from audits import penilaian as pl

    tahap(periode, TahapanPeriode.Jenis.REVIEW_AUDITOR, timezone.localdate())
    t = pl.tim_auditor(audit_dinilai)
    pl.pastikan_penilaian(audit_dinilai, t[1].pengguna)
    for b in audit_dinilai.pernyataan_berlaku():
        p = audit_dinilai.penilaian.get(auditor=t[1].pengguna, pernyataan=b)
        pl.simpan_penilaian(audit_dinilai, t[1], b.pk, "SESUAI", "Dasar", "", p.versi)
    pl.kunci(audit_dinilai, t[1], t[1].pengguna)
    tugas.kirim_pengingat_harian()
    assert penerima_notif("PENGINGAT_PENILAIAN") == {"Ani", "Citra"}  # Budi sudah mengunci
    assert not notif("PENGINGAT_SER").exists()  # SER sudah dikirim


def test_pengingat_rencana_ptk(audit, ketua, penugasan_auditee, periode):
    audit = ajukan(audit, ketua)
    findings.setujui(audit, penugasan_auditee, CHECKLIST_AUDITEE)
    tahap(periode, TahapanPeriode.Jenis.TINDAK_LANJUT_PTK, timezone.localdate() + timedelta(days=3))
    tugas.kirim_pengingat_harian()
    assert penerima_notif("PENGINGAT_PTK") == {"Kaprodi"}
    data = {"akar_masalah": "a", "rencana_tindakan": "r", "target_tanggal": timezone.localdate(), "pic": "p"}
    for p in segarkan(audit).ptk.all():
        findings.isi_ptk(segarkan(audit), penugasan_auditee, p, data)
    assert tenggat_pengguna(penugasan_auditee.pengguna) == []


def test_banner_tenggat_muncul_lalu_hilang(client, audit_baru, periode, auditee):
    tahap(periode, TahapanPeriode.Jenis.PENGISIAN_SER, timezone.localdate() + timedelta(days=1))
    client.force_login(auditee)
    isi = client.get(reverse("beranda")).content.decode()
    assert "Pengisian SER Teknik Elektro</strong> jatuh tempo 1 hari lagi" in isi
    assert "Tenggat pengisian ser" in isi
    ser.pastikan_jawaban(audit_baru)
    for b in audit_baru.pernyataan_berlaku():
        ser.simpan_isian(audit_baru, b.pk, "x", audit_baru.jawaban_ser.get(pernyataan=b).versi, auditee, kategori="SESUAI")
        ser.tambah_tautan(segarkan(audit_baru), b.pk, "https://drive.google.com/file/d/x/view", auditee)
    ser.kirim(segarkan(audit_baru), auditee)
    assert "jatuh tempo" not in client.get(reverse("beranda")).content.decode()


def test_pasang_jadwal_harian_jam_tujuh(settings):
    call_command("pasang_jadwal")
    call_command("pasang_jadwal")  # idempoten
    s = Schedule.objects.get(name="pengingat-harian")
    assert s.func == "notifications.tugas.kirim_pengingat_harian" and s.schedule_type == Schedule.DAILY
    assert timezone.localtime(s.next_run).strftime("%H:%M") == "07:00"


# --- Halaman notifikasi (NFR-08) -------------------------------------------------------------------

def test_lonceng_buka_dan_tandai_dibaca(client, audit_dinilai, auditor):
    client.force_login(auditor[0])
    isi = client.get(reverse("notifications:daftar")).content.decode()
    belum = Notifikasi.objects.filter(penerima=auditor[0], dibaca_pada__isnull=True)
    assert f"{belum.count()}<span class=\"sr-only\"> belum dibaca" in isi
    n = belum.first()
    r = client.get(reverse("notifications:buka", args=[n.pk]))
    assert r.status_code == 302 and r.url == n.tautan
    n.refresh_from_db()
    assert n.dibaca_pada is not None
    client.post(reverse("notifications:tandai_semua"))
    assert not Notifikasi.objects.filter(penerima=auditor[0], dibaca_pada__isnull=True).exists()


def test_notifikasi_orang_lain_tidak_bisa_dibuka(client, audit_dinilai, auditor):
    n = Notifikasi.objects.filter(penerima=auditor[0]).first()
    client.force_login(auditor[1])
    assert client.get(reverse("notifications:buka", args=[n.pk])).status_code == 404


# --- Login tamu (FR-02) -----------------------------------------------------------------------------

@pytest.fixture
def tamu(db):
    user = buat_pengguna("Tamu", peran=Peran.PENGGUNA, akun_tamu=True)
    user.set_password("RahasiaTamu!2026")
    user.save()
    return user


def test_tamu_masuk_dengan_password(client, tamu):
    r = client.post(reverse("account_login"), {"login": "tamu@unika.ac.id", "password": "RahasiaTamu!2026"})
    assert r.status_code == 302
    assert client.get(reverse("beranda")).status_code == 200


def test_akun_kampus_tidak_bisa_masuk_dengan_password(client):
    dosen = buat_pengguna("Dosen")
    dosen.set_password("RahasiaDosen!2026")
    dosen.save()
    r = client.post(reverse("account_login"), {"login": "dosen@unika.ac.id", "password": "RahasiaDosen!2026"})
    assert r.status_code == 200  # formulir ditampilkan lagi dengan galat
    assert client.get(reverse("beranda")).status_code == 302


def test_reset_password_hanya_untuk_tamu_dan_lewat_antrean(client, tamu):
    buat_pengguna("Dosen")
    client.post(reverse("account_reset_password"), {"email": "dosen@unika.ac.id"})
    assert not KirimanEmail.objects.filter(penerima="dosen@unika.ac.id").exists()
    client.post(reverse("account_reset_password"), {"email": "tamu@unika.ac.id"})
    k = KirimanEmail.objects.get(penerima="tamu@unika.ac.id", jenis="AKUN")
    assert "/akun/password/reset/key/" in k.isi_teks
    assert mail.outbox == []  # belum dikirim di request web


def test_undangan_tamu_lewat_admin(client, tamu):
    master = buat_pengguna("Kepala", peran=Peran.MASTER_ADMIN)
    bukan_tamu = buat_pengguna("Dosen")
    client.force_login(master)
    r = client.post(reverse("admin:accounts_user_changelist"), {"action": "kirim_undangan_tamu", "_selected_action": [tamu.pk, bukan_tamu.pk]})
    assert r.status_code == 302
    k = KirimanEmail.objects.get(jenis="UNDANGAN_TAMU")
    assert k.penerima == "tamu@unika.ac.id"
    tautan = next(baris for baris in k.isi_teks.splitlines() if "/akun/password/reset/key/" in baris).strip()
    client.logout()
    assert client.get(tautan.replace("http://localhost:8000", "")).status_code in (200, 302)
