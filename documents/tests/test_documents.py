"""Nomor surat, dokumen PDF di antrean, unduhan, dan scan: FR-39 s.d. FR-43, BR-15, BR-16, NFR-03, NFR-08."""

import io
from datetime import date
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.urls import reverse

from accounts.peran import Peran
from audits import penilaian as penilaian_layanan
from audits.models import Audit, HasilPerhitungan
from audits.tests.conftest import buat_pengguna
from documents import nomor as layanan_nomor
from documents import sinyal, tugas
from documents.konteks import konteks
from documents.models import Dokumen, JenisDokumen, NomorSurat, PengaturanDokumen, PolaNomorSurat, periksa_pola
from documents.pdf import PDFTidakTersedia
from findings import layanan as findings
from masterdata.models import KategoriSurat

from .conftest import PDF_UJI

pytestmark = pytest.mark.django_db
S = Audit.Status
POLA = "{nomor}/LPM/{kategori}/{bulan_romawi}/{tahun}"
CHECKLIST_KETUA = {k for k, _ in findings.CHECKLIST_KETUA}
CHECKLIST_AUDITEE = {k for k, _ in findings.CHECKLIST_AUDITEE}


KODE_JENIS = {JenisDokumen.PTK: "PTK", JenisDokumen.LAPORAN_AMI: "LAP", JenisDokumen.BERITA_ACARA: "BA"}


@pytest.fixture
def pola_umum(db):
    return {j: PolaNomorSurat.objects.create(jenis=j, pola=f"{{nomor}}/{k}/{{kategori}}/{{bulan_romawi}}/{{tahun}}") for j, k in KODE_JENIS.items()}


def test_pola_identik_antar_jenis_ditolak(pola_umum):
    p = PolaNomorSurat(jenis=JenisDokumen.LAPORAN_AMI, pola=pola_umum[JenisDokumen.PTK].pola)
    with pytest.raises(ValidationError, match="pembeda"):
        p.clean()


def test_nomor_bentrok_tidak_menggagalkan_dan_tidak_membuang_nomor(audit, ketua):
    PolaNomorSurat.objects.create(jenis=JenisDokumen.PTK, pola="{nomor}/SAMA")
    PolaNomorSurat.objects.create(jenis=JenisDokumen.LAPORAN_AMI, pola="{nomor}/SAMA")  # salah konfigurasi
    audit = lengkapi_dan_ajukan(audit, ketua)
    assert audit.status == S.MENUNGGU_PERSETUJUAN
    assert sorted(audit.nomor_surat.values_list("teks", flat=True)) == ["001/SAMA", "002/SAMA"]
    # Penghitung Laporan tidak naik karena penerbitannya dibatalkan.
    assert not PolaNomorSurat.objects.get(jenis="LAPORAN_AMI").penghitung.filter(terakhir__gt=0).exists()


def segarkan(audit):
    return Audit.objects.select_related("unit__kategori_surat", "unit__induk").get(pk=audit.pk)


def lengkapi_dan_ajukan(audit, ketua):
    findings.sinkron_temuan(audit)
    for t in audit.temuan.all():
        findings.simpan_uraian(audit, ketua, t, f"Uraian {t}")
    findings.simpan_kesimpulan(
        audit, ketua, {"skor_a": 3, "skor_b": 3, "skor_c": 3, "penjelasan_a": "a", "penjelasan_b": "b", "penjelasan_c": "c"}, []
    )
    findings.ajukan_ke_auditee(audit, ketua, CHECKLIST_KETUA)
    return segarkan(audit)


def jadikan_final(audit, ketua, auditee):
    audit = lengkapi_dan_ajukan(audit, ketua)
    findings.setujui(audit, auditee, CHECKLIST_AUDITEE)
    return segarkan(audit)


# --- Pola dan penerbitan nomor (FR-39, BR-15) --------------------------------------------

def test_render_pola(prodi, fakultas):
    prodi.kategori_surat = KategoriSurat.objects.create(nama="Prodi A", kode="PA")
    teks = layanan_nomor.render_pola(POLA + "/{kode_unit}/{kode_fakultas}", 7, date(2026, 3, 5), prodi)
    assert teks == "007/LPM/PA/III/2026/TE/FT"


@pytest.mark.parametrize("pola, pesan", [("{nomor}/{rahasia}", "tidak dikenal"), ("LPM/{tahun}", "wajib memuat"), ("{nomor", "tidak valid")])
def test_pola_tidak_valid_ditolak(pola, pesan):
    with pytest.raises(ValidationError, match=pesan):
        periksa_pola(pola)


