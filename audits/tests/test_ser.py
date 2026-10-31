"""SER auditee: FR-18 s.d. FR-23, BR-01, NFR-05, NFR-06, NFR-08, NFR-09, Bab 6.6."""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from accounts.peran import Peran
from audits import ser
from audits.layanan import simpan_audit
from audits.models import Audit, Bukti, JawabanSER, RiwayatStatus
from audits.status import ubah_status
from masterdata.models import PernyataanStandar, TahapanPeriode, TipeUnit

from .conftest import buat_pengguna

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 isi bukti"
TAUTAN = "https://drive.google.com/file/d/abc123/view"


@pytest.fixture(autouse=True)
def media_sementara(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def butir2(standar):
    p = PernyataanStandar.objects.create(standar=standar, kode="1.2", pernyataan="Kurikulum ditinjau berkala.", urutan=2)
    p.tipe_unit.set([TipeUnit.PRODI_S1])
    return p


@pytest.fixture
def audit(tim, admin_lpm, butir2):
    return simpan_audit(**tim, oleh=admin_lpm)


@pytest.fixture
def butir(audit):
    return list(audit.pernyataan_berlaku())


def isi_lengkap(audit, auditee, butir):
    ser.pastikan_jawaban(audit)
    for p in butir:
        j = audit.jawaban_ser.get(pernyataan=p)
        ser.simpan_penjelasan(audit, p.pk, f"Penjelasan {p.kode}", j.versi, auditee)
        ser.tambah_tautan(audit, p.pk, TAUTAN, auditee)


def deadline(periode, tanggal):
    TahapanPeriode.objects.update_or_create(
        periode=periode, jenis=TahapanPeriode.Jenis.PENGISIAN_SER,
        defaults={"tanggal_mulai": tanggal - timedelta(days=14), "tanggal_selesai": tanggal},
    )


# --- Butir dan status (FR-18, Bab 6.6) ----------------------------------------------

def test_butir_ser_sesuai_pernyataan_berlaku(audit):
    assert [p.kode for p, _ in ser.butir_ser(audit)] == ["1.1", "1.2"]


def test_simpan_pertama_memindahkan_status_ke_pengisian_ser(audit, auditee, butir):
    ser.pastikan_jawaban(audit)
    ser.simpan_penjelasan(audit, butir[0].pk, "Ada profil lulusan.", 1, auditee)
    audit.refresh_from_db()
    assert audit.status == Audit.Status.PENGISIAN_SER
    r = RiwayatStatus.objects.get(audit=audit)
    assert (r.dari, r.ke, r.oleh) == ("BELUM_MULAI", "PENGISIAN_SER", auditee)


def test_jawaban_tidak_punya_field_skor():
    # BR-01: auditee tidak memberi skor angka
    assert not any("skor" in f.name or "nilai" in f.name for f in JawabanSER._meta.get_fields())


def test_lompatan_status_ilegal_ditolak(audit, admin_lpm):
    with pytest.raises(ValidationError, match="tidak dapat berpindah"):
        ubah_status(audit, Audit.Status.FINAL, admin_lpm)


def test_riwayat_status_tidak_bisa_diubah_atau_dihapus(audit, auditee, butir):
    ser.pastikan_jawaban(audit)
    ser.simpan_penjelasan(audit, butir[0].pk, "x", 1, auditee)
    r = RiwayatStatus.objects.get()
    r.alasan = "ubah"
    with pytest.raises(ValueError):
        r.save()
    with pytest.raises(ValueError):
        r.delete()


def test_butir_di_luar_audit_ditolak(audit, auditee, standar):
    lain = PernyataanStandar.objects.create(standar=standar, kode="9.9", pernyataan="Khusus fakultas")
    lain.tipe_unit.set([TipeUnit.FAKULTAS])
    with pytest.raises(ValidationError, match="tidak termasuk"):
        ser.simpan_penjelasan(audit, lain.pk, "x", 1, auditee)


# --- Optimistic locking (NFR-05) ----------------------------------------------------

def test_konflik_versi(audit, auditee, butir):
    ser.pastikan_jawaban(audit)
    ser.simpan_penjelasan(audit, butir[0].pk, "Tab A", 1, auditee)
    with pytest.raises(ser.KonflikVersi) as e:
        ser.simpan_penjelasan(audit, butir[0].pk, "Tab B", 1, auditee)
    assert e.value.jawaban.penjelasan == "Tab A" and e.value.jawaban.versi == 2
    assert JawabanSER.objects.get(audit=audit, pernyataan=butir[0]).penjelasan == "Tab A"


def test_simpan_butir_hemat_query(audit, auditee, butir, django_assert_max_num_queries):
    # Pengaman NFR-02 (simpan butir < 500 ms): jumlah query tetap kecil.
    ser.pastikan_jawaban(audit)
    ser.simpan_penjelasan(audit, butir[0].pk, "awal", 1, auditee)
    with django_assert_max_num_queries(8):
        ser.simpan_penjelasan(audit, butir[0].pk, "lagi", 2, auditee)


# --- Bukti (FR-19, NFR-06, NFR-09) --------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://drive.google.com/file/d/abc/view",
    "https://docs.google.com/document/d/abc/edit",
    "https://DRIVE.google.com/drive/folders/xyz",
])
def test_tautan_google_drive_diterima(url):
    assert ser.periksa_tautan(url) == url


