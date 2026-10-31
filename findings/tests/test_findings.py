"""Perumusan temuan sampai Final: FR-32 s.d. FR-38, BR-12, BR-14 s.d. BR-18, NFR-08."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from accounts.peran import Peran
from audits.models import Audit, HasilPerhitungan
from audits.tests.conftest import buat_pengguna
from findings import layanan
from findings.models import PTK, Kesimpulan, Temuan, Usulan
from masterdata.models import TujuanAudit

from .conftest import nilai_semua

pytestmark = pytest.mark.django_db
S = Audit.Status


def segarkan(audit):
    return Audit.objects.get(pk=audit.pk)


def lengkapi(audit, ketua, c=4, c_tidak_berlaku=False):
    layanan.sinkron_temuan(audit)
    for t in audit.temuan.all():
        layanan.simpan_uraian(audit, ketua, t, f"Uraian {t}")
    data = {"skor_a": 3, "skor_b": 2, "skor_c": c, "penjelasan_a": "A", "penjelasan_b": "B", "penjelasan_c": "C"}
    if c_tidak_berlaku:
        data["c_tidak_berlaku"] = "1"
    layanan.simpan_kesimpulan(audit, ketua, data, [])


CHECKLIST_KETUA = {k for k, _ in layanan.CHECKLIST_KETUA}
CHECKLIST_AUDITEE = {k for k, _ in layanan.CHECKLIST_AUDITEE}


def ajukan(audit, ketua, **kw):
    lengkapi(audit, ketua, **kw)
    return layanan.ajukan_ke_auditee(audit, ketua, CHECKLIST_KETUA)


# --- Temuan otomatis (FR-33, BR-14) ------------------------------------------------------

def test_temuan_otomatis_dari_kategori_final(audit):
    assert audit.status == S.PERUMUSAN_TEMUAN
    layanan.sinkron_temuan(audit)
    assert [(t.jenis, t.pernyataan.kode) for t in audit.temuan.select_related("pernyataan")] == [
        ("KELEBIHAN", "1.2"), ("KTS", "1.3"), ("OB", "1.4"),
    ]


def test_ubah_kategori_final_menyinkronkan_temuan(audit, ketua):
    layanan.sinkron_temuan(audit)
    kts = audit.temuan.get(jenis="KTS")
    layanan.simpan_uraian(audit, ketua, kts, "Dokumen renstra tidak ada")
    butir = {p.kode: p for p in audit.pernyataan_berlaku()}

    with pytest.raises(ValidationError, match="Alasan"):
        layanan.ubah_kategori_final(audit, ketua, butir["1.3"].pk, "OB", "")
    layanan.ubah_kategori_final(audit, ketua, butir["1.3"].pk, "OB", "Dokumen ditemukan saat diskusi")
    t = audit.temuan.get(pernyataan=butir["1.3"])
    assert t.jenis == "OB" and t.uraian == "Dokumen renstra tidak ada"  # uraian dipertahankan

    layanan.ubah_kategori_final(audit, ketua, butir["1.4"].pk, "SESUAI", "Bukti lengkap")
    assert not audit.temuan.filter(pernyataan=butir["1.4"]).exists()
    layanan.ubah_kategori_final(audit, ketua, butir["1.1"].pk, "PELAMPAUAN", "Melampaui standar")
    assert audit.temuan.get(pernyataan=butir["1.1"]).jenis == "KELEBIHAN"


def test_hanya_ketua_mengubah_kategori(audit, anggota):
    with pytest.raises(PermissionError):
        layanan.ubah_kategori_final(audit, anggota, audit.pernyataan_berlaku()[0].pk, "KTS", "x")


def test_usulan_uraian_dari_kondisi_faktual(audit):
    layanan.sinkron_temuan(audit)
    saran = layanan.usulan_uraian(audit, audit.temuan.get(jenis="KTS"))
    assert len(saran) == 3 and all("Kondisi faktual 1.3" in teks for _, teks in saran)


# --- Usulan anggota (Bab 4) ---------------------------------------------------------------

def test_usulan_peluang_diterima_ketua(audit, ketua, anggota):
    u = layanan.ajukan_usulan(audit, anggota, Usulan.Jenis.PELUANG, "Digitalisasi arsip kurikulum")
    layanan.tanggapi_usulan(audit, ketua, u, terima=True)
    u.refresh_from_db()
    assert u.status == Usulan.Status.DITERIMA
    assert audit.temuan.get(jenis="PELUANG").uraian == "Digitalisasi arsip kurikulum"
    with pytest.raises(ValidationError, match="sudah ditanggapi"):
        layanan.tanggapi_usulan(audit, ketua, u, terima=False)


def test_usulan_uraian_ditambahkan(audit, ketua, anggota):
    layanan.sinkron_temuan(audit)
    t = audit.temuan.get(jenis="OB")
    layanan.simpan_uraian(audit, ketua, t, "Awal")
    u = layanan.ajukan_usulan(audit, anggota, Usulan.Jenis.URAIAN, "Tambahan dari anggota", temuan=t)
    layanan.tanggapi_usulan(audit, ketua, u, terima=True)
    t.refresh_from_db()
    assert t.uraian == "Awal\nTambahan dari anggota"


def test_auditee_tidak_bisa_mengusulkan(audit, penugasan_auditee):
    with pytest.raises(PermissionError):
        layanan.ajukan_usulan(audit, penugasan_auditee, Usulan.Jenis.PELUANG, "x")


def test_anggota_tidak_bisa_menanggapi_usulan(audit, anggota):
    u = layanan.ajukan_usulan(audit, anggota, Usulan.Jenis.PELUANG, "x")
    with pytest.raises(PermissionError):
        layanan.tanggapi_usulan(audit, anggota, u, terima=True)


# --- Checklist ketua, NK, hasil akhir, PTK -------------------------------------------------

def test_syarat_ketua_menyebut_kekurangan(audit):
    layanan.sinkron_temuan(audit)
    syarat = " ".join(layanan.syarat_ketua(audit))
    assert "3 temuan belum memiliki uraian" in syarat and "Kesimpulan" in syarat
    with pytest.raises(ValidationError):
        layanan.ajukan_ke_auditee(audit, audit.penugasan.get(ketua=True), CHECKLIST_KETUA)


def test_checklist_ketua_wajib_lengkap(audit, ketua):
    lengkapi(audit, ketua)
    with pytest.raises(ValidationError, match="Centang"):
        layanan.ajukan_ke_auditee(audit, ketua, CHECKLIST_KETUA - {"teruskan"})


def test_ajukan_menghitung_final_dan_menomori_ptk(audit, ketua):
    hasil = ajukan(audit, ketua)
    audit = segarkan(audit)
    assert audit.status == S.MENUNGGU_PERSETUJUAN
    # N tiap auditor = (3+4+1+2)/16×100 = 62,5; NE = 62,5 − 0,5 − 0,3 + 0,25 = 61,95
    assert hasil.tahap == HasilPerhitungan.Tahap.FINAL and hasil.ne == Decimal("61.95")
    assert not hasil.memenuhi_kkm
    # NK = 0,6×75 + 0,3×50 + 0,1×100 = 70
    assert hasil.nk == Decimal("70.00")
    assert hasil.hasil_akhir is None  # proporsi NE/NK belum diputuskan LPM
    assert [(p.kode, p.temuan.pernyataan.kode) for p in audit.ptk.select_related("temuan__pernyataan")] == [
        ("PTK No. 001", "1.3"), ("PTK No. 002", "1.4"),
    ]


def test_hasil_akhir_dengan_proporsi_pengaturan(audit, ketua, periode):
    periode.pengaturan.proporsi_ne = Decimal("70")
    periode.pengaturan.proporsi_nk = Decimal("30")
    periode.pengaturan.save()
    hasil = ajukan(audit, ketua)
    assert hasil.hasil_akhir == Decimal("64.37")  # 0,7×61,95 + 0,3×70 = 64,365


def test_c_tidak_berlaku_bobot_dibagi(audit, ketua):
    hasil = ajukan(audit, ketua, c_tidak_berlaku=True)
    assert hasil.nk == Decimal("66.67")  # (60×75 + 30×50) / 90


def test_tanpa_kts_ob_tidak_ada_ptk(audit_dinilai):
    # BR-16
    audit = nilai_semua(audit_dinilai, [[3, 3, 3, 4]] * 3)
    ketua = audit.penugasan.get(ketua=True)
    ajukan(audit, ketua)
    assert not PTK.objects.filter(audit=audit).exists()
    assert segarkan(audit).status == S.MENUNGGU_PERSETUJUAN


# --- Persetujuan auditee dan keberatan (FR-38, BR-18) ---------------------------------------

def test_auditee_menyetujui_menjadi_final(audit, ketua, penugasan_auditee):
    ajukan(audit, ketua)
    audit = segarkan(audit)
    with pytest.raises(ValidationError, match="Centang"):
        layanan.setujui(audit, penugasan_auditee, {"baca"})
    layanan.setujui(audit, penugasan_auditee, CHECKLIST_AUDITEE)
    assert segarkan(audit).status == S.FINAL


def test_keberatan_sekali_dan_wajib_ditanggapi(audit, ketua, penugasan_auditee):
    ajukan(audit, ketua)
    audit = segarkan(audit)
    with pytest.raises(ValidationError, match="Tuliskan"):
        layanan.ajukan_keberatan(audit, penugasan_auditee, " ")
    layanan.ajukan_keberatan(audit, penugasan_auditee, "Butir 1.4 sudah ada SOP-nya")
    audit = segarkan(audit)
    assert audit.status == S.PERUMUSAN_TEMUAN

    with pytest.raises(ValidationError):
        layanan.ajukan_ke_auditee(audit, ketua, CHECKLIST_KETUA)  # belum ditanggapi
    assert "Keberatan auditee belum ditanggapi." in layanan.syarat_ketua(audit)
    layanan.tanggapi_keberatan(audit, ketua, "SOP diperiksa; kategori diubah menjadi Sesuai.")
    layanan.ubah_kategori_final(audit, ketua, audit.pernyataan_berlaku().get(kode="1.4").pk, "SESUAI", "SOP ada")
    layanan.ajukan_ke_auditee(audit, ketua, CHECKLIST_KETUA)
    audit = segarkan(audit)
    assert audit.status == S.MENUNGGU_PERSETUJUAN
    assert [p.kode for p in audit.ptk.all()] == ["PTK No. 001"]  # dinomori ulang

    with pytest.raises(ValidationError, match="sekali"):
        layanan.ajukan_keberatan(audit, penugasan_auditee, "Lagi")
    layanan.setujui(audit, penugasan_auditee, CHECKLIST_AUDITEE)
    assert segarkan(audit).status == S.FINAL


def test_hanya_auditee_yang_menyetujui(audit, ketua):
    ajukan(audit, ketua)
    with pytest.raises(PermissionError):
        layanan.setujui(segarkan(audit), ketua, CHECKLIST_AUDITEE)


# --- PTK auditee (FR-36) -----------------------------------------------------------------

def test_isi_ptk_setelah_final(audit, ketua, penugasan_auditee):
    ajukan(audit, ketua)
    audit = segarkan(audit)
    ptk = audit.ptk.first()
    data = {"akar_masalah": "SOP belum ada", "rencana_tindakan": "Susun SOP", "target_tanggal": date(2026, 6, 30), "pic": "Kaprodi"}
    with pytest.raises(ValidationError, match="Final"):
        layanan.isi_ptk(audit, penugasan_auditee, ptk, data)
    layanan.setujui(audit, penugasan_auditee, CHECKLIST_AUDITEE)
    audit = segarkan(audit)
    ptk = layanan.isi_ptk(audit, penugasan_auditee, ptk, {**data, "pic": ""})
    assert ptk.status == PTK.Status.TERBUKA  # belum lengkap
    ptk = layanan.isi_ptk(audit, penugasan_auditee, ptk, data)
    assert ptk.status == PTK.Status.DIRENCANAKAN
    with pytest.raises(PermissionError):
        layanan.isi_ptk(audit, ketua, ptk, data)


# --- Halaman dan akses (NFR-08, Bab 4) ------------------------------------------------------

def test_akses_halaman_perumusan(client, audit, ketua, anggota, penugasan_auditee, admin_lpm):
    url = reverse("findings:perumusan", args=[audit.pk])
    for orang, kode in ((ketua.pengguna, 200), (anggota.pengguna, 200), (admin_lpm, 200), (penugasan_auditee.pengguna, 403)):
        client.force_login(orang)
        assert client.get(url).status_code == kode
    client.force_login(buat_pengguna("Orang"))
    assert client.get(url).status_code == 403


def test_halaman_perumusan_untuk_ketua_dapat_diubah(client, audit, ketua):
    TujuanAudit.objects.create(kode="a", teks="Tujuan contoh")
    client.force_login(ketua.pengguna)
    resp = client.get(reverse("findings:perumusan", args=[audit.pk]))
    assert resp.context["bisa_ubah"] is True
    isi = resp.content.decode()
    assert "Kategori final per butir" in isi and "Tujuan contoh" in isi and "Teruskan kepada auditee" in isi


def test_anggota_mengusulkan_lewat_halaman(client, audit, anggota):
    client.force_login(anggota.pengguna)
    r = client.post(reverse("findings:perumusan", args=[audit.pk]), {"aksi": "usulan", "jenis": "PELUANG", "isi": "Usul"})
    assert r.status_code == 302 and Usulan.objects.filter(audit=audit).count() == 1
    r = client.post(reverse("findings:perumusan", args=[audit.pk]), {"aksi": "peluang_tambah", "uraian": "x"})
    assert r.status_code == 403  # anggota bukan ketua


def test_ketua_alur_lengkap_lewat_halaman(client, audit, ketua, penugasan_auditee):
    url = reverse("findings:perumusan", args=[audit.pk])
    client.force_login(ketua.pengguna)
    client.get(url)
    for t in audit.temuan.all():
        client.post(url, {"aksi": "uraian", "temuan": t.pk, "uraian": f"Uraian {t.pk}"})
    client.post(url, {"aksi": "kesimpulan", "skor_a": "3", "skor_b": "3", "skor_c": "3",
                      "penjelasan_a": "a", "penjelasan_b": "b", "penjelasan_c": "c"})
    r = client.post(url, {"aksi": "ajukan", "checklist": list(CHECKLIST_KETUA)})
    assert r.status_code == 302
    assert segarkan(audit).status == S.MENUNGGU_PERSETUJUAN

    client.force_login(penugasan_auditee.pengguna)
    url_p = reverse("findings:persetujuan", args=[audit.pk])
    resp = client.get(url_p)
    assert resp.status_code == 200 and resp.context["bisa_putuskan"] is True
    assert resp.context["nilai_auditor"] == []  # skor per auditor baru terbuka setelah Final
    assert client.get(reverse("audits:perbedaan", args=[audit.pk])).status_code == 403
    client.post(url_p, {"aksi": "setuju", "checklist": list(CHECKLIST_AUDITEE)})
    assert segarkan(audit).status == S.FINAL
    resp = client.get(url_p)
    assert len(resp.context["nilai_auditor"]) == 3
    assert client.get(reverse("audits:perbedaan", args=[audit.pk])).status_code == 200
    assert client.get(reverse("findings:ptk", args=[audit.pk])).status_code == 200


def test_auditee_belum_melihat_hasil_saat_perumusan(client, audit, penugasan_auditee):
    client.force_login(penugasan_auditee.pengguna)
    assert client.get(reverse("findings:persetujuan", args=[audit.pk])).status_code == 403
    assert client.get(reverse("findings:ptk", args=[audit.pk])).status_code == 403


def test_isi_ptk_lewat_halaman(client, audit, ketua, penugasan_auditee):
    ajukan(audit, ketua)
    layanan.setujui(segarkan(audit), penugasan_auditee, CHECKLIST_AUDITEE)
    ptk = PTK.objects.filter(audit=audit).first()
    client.force_login(penugasan_auditee.pengguna)
    r = client.post(reverse("findings:ptk", args=[audit.pk]), {
        "ptk": ptk.pk, "akar_masalah": "a", "rencana_tindakan": "r", "target_tanggal": "2026-06-30", "pic": "p",
    })
    assert r.status_code == 302
    ptk.refresh_from_db()
    assert ptk.status == PTK.Status.DIRENCANAKAN
    client.force_login(ketua.pengguna)
    r = client.post(reverse("findings:ptk", args=[audit.pk]), {"ptk": ptk.pk, "akar_masalah": "ubah"})
    assert r.status_code == 403


# --- Data contoh ----------------------------------------------------------------------------

def test_isi_data_contoh_tujuan_audit(settings):
    settings.DEBUG = True
    call_command("isi_data_contoh")
    call_command("isi_data_contoh")  # idempoten
    assert list(TujuanAudit.objects.values_list("kode", flat=True)) == list("abcdef")


def test_isi_data_contoh_ditolak_di_produksi(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("isi_data_contoh")