def test_nomor_urut_per_pola_dan_direset_per_tahun(audit, pola_umum):
    a = layanan_nomor.terbitkan(audit, JenisDokumen.LAPORAN_AMI)
    assert a.teks.startswith("001/LAP/-/") and a.nomor_urut == 1
    assert layanan_nomor.terbitkan(audit, JenisDokumen.LAPORAN_AMI) == a  # idempoten
    b = layanan_nomor.terbitkan(audit, JenisDokumen.BERITA_ACARA)
    assert b.nomor_urut == 1  # pola lain, penghitung sendiri
    a.status = NomorSurat.Status.BATAL
    a.save()
    with mock.patch("documents.nomor.timezone.localdate", return_value=date(2027, 1, 2)):
        c = layanan_nomor.terbitkan(audit, JenisDokumen.LAPORAN_AMI)
    assert (c.nomor_urut, c.tahun) == (1, 2027) and c.teks.endswith("/I/2027")


def test_pola_khusus_kategori_unit_didahulukan(audit, pola_umum):
    kategori = KategoriSurat.objects.create(nama="Prodi A", kode="PA")
    PolaNomorSurat.objects.create(jenis=JenisDokumen.LAPORAN_AMI, kategori=kategori, pola="LAP-{nomor}/{kategori}")
    audit.unit.kategori_surat = kategori
    audit.unit.save()
    assert layanan_nomor.terbitkan(segarkan(audit), JenisDokumen.LAPORAN_AMI).teks == "LAP-001/PA"


def test_tanpa_pola_tidak_menghalangi_alur(audit, ketua):
    audit = lengkapi_dan_ajukan(audit, ketua)
    assert audit.status == S.MENUNGGU_PERSETUJUAN
    assert not NomorSurat.objects.exists()
    assert layanan_nomor.terbitkan_untuk_audit(audit) == ["Laporan AMI", "PTK"]


def test_nomor_terbit_saat_diteruskan_ke_auditee(audit, ketua, pola_umum):
    audit = lengkapi_dan_ajukan(audit, ketua)
    nomor = list(audit.nomor_surat.order_by("jenis", "ptk__nomor_urut"))
    assert [(n.jenis, n.nomor_urut) for n in nomor] == [("LAPORAN_AMI", 1), ("PTK", 1), ("PTK", 2)]
    ptk = audit.ptk.get(nomor_urut=1)
    assert ptk.nomor_surat == ptk.nomor_surat_set.get().teks
    assert not audit.nomor_surat.filter(jenis=JenisDokumen.BERITA_ACARA).exists()  # tanpa Audit Lapangan


def test_nomor_ptk_batal_setelah_keberatan_tidak_dipakai_ulang(audit, ketua, penugasan_auditee, pola_umum):
    audit = lengkapi_dan_ajukan(audit, ketua)
    findings.ajukan_keberatan(audit, penugasan_auditee, "Butir 1.4 sudah sesuai")
    audit = segarkan(audit)
    findings.tanggapi_keberatan(audit, ketua, "Diterima")
    findings.ubah_kategori_final(audit, ketua, audit.pernyataan_berlaku().get(kode="1.4").pk, "SESUAI", "SOP ada")
    findings.ajukan_ke_auditee(audit, ketua, CHECKLIST_KETUA)
    ptk_nomor = audit.nomor_surat.filter(jenis=JenisDokumen.PTK).order_by("nomor_urut")
    assert [(n.nomor_urut, n.status) for n in ptk_nomor] == [(1, "AKTIF"), (2, "BATAL")]
    # Nomor 2 yang batal tidak dipakai ulang: penerbitan PTK berikutnya mulai dari 3.
    assert pola_umum[JenisDokumen.PTK].penghitung.get().terakhir == 2
    ptk_baru = audit.ptk.get()
    ptk_baru.nomor_surat_set.update(status=NomorSurat.Status.BATAL)
    assert layanan_nomor.terbitkan(audit, JenisDokumen.PTK, ptk_baru).nomor_urut == 3