@pytest.mark.parametrize("url", [
    "http://drive.google.com/file/d/abc",
    "https://drive.google.com.evil.com/x",
    "https://dropbox.com/s/abc",
    "javascript:alert(1)",
    "",
])
def test_tautan_selain_google_drive_https_ditolak(url):
    with pytest.raises(ValidationError):
        ser.periksa_tautan(url)


@pytest.mark.parametrize("nama, isi", [
    ("laporan.pdf", PDF),
    ("foto.PNG", b"\x89PNG\r\n\x1a\n...."),
    ("foto.jpg", b"\xff\xd8\xff\xe0...."),
    ("data.xlsx", b"PK\x03\x04...."),
    ("lama.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1...."),
])
def test_berkas_diizinkan(nama, isi):
    ser.periksa_berkas(SimpleUploadedFile(nama, isi))


@pytest.mark.parametrize("nama, isi, pesan", [
    ("arsip.zip", b"PK\x03\x04", "tidak diizinkan"),
    ("video.mp4", b"\x00\x00\x00\x18ftyp", "tidak diizinkan"),
    ("skrip.exe", b"MZ", "tidak diizinkan"),
    ("palsu.pdf", b"MZ\x90\x00", "tidak sesuai"),
    ("kosong.pdf", b"", "kosong"),
])
def test_berkas_ditolak(nama, isi, pesan):
    with pytest.raises(ValidationError, match=pesan):
        ser.periksa_berkas(SimpleUploadedFile(nama, isi))


def test_berkas_lebih_dari_20_mb_ditolak():
    besar = SimpleUploadedFile("besar.pdf", PDF + b"0" * ser.UKURAN_BERKAS_MAKS)
    with pytest.raises(ValidationError, match="20 MB"):
        ser.periksa_berkas(besar)


def test_unggah_berkas_menyimpan_tanpa_nama_asli_di_path(audit, auditee, butir):
    b = ser.tambah_berkas(audit, butir[0].pk, SimpleUploadedFile("Laporan Rahasia.pdf", PDF), auditee)
    assert b.nama == "Laporan Rahasia.pdf" and b.ukuran == len(PDF)
    assert b.berkas.name.startswith(f"bukti/{audit.pk}/") and "Rahasia" not in b.berkas.name
    audit.refresh_from_db()
    assert audit.status == Audit.Status.PENGISIAN_SER


def test_hapus_bukti_menghapus_berkas(audit, auditee, butir):
    b = ser.tambah_berkas(audit, butir[0].pk, SimpleUploadedFile("a.pdf", PDF), auditee)
    storage, nama = b.berkas.storage, b.berkas.name
    ser.hapus_bukti(audit, b)
    assert not Bukti.objects.exists() and not storage.exists(nama)


# --- Kirim dan kunci (FR-22, FR-23) --------------------------------------------------

def test_ringkasan_menyebut_butir_belum_lengkap(audit, auditee, butir):
    ser.pastikan_jawaban(audit)
    ser.simpan_penjelasan(audit, butir[0].pk, "ada", 1, auditee)
    ser.tambah_tautan(audit, butir[1].pk, TAUTAN, auditee)
    r = ser.ringkasan(audit)
    assert (r.total, r.lengkap) == (2, 0)
    assert [(p.kode, kurang) for p, kurang in r.belum_lengkap] == [("1.1", ["bukti"]), ("1.2", ["penjelasan"])]
    assert not r.siap_dikirim


def test_kirim_ditolak_bila_belum_lengkap(audit, auditee):
    with pytest.raises(ValidationError, match="belum lengkap"):
        ser.kirim(audit, auditee)


