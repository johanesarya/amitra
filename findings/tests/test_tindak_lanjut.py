"""Tindak lanjut PTK lintas periode: FR-21, FR-24, FR-36, FR-37, BR-17, Bab 6.6, Lampiran D."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.urls import reverse

from accounts.peran import Peran
from audits import ser
from audits.layanan import simpan_audit
from audits.models import Audit
from audits.tests.conftest import buat_pengguna
from documents.konteks import konteks
from documents.models import Dokumen, JenisDokumen
from findings import layanan, tindak_lanjut
from findings.models import PTK
from masterdata.models import PengaturanPeriode, Periode
from masterdata.salin import salin_standar
from notifications.models import Notifikasi

from .conftest import nilai_semua

pytestmark = pytest.mark.django_db
S = Audit.Status
CHECKLIST_KETUA = {k for k, _ in layanan.CHECKLIST_KETUA}
CHECKLIST_AUDITEE = {k for k, _ in layanan.CHECKLIST_AUDITEE}
RENCANA = {"akar_masalah": "Belum ada SOP", "rencana_tindakan": "Susun SOP", "target_tanggal": date(2026, 6, 30), "pic": "Kaprodi"}
TAUTAN = "https://drive.google.com/file/d/bukti/view"


def segarkan(audit):
    return Audit.objects.get(pk=audit.pk)


def jadikan_final(audit, ketua, auditee):
    layanan.sinkron_temuan(audit)
    for t in audit.temuan.all():
        layanan.simpan_uraian(audit, ketua, t, f"Uraian {t}")
    layanan.simpan_kesimpulan(audit, ketua, {"skor_a": 3, "skor_b": 3, "skor_c": 3, "penjelasan_a": "a",
                                             "penjelasan_b": "b", "penjelasan_c": "c"}, [])
    layanan.ajukan_ke_auditee(audit, ketua, CHECKLIST_KETUA)
    layanan.setujui(segarkan(audit), auditee, CHECKLIST_AUDITEE)
    return segarkan(audit)


@pytest.fixture
def lama(audit, ketua, penugasan_auditee):
    """Audit 2025/2026 Final dengan PTK 001 (butir 1.3, KTS) dan 002 (butir 1.4, OB)."""
    return jadikan_final(audit, ketua, penugasan_auditee)


def kirim_rencana(lama, penugasan_auditee):
    for p in lama.ptk.all():
        layanan.isi_ptk(lama, penugasan_auditee, p, RENCANA)
    tindak_lanjut.kirim_rencana(lama, penugasan_auditee)
    return segarkan(lama)


@pytest.fixture
def pimpinan_baru(prodi):
    return buat_pengguna("KaprodiBaru", homebase=prodi)


@pytest.fixture
def baru(lama, periode, prodi, lingkup, auditor, admin_lpm, pimpinan_baru):
    """Audit 2026/2027 unit yang sama, standar disalin, tim baru, SER sudah dikirim."""
    p2 = Periode.objects.create(nama="AMI 2026/2027", tahun_akademik="2026/2027")
    PengaturanPeriode.pastikan_ada(p2)
    salin_standar(periode, p2)
    a = simpan_audit(periode=p2, unit=prodi, lingkup=[lingkup], auditee=pimpinan_baru, auditor=auditor[2:5], ketua=auditor[2], oleh=admin_lpm)
    ser.pastikan_jawaban(a)
    for b in a.pernyataan_berlaku():
        ser.simpan_penjelasan(a, b.pk, "Penjelasan baru", a.jawaban_ser.get(pernyataan=b).versi, pimpinan_baru)
        ser.tambah_tautan(segarkan(a), b.pk, TAUTAN, pimpinan_baru)
    ser.kirim(segarkan(a), pimpinan_baru)
    return segarkan(a)


def penugasan(audit, user):
    return audit.penugasan.get(pengguna=user)


# --- Alur status (Bab 6.6) -----------------------------------------------------------------

def test_final_tanpa_ptk_langsung_ditutup(audit_dinilai):
    audit = nilai_semua(audit_dinilai, [[3, 3, 3, 4]] * 3)
    audit = jadikan_final(audit, audit.penugasan.get(ketua=True), audit.penugasan.get(peran="AUDITEE"))
    assert audit.status == S.DITUTUP
    assert list(audit.riwayat_status.values_list("ke", flat=True))[-2:] == ["FINAL", "DITUTUP"]


def test_final_dengan_ptk_tetap_final(lama):
    assert lama.status == S.FINAL and lama.ptk.count() == 2


def test_kirim_rencana_lalu_terkunci(lama, penugasan_auditee):
    with pytest.raises(ValidationError, match="Lengkapi rencana"):
        tindak_lanjut.kirim_rencana(lama, penugasan_auditee)
    lama = kirim_rencana(lama, penugasan_auditee)
    assert lama.status == S.TINDAK_LANJUT_PTK
    assert all(p.rencana_dikirim_pada for p in lama.ptk.all())
    with pytest.raises(ValidationError, match="terkunci"):
        layanan.isi_ptk(lama, penugasan_auditee, lama.ptk.first(), {**RENCANA, "pic": "Lain"})


def test_realisasi_dan_bukti_tindak_lanjut(lama, penugasan_auditee, ketua, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = lama.ptk.first()
    with pytest.raises(ValidationError, match="setelah rencana"):
        tindak_lanjut.simpan_realisasi(lama, penugasan_auditee, p, "x")
    lama = kirim_rencana(lama, penugasan_auditee)
    tindak_lanjut.simpan_realisasi(lama, penugasan_auditee, p, "SOP disahkan Maret 2026")
    b1 = tindak_lanjut.tambah_bukti(lama, penugasan_auditee, p, url=TAUTAN, nama="SK SOP")
    b2 = tindak_lanjut.tambah_bukti(lama, penugasan_auditee, p, berkas=SimpleUploadedFile("sop.pdf", b"%PDF-1.4 sop"))
    assert {b1.ptk_id, b2.ptk_id} == {p.pk} and b2.jawaban_id is None
    assert b2.berkas.name.startswith(f"bukti-ptk/{lama.pk}/")
    with pytest.raises(ValidationError):
        tindak_lanjut.tambah_bukti(lama, penugasan_auditee, p, url="https://dropbox.com/x")
    with pytest.raises(PermissionError):
        tindak_lanjut.simpan_realisasi(lama, ketua, p, "bukan auditee")


# --- Audit periode lalu dan padanan butir (FR-21, BR-17) --------------------------------------

def test_audit_periode_lalu_dan_padanan_lewat_asal(lama, baru):
    assert tindak_lanjut.audit_periode_lalu(baru) == lama
    padanan = tindak_lanjut.padanan_butir(baru, tindak_lanjut.ptk_periode_lalu(baru))
    kode = {baru.pernyataan_berlaku().get(pk=pk).kode: [p.kode for p in ptk] for pk, ptk in padanan.items()}
    assert kode == {"1.3": ["PTK No. 001"], "1.4": ["PTK No. 002"]}


def test_padanan_lewat_kode_bila_standar_diimpor_ulang(lama, baru):
    for p in baru.pernyataan_berlaku():
        p.asal = None
        p.save()
    assert len(tindak_lanjut.padanan_butir(baru, tindak_lanjut.ptk_periode_lalu(baru))) == 2


def test_temuan_lalu_tampil_di_ser_periode_baru(client, lama, baru, pimpinan_baru):
    butir = baru.pernyataan_berlaku().get(kode="1.3")
    client.force_login(pimpinan_baru)
    isi = client.get(reverse("audits:ser", args=[baru.pk]), {"butir": butir.pk}).content.decode()
    assert "Temuan periode lalu pada butir ini" in isi and "PTK No. 001" in isi and "belum diverifikasi efektif" in isi
    lain = baru.pernyataan_berlaku().get(kode="1.1")
    assert "Temuan periode lalu" not in client.get(reverse("audits:ser", args=[baru.pk]), {"butir": lain.pk}).content.decode()


# --- Verifikasi (FR-37) -----------------------------------------------------------------------

def test_tim_baru_diberi_tahu_ada_ptk_lalu(baru, auditor):
    assert set(Notifikasi.objects.filter(jenis="PTK_LALU").values_list("penerima__nama", flat=True)) == {"Citra", "Dedi", "Eka"}


def test_verifikasi_menutup_audit_lama(lama, baru, auditor, penugasan_auditee):
    lama = kirim_rencana(lama, penugasan_auditee)
    p1, p2 = lama.ptk.order_by("nomor_urut")
    anggota = penugasan(baru, auditor[3])
    with pytest.raises(ValidationError, match="Catatan"):
        tindak_lanjut.verifikasi(baru, anggota, p1, PTK.Status.EFEKTIF, "")
    tindak_lanjut.verifikasi(baru, anggota, p1, PTK.Status.EFEKTIF, "SOP sudah dijalankan")
    assert segarkan(lama).status == S.TINDAK_LANJUT_PTK  # masih ada yang belum
    ketua_baru = penugasan(baru, auditor[2])
    tindak_lanjut.verifikasi(baru, ketua_baru, p2, PTK.Status.TIDAK_EFEKTIF, "Belum ada bukti pelaksanaan")
    assert segarkan(lama).status == S.DITUTUP
    p1.refresh_from_db()
    assert (p1.status, p1.diverifikasi_di, p1.diverifikasi_oleh) == ("EFEKTIF", baru, auditor[3])
    penerima = set(Notifikasi.objects.filter(jenis="PTK_DIVERIFIKASI").values_list("penerima__nama", flat=True))
    assert penerima == {"Kaprodi", "KaprodiBaru"}
    assert tindak_lanjut.ringkasan_verifikasi(baru) | {"audit_lalu": None} == {
        "audit_lalu": None, "total": 2, "efektif": 1, "belum_efektif": 1, "belum_diverifikasi": 0,
    }


def test_verifikasi_hanya_oleh_tim_baru_pada_status_yang_diizinkan(lama, baru, auditor, pimpinan_baru, prodi_lain, tim, admin_lpm):
    p = lama.ptk.first()
    with pytest.raises(PermissionError):
        tindak_lanjut.verifikasi(baru, penugasan(baru, pimpinan_baru), p, PTK.Status.EFEKTIF, "x")
    # PTK unit lain ditolak.
    lain = simpan_audit(**{**tim, "periode": baru.periode, "unit": prodi_lain, "auditee": buat_pengguna("KaprodiTS"),
                           "auditor": auditor[2:5], "ketua": auditor[2]}, oleh=admin_lpm)
    lain.status = S.PENILAIAN_AUDITOR
    lain.save()
    with pytest.raises(ValidationError, match="bukan milik"):
        tindak_lanjut.verifikasi(lain, penugasan(lain, auditor[2]), p, PTK.Status.EFEKTIF, "x")
    baru.status = S.MENUNGGU_PERSETUJUAN
    baru.save()
    with pytest.raises(ValidationError, match="selama penilaian"):
        tindak_lanjut.verifikasi(baru, penugasan(baru, auditor[2]), p, PTK.Status.EFEKTIF, "x")


def test_halaman_verifikasi_dan_bukti(client, lama, baru, auditor, penugasan_auditee, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    lama = kirim_rencana(lama, penugasan_auditee)
    p = lama.ptk.first()
    b = tindak_lanjut.tambah_bukti(lama, penugasan_auditee, p, berkas=SimpleUploadedFile("sop.pdf", b"%PDF-1.4 sop"))
    url = reverse("findings:verifikasi", args=[baru.pk])
    client.force_login(auditor[3])
    resp = client.get(url)
    assert resp.status_code == 200 and resp.context["bisa_verifikasi"] is True
    r = client.get(reverse("findings:verifikasi_bukti", args=[baru.pk, b.pk]))
    assert r.status_code == 200 and b"".join(r.streaming_content) == b"%PDF-1.4 sop"
    r = client.post(url, {"ptk": p.pk, "hasil": "EFEKTIF", "catatan": "Terbukti"})
    assert r.status_code == 302
    p.refresh_from_db()
    assert p.status == PTK.Status.EFEKTIF
    client.force_login(auditor[0])  # auditor audit lama, bukan tim baru
    assert client.get(url).status_code == 403


def test_verifikasi_membuat_ulang_dokumen_ptk(lama, baru, auditor, penugasan_auditee, django_capture_on_commit_callbacks):
    p = lama.ptk.first()
    Dokumen.objects.get_or_create(audit=lama, jenis=JenisDokumen.PTK, ptk=p)
    from unittest import mock

    with mock.patch("documents.tugas.render_pdf", return_value=b"%PDF"), django_capture_on_commit_callbacks(execute=True):
        tindak_lanjut.verifikasi(baru, penugasan(baru, auditor[2]), p, PTK.Status.EFEKTIF, "OK")
    d = Dokumen.objects.get(ptk=p)
    assert d.status == "SIAP"
    html = render_to_string("documents/pdf/ptk.html", konteks(d))
    assert "Terverifikasi efektif" in html and "OK" in html


def test_lampiran_d_laporan_dan_petunjuk_kesimpulan_c(client, lama, baru, auditor):
    tindak_lanjut.verifikasi(baru, penugasan(baru, auditor[2]), lama.ptk.first(), PTK.Status.EFEKTIF, "Tuntas")
    d, _ = Dokumen.objects.get_or_create(audit=baru, jenis=JenisDokumen.LAPORAN_AMI)
    html = render_to_string("documents/pdf/laporan.html", konteks(d))
    bagian_d = html.split('id="lampiran-d"', 1)[1]
    assert "PTK No. 001" in bagian_d and "Terverifikasi efektif" in bagian_d and "Belum diverifikasi" in bagian_d
    baru.status = S.PERUMUSAN_TEMUAN
    baru.save()
    client.force_login(auditor[2])
    isi = client.get(reverse("findings:perumusan", args=[baru.pk])).content.decode()
    assert "1 dari 2 PTK periode lalu efektif" in isi


# --- Riwayat berbasis unit (FR-24) ------------------------------------------------------------

def test_pimpinan_baru_membuka_riwayat_unit(client, lama, baru, pimpinan_baru):
    client.force_login(pimpinan_baru)
    daftar = client.get(reverse("audits:riwayat")).context["daftar"]
    assert lama in list(daftar)
    for nama in ("audits:detail", "audits:ser", "findings:persetujuan", "findings:ptk", "documents:daftar", "audits:perbedaan"):
        assert client.get(reverse(nama, args=[lama.pk])).status_code == 200, nama
    # Hanya-baca: tidak bisa mengisi PTK audit lama.
    r = client.post(reverse("findings:ptk", args=[lama.pk]), {"aksi": "rencana", "ptk": lama.ptk.first().pk, **RENCANA})
    assert r.status_code == 403


def test_auditee_unit_lain_tidak_bisa_membuka_riwayat(client, lama):
    orang = buat_pengguna("Lain")
    client.force_login(orang)
    assert client.get(reverse("audits:detail", args=[lama.pk])).status_code == 403


# --- Arsip periode (Bab 6.6) -------------------------------------------------------------------

def test_arsip_periode_menutup_audit_terbuka(client, lama, penugasan_auditee):
    lama = kirim_rencana(lama, penugasan_auditee)
    url = reverse("audits:arsip_periode", args=[lama.periode_id])
    client.force_login(buat_pengguna("Staf", peran=Peran.ADMIN))
    assert client.get(url).status_code == 403
    client.force_login(buat_pengguna("Kepala", peran=Peran.MASTER_ADMIN))
    assert client.get(url).status_code == 200
    client.post(url, {"alasan": ""})
    assert segarkan(lama).status == S.TINDAK_LANJUT_PTK
    client.post(url, {"alasan": "Tutup buku 2025/2026"})
    lama = segarkan(lama)
    assert lama.status == S.DITUTUP and "Tutup buku" in lama.riwayat_status.last().alasan