def test_koreksi_nomor_sebelum_final_dan_terkunci_sesudahnya(audit, ketua, penugasan_auditee, pola_umum, admin_lpm):
    audit = lengkapi_dan_ajukan(audit, ketua)
    n1, n2 = audit.nomor_surat.filter(jenis=JenisDokumen.PTK).order_by("nomor_urut")
    with pytest.raises(ValidationError, match="Alasan"):
        layanan_nomor.koreksi(n1, "123/LPM/X", "", admin_lpm)
    with pytest.raises(ValidationError, match="sudah dipakai"):
        layanan_nomor.koreksi(n1, n2.teks, "salah ketik", admin_lpm)
    layanan_nomor.koreksi(n1, "123/LPM/X", "Menyesuaikan buku agenda", admin_lpm)
    n1.refresh_from_db()
    assert n1.teks == "123/LPM/X" and n1.ptk.nomor_surat == "123/LPM/X"
    findings.setujui(segarkan(audit), penugasan_auditee, CHECKLIST_AUDITEE)
    n1.refresh_from_db()
    with pytest.raises(ValidationError, match="terkunci"):
        layanan_nomor.koreksi(n1, "999", "x", admin_lpm)


# --- Pembuatan dokumen di antrean (FR-40, FR-41, NFR-03) ---------------------------------

def test_profil_auditee_diantre_saat_diplot(audit_dinilai):
    d = Dokumen.objects.get(audit=audit_dinilai, jenis=JenisDokumen.PROFIL_AUDITEE)
    assert d.status == Dokumen.Status.DIANTRE and not d.berkas


def test_paket_final_dibuat_lewat_antrean(audit, ketua, penugasan_auditee, pola_umum, pdf_palsu, django_capture_on_commit_callbacks):
    terkirim = []
    sinyal.paket_final_siap.connect(lambda sender, audit, **kw: terkirim.append(audit.pk), weak=False, dispatch_uid="uji")
    try:
        with django_capture_on_commit_callbacks(execute=True):
            audit = jadikan_final(audit, ketua, penugasan_auditee)
    finally:
        sinyal.paket_final_siap.disconnect(dispatch_uid="uji")
    dokumen = {(d.jenis, d.ptk_id): d for d in Dokumen.objects.filter(audit=audit)}
    jenis = sorted(j for j, _ in dokumen)
    assert jenis == sorted(["DAFTAR_TILIK", "LAPORAN_AMI", "PROFIL_AUDITEE", "PTK", "PTK", "TEMUAN"])
    assert all(d.status == Dokumen.Status.SIAP and d.berkas for d in dokumen.values())
    tilik = dokumen[("DAFTAR_TILIK", None)]
    assert tilik.berkas.read() == PDF_UJI and tilik.berkas_excel
    assert audit.pk in terkirim  # FR-42: siap dikirim email oleh notifications


def test_berita_acara_hanya_bila_ada_audit_lapangan(audit):
    assert JenisDokumen.BERITA_ACARA not in tugas.jenis_paket_final(audit)
    penilaian_layanan.hitung(audit, HasilPerhitungan.Tahap.SETELAH_AL)
    assert JenisDokumen.BERITA_ACARA in tugas.jenis_paket_final(audit)


def test_tanpa_kts_ob_tidak_ada_dokumen_ptk(audit_dinilai, pdf_palsu):
    from findings.tests.conftest import nilai_semua

    audit = nilai_semua(audit_dinilai, [[3, 3, 3, 4]] * 3)
    ketua = audit.penugasan.get(ketua=True)
    audit = jadikan_final(audit, ketua, audit.penugasan.get(peran="AUDITEE"))
    assert not Dokumen.objects.filter(audit=audit, jenis=JenisDokumen.PTK).exists()
    isi = render_to_string(tugas.TEMPLATE[JenisDokumen.LAPORAN_AMI], konteks(Dokumen.objects.get(audit=audit, jenis="LAPORAN_AMI")))
    assert "Tidak ada temuan KTS/OB" in isi  # BR-16


def test_render_gagal_dicatat(audit_dinilai, django_capture_on_commit_callbacks):
    d = Dokumen.objects.get(audit=audit_dinilai, jenis=JenisDokumen.PROFIL_AUDITEE)
    with mock.patch("documents.tugas.render_pdf", side_effect=PDFTidakTersedia("Pango tidak ditemukan")):
        # Galat dilempar ulang agar worker mencoba lagi (max_attempts); di mode sinkron sampai ke pemanggil.
        with pytest.raises(PDFTidakTersedia), django_capture_on_commit_callbacks(execute=True):
            tugas.antrekan(d)
    d.refresh_from_db()
    assert d.status == Dokumen.Status.GAGAL and "Pango" in d.galat