def test_kirim_mengunci_ser(audit, auditee, butir):
    isi_lengkap(audit, auditee, butir)
    ser.kirim(audit, auditee)
    audit.refresh_from_db()
    assert audit.status == Audit.Status.PENILAIAN_AUDITOR and audit.ser_dikirim_pada
    j = audit.jawaban_ser.get(pernyataan=butir[0])
    with pytest.raises(ser.SERTerkunci, match="terkunci"):
        ser.simpan_penjelasan(audit, butir[0].pk, "ubah", j.versi, auditee)
    with pytest.raises(ser.SERTerkunci):
        ser.tambah_tautan(audit, butir[0].pk, TAUTAN, auditee)


# --- Deadline dan buka kunci (Bab 4, FR-23) ------------------------------------------

def test_ser_terkunci_setelah_deadline(audit, auditee, butir, periode):
    deadline(periode, timezone.localdate() - timedelta(days=1))
    ser.pastikan_jawaban(audit)
    with pytest.raises(ser.SERTerkunci, match="Batas pengisian"):
        ser.simpan_penjelasan(audit, butir[0].pk, "telat", 1, auditee)


def test_hari_deadline_masih_bisa_diisi(audit, periode):
    deadline(periode, timezone.localdate())
    assert audit.ser_bisa_diisi()


def test_buka_kunci_setelah_kirim(audit, auditee, butir):
    isi_lengkap(audit, auditee, butir)
    ser.kirim(audit, auditee)
    master = buat_pengguna("Kepala", peran=Peran.MASTER_ADMIN)
    ser.buka_kunci(audit, master, "Bukti 1.2 salah unggah")
    audit.refresh_from_db()
    assert audit.status == Audit.Status.PENGISIAN_SER and audit.ser_bisa_diisi()
    r = audit.riwayat_status.last()
    assert (r.dari, r.ke, r.oleh) == ("PENILAIAN_AUDITOR", "PENGISIAN_SER", master)
    assert "Bukti 1.2 salah unggah" in r.alasan


def test_buka_kunci_wajib_alasan(audit):
    with pytest.raises(ValidationError, match="Alasan"):
        ser.buka_kunci(audit, None, "  ")


def test_perpanjangan_setelah_deadline_wajib_batas_baru(audit, periode):
    deadline(periode, timezone.localdate() - timedelta(days=3))
    with pytest.raises(ValidationError, match="Tetapkan batas baru"):
        ser.buka_kunci(audit, None, "Terlambat karena sakit")
    besok = timezone.localdate() + timedelta(days=1)
    ser.buka_kunci(audit, None, "Terlambat karena sakit", batas_baru=besok)
    audit.refresh_from_db()
    assert audit.batas_ser == besok and audit.ser_bisa_diisi()
    assert "Perpanjangan" in audit.riwayat_status.last().alasan


def test_batas_baru_tidak_boleh_lampau(audit):
    with pytest.raises(ValidationError, match="sebelum hari ini"):
        ser.buka_kunci(audit, None, "x", batas_baru=date(2000, 1, 1))


# --- Halaman dan akses (NFR-08) -------------------------------------------------------

def test_auditee_membuka_halaman_ser(client, audit, auditee):
    client.force_login(auditee)
    resp = client.get(reverse("audits:ser", args=[audit.pk]))
    assert resp.status_code == 200
    isi = resp.content.decode()
    assert "Himbauan" in isi and "Google Drive" in isi
    assert resp.context["bisa_ubah"] is True
    assert JawabanSER.objects.filter(audit=audit).count() == 2


def test_autosave_lewat_endpoint(client, audit, auditee, butir):
    client.force_login(auditee)
    client.get(reverse("audits:ser", args=[audit.pk]))
    url = reverse("audits:ser_simpan", args=[audit.pk, butir[0].pk])
    r = client.post(url, {"penjelasan": "Isi pertama", "versi": 1})
    assert r.status_code == 200 and r.json()["versi"] == 2 and r.json()["lengkap"] is False
    konflik = client.post(url, {"penjelasan": "Tab lama", "versi": 1})
    assert konflik.status_code == 409
    assert konflik.json()["data"]["penjelasan"] == "Isi pertama"


def test_endpoint_simpan_ditolak_untuk_selain_auditee(client, audit, auditor, admin_lpm, butir):
    url = reverse("audits:ser_simpan", args=[audit.pk, butir[0].pk])
    for orang in (auditor[0], admin_lpm):
        client.force_login(orang)
        assert client.post(url, {"penjelasan": "x", "versi": 1}).status_code == 403


def test_endpoint_simpan_terkunci_423(client, audit, auditee, butir):
    isi_lengkap(audit, auditee, butir)
    ser.kirim(audit, auditee)
    client.force_login(auditee)
    j = audit.jawaban_ser.get(pernyataan=butir[0])
    r = client.post(reverse("audits:ser_simpan", args=[audit.pk, butir[0].pk]), {"penjelasan": "x", "versi": j.versi})
    assert r.status_code == 423