def test_isi_ptk_membuat_ulang_dokumen_ptk(audit, ketua, penugasan_auditee, pdf_palsu, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        audit = jadikan_final(audit, ketua, penugasan_auditee)
    ptk = audit.ptk.first()
    versi_awal = Dokumen.objects.get(ptk=ptk).versi
    with django_capture_on_commit_callbacks(execute=True):
        findings.isi_ptk(audit, penugasan_auditee, ptk, {"akar_masalah": "a", "rencana_tindakan": "r", "target_tanggal": date(2026, 6, 1), "pic": "p"})
    d = Dokumen.objects.get(ptk=ptk)
    assert d.versi == versi_awal + 1
    assert d.berkas.storage.exists(d.berkas.name)  # berkas baru tidak ikut terhapus saat dibuat ulang


@pytest.mark.parametrize("jenis", list(JenisDokumen))
def test_semua_template_dapat_dirender(audit, ketua, penugasan_auditee, pola_umum, jenis):
    PengaturanDokumen.objects.create(jenis=jenis, judul=f"Judul {jenis}", nomor_formulir="064-00/Unika/LPM/R-Q")
    audit = jadikan_final(audit, ketua, penugasan_auditee)
    ptk = audit.ptk.first() if jenis == JenisDokumen.PTK else None
    d, _ = Dokumen.objects.get_or_create(audit=audit, jenis=jenis, ptk=ptk)
    isi = render_to_string(tugas.TEMPLATE[jenis], konteks(d))
    assert "Teknik Elektro" in isi and f"Judul {jenis}" in isi
    assert 'content: "064-00/Unika/LPM/R-Q"' in isi  # nomor formulir di kaki halaman
    if jenis in (JenisDokumen.PTK, JenisDokumen.LAPORAN_AMI):
        assert d.nomor_aktif().teks in isi


def test_daftar_tilik_memuat_kategori_auditee(audit, ketua, penugasan_auditee):
    # BR-01 (revisi 31 Okt 2026): pilihan auditee tampil di samping penilaian auditor.
    from openpyxl import load_workbook

    from documents.konteks import excel_daftar_tilik

    audit = jadikan_final(audit, ketua, penugasan_auditee)
    audit.jawaban_ser.update(kategori="PELAMPAUAN")
    d = Dokumen.objects.get(audit=audit, jenis=JenisDokumen.DAFTAR_TILIK)
    isi = render_to_string(tugas.TEMPLATE[JenisDokumen.DAFTAR_TILIK], konteks(d))
    assert "Kategori auditee" in isi and "Pelampauan (4)" in isi
    ws = load_workbook(io.BytesIO(excel_daftar_tilik(audit))).active
    judul = [c.value for c in ws[3]]
    kolom = judul.index("Kategori auditee")
    assert judul[kolom + 1] == "Skor auditee"
    assert (ws.cell(4, kolom + 1).value, ws.cell(4, kolom + 2).value) == ("Pelampauan", 4)


# --- Halaman, unduhan, dan hak akses (NFR-08, Bab 4) ---------------------------------------

@pytest.fixture
def audit_final(audit, ketua, penugasan_auditee, pdf_palsu, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        return jadikan_final(audit, ketua, penugasan_auditee)


def test_unduh_sesuai_hak_akses(client, audit_final, penugasan_auditee, anggota, admin_lpm):
    d = Dokumen.objects.get(audit=audit_final, jenis=JenisDokumen.LAPORAN_AMI)
    url = reverse("documents:unduh", args=[audit_final.pk, d.pk, "pdf"])
    for orang in (penugasan_auditee.pengguna, anggota.pengguna, admin_lpm):
        client.force_login(orang)
        r = client.get(url)
        assert r.status_code == 200 and b"".join(r.streaming_content) == PDF_UJI
    for orang in (buat_pengguna("Orang"), buat_pengguna("Rektor", peran=Peran.VIEWER)):
        client.force_login(orang)
        assert client.get(url).status_code == 403
    client.logout()
    assert client.get(url).status_code == 302


def test_unduh_excel_daftar_tilik(client, audit_final, admin_lpm):
    d = Dokumen.objects.get(audit=audit_final, jenis=JenisDokumen.DAFTAR_TILIK)
    client.force_login(admin_lpm)
    r = client.get(reverse("documents:unduh", args=[audit_final.pk, d.pk, "excel"]))
    assert r.status_code == 200 and r["Content-Disposition"].endswith('.xlsx"')
    assert client.get(reverse("documents:unduh", args=[audit_final.pk, d.pk, "scan"])).status_code == 404


def test_halaman_dokumen_dan_polling(client, audit_dinilai, admin_lpm):
    client.force_login(admin_lpm)
    isi = client.get(reverse("documents:daftar", args=[audit_dinilai.pk])).content.decode()
    assert "Profil Auditee" in isi and 'hx-trigger="every 3s"' in isi  # masih diantre
    Dokumen.objects.filter(audit=audit_dinilai).update(status=Dokumen.Status.SIAP)
    r = client.get(reverse("documents:daftar", args=[audit_dinilai.pk]), HTTP_HX_REQUEST="true")
    assert "every 3s" not in r.content.decode()
    assert "<html" not in r.content.decode()  # partial untuk HTMX


def test_dokumen_tertahan_memberi_petunjuk_worker(client, audit_dinilai, admin_lpm, auditee):
    from datetime import timedelta

    from django.utils import timezone

    Dokumen.objects.filter(audit=audit_dinilai).update(diminta_pada=timezone.now() - timedelta(minutes=5))
    client.force_login(admin_lpm)
    isi = client.get(reverse("documents:daftar", args=[audit_dinilai.pk])).content.decode()
    assert "python manage.py qcluster" in isi
    client.force_login(auditee)
    isi = client.get(reverse("documents:daftar", args=[audit_dinilai.pk])).content.decode()
    assert "sedang disiapkan" in isi and "qcluster" not in isi
    Dokumen.objects.filter(audit=audit_dinilai).update(diminta_pada=timezone.now())
    client.force_login(admin_lpm)
    assert "qcluster" not in client.get(reverse("documents:daftar", args=[audit_dinilai.pk])).content.decode()


def test_buat_ulang_hanya_admin(client, audit_final, anggota, admin_lpm, pdf_palsu, django_capture_on_commit_callbacks):
    d = Dokumen.objects.get(audit=audit_final, jenis=JenisDokumen.TEMUAN)
    url = reverse("documents:buat_ulang", args=[audit_final.pk, d.pk])
    client.force_login(anggota.pengguna)
    assert client.post(url).status_code == 403
    client.force_login(admin_lpm)
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(url).status_code == 302
    d.refresh_from_db()
    assert d.versi == 2


def test_unggah_scan(client, audit_final, ketua, anggota):
    d = Dokumen.objects.get(audit=audit_final, jenis=JenisDokumen.LAPORAN_AMI)
    url = reverse("documents:unggah_scan", args=[audit_final.pk, d.pk])
    client.force_login(anggota.pengguna)
    assert client.post(url, {"scan": SimpleUploadedFile("ttd.pdf", PDF_UJI)}).status_code == 403
    client.force_login(ketua.pengguna)
    client.post(url, {"scan": SimpleUploadedFile("ttd.pdf", b"MZ bukan pdf")})
    d.refresh_from_db()
    assert not d.scan
    client.post(url, {"scan": SimpleUploadedFile("ttd.pdf", PDF_UJI)})
    d.refresh_from_db()
    assert d.scan and d.scan_oleh == ketua.pengguna
    r = client.get(reverse("documents:unduh", args=[audit_final.pk, d.pk, "scan"]))
    assert r.status_code == 200


def test_koreksi_nomor_lewat_halaman(client, audit, ketua, pola_umum, admin_lpm):
    audit = lengkapi_dan_ajukan(audit, ketua)
    n = audit.nomor_surat.filter(jenis=JenisDokumen.LAPORAN_AMI).get()
    url = reverse("documents:koreksi_nomor", args=[audit.pk, n.pk])
    client.force_login(ketua.pengguna)
    assert client.get(url).status_code == 403
    client.force_login(admin_lpm)
    r = client.post(url, {"teks": "77/LPM/LAP/2026", "alasan": "Sesuai buku agenda"})
    assert r.status_code == 302
    n.refresh_from_db()
    assert n.teks == "77/LPM/LAP/2026" and n.dikoreksi_oleh == admin_lpm


def test_terbitkan_nomor_setelah_pola_diatur(client, audit, ketua, admin_lpm):
    audit = lengkapi_dan_ajukan(audit, ketua)  # belum ada pola
    PolaNomorSurat.objects.create(jenis=JenisDokumen.PTK, pola="{nomor}/PTK/{tahun}")
    PolaNomorSurat.objects.create(jenis=JenisDokumen.LAPORAN_AMI, pola="{nomor}/LAP/{tahun}")
    client.force_login(admin_lpm)
    client.post(reverse("documents:terbitkan_nomor", args=[audit.pk]))
    assert audit.nomor_surat.filter(status="AKTIF").count() == 3