def test_tambah_tautan_lewat_htmx(client, audit, auditee, butir):
    client.force_login(auditee)
    r = client.post(reverse("audits:bukti_tautan", args=[audit.pk, butir[0].pk]), {"url": TAUTAN, "nama": "SK Kurikulum"})
    assert r.status_code == 200 and "SK Kurikulum" in r.content.decode()
    salah = client.post(reverse("audits:bukti_tautan", args=[audit.pk, butir[0].pk]), {"url": "https://dropbox.com/x"})
    assert "drive.google.com" in salah.content.decode()
    assert Bukti.objects.count() == 1


def test_auditor_belum_bisa_melihat_ser_sebelum_dikirim(client, audit, auditor):
    client.force_login(auditor[0])
    assert client.get(reverse("audits:ser", args=[audit.pk])).status_code == 403


def test_auditor_melihat_ser_setelah_dikirim_tanpa_bisa_mengubah(client, audit, auditee, auditor, butir):
    isi_lengkap(audit, auditee, butir)
    ser.kirim(audit, auditee)
    client.force_login(auditor[1])
    resp = client.get(reverse("audits:ser", args=[audit.pk]))
    assert resp.status_code == 200 and resp.context["bisa_ubah"] is False
    assert "Penjelasan 1.1" in resp.content.decode()


def test_admin_lpm_memantau_ser_kapan_saja(client, audit, admin_lpm):
    client.force_login(admin_lpm)
    resp = client.get(reverse("audits:ser", args=[audit.pk]))
    assert resp.status_code == 200 and resp.context["bisa_ubah"] is False


def test_unduh_bukti_dengan_pemeriksaan_akses(client, audit, auditee, auditor, butir):
    b = ser.tambah_berkas(audit, butir[0].pk, SimpleUploadedFile("bukti.pdf", PDF), auditee)
    url = reverse("audits:bukti_unduh", args=[audit.pk, b.pk])
    client.force_login(auditee)
    r = client.get(url)
    assert r.status_code == 200 and b"".join(r.streaming_content) == PDF
    client.force_login(auditor[0])  # SER belum dikirim
    assert client.get(url).status_code == 403
    client.force_login(buat_pengguna("Orang"))
    assert client.get(url).status_code == 403


def test_berkas_bukti_tidak_dilayani_di_url_media(client, audit, auditee, butir):
    b = ser.tambah_berkas(audit, butir[0].pk, SimpleUploadedFile("bukti.pdf", PDF), auditee)
    client.force_login(auditee)
    assert client.get(f"/media/{b.berkas.name}").status_code == 404


def test_bukti_audit_lain_tidak_bisa_diakses_lewat_audit_sendiri(client, audit, auditee, butir, tim, admin_lpm, prodi_lain, auditor):
    lain = simpan_audit(**{**tim, "unit": prodi_lain, "auditee": auditor[4]}, oleh=admin_lpm)
    b = ser.tambah_berkas(audit, butir[0].pk, SimpleUploadedFile("a.pdf", PDF), auditee)
    client.force_login(auditor[4])
    assert client.get(reverse("audits:bukti_unduh", args=[lain.pk, b.pk])).status_code == 404


def test_halaman_kirim_dan_kirim(client, audit, auditee, butir):
    client.force_login(auditee)
    url = reverse("audits:ser_kirim", args=[audit.pk])
    isi = client.get(url).content.decode()
    assert "2 butir belum lengkap" in isi and "disabled" in isi
    isi_lengkap(audit, auditee, butir)
    assert client.post(url).status_code == 302
    audit.refresh_from_db()
    assert audit.status == Audit.Status.PENILAIAN_AUDITOR


@pytest.mark.parametrize("peran, status", [(Peran.MASTER_ADMIN, 200), (Peran.ADMIN, 403), (Peran.PENGGUNA, 403)])
def test_buka_kunci_hanya_master_admin(client, audit, peran, status):
    client.force_login(buat_pengguna("Uji", peran=peran))
    assert client.get(reverse("audits:ser_buka_kunci", args=[audit.pk])).status_code == status


def test_buka_kunci_lewat_halaman(client, audit, auditee, butir):
    isi_lengkap(audit, auditee, butir)
    ser.kirim(audit, auditee)
    client.force_login(buat_pengguna("Kepala", peran=Peran.MASTER_ADMIN))
    r = client.post(reverse("audits:ser_buka_kunci", args=[audit.pk]), {"alasan": "Revisi bukti"})
    assert r.status_code == 302
    audit.refresh_from_db()
    assert audit.status == Audit.Status.PENGISIAN_SER
