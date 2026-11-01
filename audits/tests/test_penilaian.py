"""Penilaian auditor, rekonsiliasi, Audit Lapangan: FR-25 s.d. FR-31, BR-02 s.d. BR-13, NFR-05, NFR-08."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.peran import Peran
from audits import penilaian as layanan
from audits import ser
from audits.layanan import simpan_audit
from audits.models import Audit, HasilPerhitungan, KategoriFinal, Penilaian
from masterdata.models import PernyataanStandar, TipeUnit

from .conftest import buat_pengguna

pytestmark = pytest.mark.django_db
S = Audit.Status
SKOR = {1: "KTS", 2: "OB", 3: "SESUAI", 4: "PELAMPAUAN"}


@pytest.fixture
def audit(tim, admin_lpm, standar, auditee):
    for i in (2, 3, 4):
        p = PernyataanStandar.objects.create(standar=standar, kode=f"1.{i}", pernyataan=f"Butir 1.{i}", urutan=i)
        p.tipe_unit.set([TipeUnit.PRODI_S1])
    audit = simpan_audit(**tim, oleh=admin_lpm)
    ser.pastikan_jawaban(audit)
    for b in audit.pernyataan_berlaku():
        ser.simpan_isian(audit, b.pk, f"Penjelasan {b.kode}", 1, auditee, kategori="SESUAI")
        ser.tambah_tautan(audit, b.pk, "https://drive.google.com/file/d/x/view", auditee)
    ser.kirim(audit, auditee)
    audit.refresh_from_db()
    return audit


@pytest.fixture
def butir(audit):
    return list(audit.pernyataan_berlaku())


@pytest.fixture
def tim_auditor(audit):
    return layanan.tim_auditor(audit)  # ketua (Ani) di urutan pertama


def segarkan(audit):
    return Audit.objects.get(pk=audit.pk)


def isi(audit, penugasan, skor, butir, kunci=True):
    """skor: daftar skor 1–4 sesuai urutan butir; None = lewati."""
    layanan.pastikan_penilaian(audit, penugasan.pengguna)
    for b, s in zip(butir, skor):
        if s is None:
            continue
        p = audit.penilaian.get(auditor=penugasan.pengguna, pernyataan=b)
        kondisi = "Kondisi faktual" if s in (1, 2) else ""
        layanan.simpan_penilaian(segarkan(audit), penugasan, b.pk, SKOR[s], f"Dasar {b.kode}", kondisi, p.versi)
    if kunci:
        penugasan.refresh_from_db()
        layanan.kunci(segarkan(audit), penugasan, penugasan.pengguna)


def contoh_brd(audit, tim_auditor, butir):
    # BRD Bab 6 / tes scoring: N = 75; 87,5; 68,75
    isi(audit, tim_auditor[0], [3, 3, 4, 2], butir)
    isi(audit, tim_auditor[1], [3, 4, 4, 3], butir)
    isi(audit, tim_auditor[2], [3, 3, 3, 2], butir)
    return segarkan(audit)


# --- Alur utama dan rumus ------------------------------------------------------------

def test_contoh_brd_sampai_keputusan_audit_lapangan(audit, tim_auditor, butir):
    audit = contoh_brd(audit, tim_auditor, butir)
    assert audit.status == S.PERLU_AUDIT_LAPANGAN  # D 18,75 > 10 dan NE ≥ 75 (BR-08)
    h = audit.hasil_tahap(HasilPerhitungan.Tahap.AWAL)
    nilai = {int(k): Decimal(v) for k, v in h.nilai_auditor.items()}
    assert [nilai[t.pengguna_id] for t in tim_auditor] == [Decimal("75.00"), Decimal("87.50"), Decimal("68.75")]
    assert h.deviasi == Decimal("18.75")
    assert h.rata_rata == Decimal("77.08")
    assert h.ne == Decimal("77.03")  # 925/12 − 0,3 + 0,25
    assert (h.jumlah_kts, h.jumlah_ob, h.jumlah_kelebihan) == (0, 1, 1)
    assert h.memenuhi_kkm and h.perlu_audit_lapangan and h.deviasi_tinggi
    assert h.parameter["kkm"] == "75.00" and h.parameter["skor"]["PELAMPAUAN"] == 4
    final = {k.pernyataan.kode: k.kategori for k in audit.kategori_final.select_related("pernyataan")}
    assert final == {"1.1": "SESUAI", "1.2": "SESUAI", "1.3": "PELAMPAUAN", "1.4": "OB"}


def test_tanpa_deviasi_langsung_perumusan_temuan(audit, tim_auditor, butir):
    for t in tim_auditor:
        isi(audit, t, [3, 3, 3, 3], butir)
    audit = segarkan(audit)
    assert audit.status == S.PERUMUSAN_TEMUAN
    h = audit.hasil_tahap(HasilPerhitungan.Tahap.AWAL)
    assert (h.deviasi, h.ne, h.perlu_audit_lapangan) == (Decimal("0.00"), Decimal("75.00"), False)


def test_deviasi_tinggi_tetapi_ne_di_bawah_kkm_tanpa_audit_lapangan(audit, tim_auditor, butir):
    # BR-07: D > 10 tetapi NE < 75 → Perumusan Temuan, deviasi tetap ditandai
    isi(audit, tim_auditor[0], [1, 1, 1, 1], butir)
    isi(audit, tim_auditor[1], [3, 3, 3, 3], butir)
    isi(audit, tim_auditor[2], [1, 1, 1, 1], butir)
    audit = segarkan(audit)
    h = audit.hasil_tahap(HasilPerhitungan.Tahap.AWAL)
    assert audit.status == S.PERUMUSAN_TEMUAN
    assert h.deviasi_tinggi and not h.memenuhi_kkm and not h.perlu_audit_lapangan


def test_ambang_dari_pengaturan_periode(audit, tim_auditor, butir, periode):
    periode.pengaturan.ambang_deviasi = Decimal("20")
    periode.pengaturan.save()
    audit = contoh_brd(audit, tim_auditor, butir)
    assert audit.status == S.PERUMUSAN_TEMUAN  # D 18,75 tidak > 20


def test_status_rekonsiliasi_belum_tercapai_sebelum_semua_mengunci(audit, tim_auditor, butir):
    isi(audit, tim_auditor[0], [3, 3, 3, 3], butir)
    isi(audit, tim_auditor[1], [3, 3, 3, 3], butir)
    assert segarkan(audit).status == S.PENILAIAN_AUDITOR
    assert not HasilPerhitungan.objects.exists()


# --- BR-02 dan kunci -----------------------------------------------------------------

def test_kunci_ditolak_tanpa_dasar_penilaian(audit, tim_auditor, butir):
    t = tim_auditor[1]
    layanan.pastikan_penilaian(audit, t.pengguna)
    for b in butir:
        p = audit.penilaian.get(auditor=t.pengguna, pernyataan=b)
        layanan.simpan_penilaian(audit, t, b.pk, "SESUAI", "", "", p.versi)
    with pytest.raises(ValidationError, match="4 butir"):
        layanan.kunci(audit, t, t.pengguna)
    assert layanan.ringkasan(audit, t)[0][1] == ["dasar penilaian"]


def test_kts_ob_wajib_kondisi_faktual(audit, tim_auditor, butir):
    t = tim_auditor[1]
    isi(audit, t, [3, 3, 3, None], butir, kunci=False)
    p = audit.penilaian.get(auditor=t.pengguna, pernyataan=butir[3])
    layanan.simpan_penilaian(audit, t, butir[3].pk, "KTS", "Dasar", "", p.versi)
    assert layanan.ringkasan(audit, t) == [(butir[3], ["kondisi faktual"])]


def test_penilaian_terkunci_tidak_bisa_diubah(audit, tim_auditor, butir):
    t = tim_auditor[1]
    isi(audit, t, [3, 3, 3, 3], butir)
    t.refresh_from_db()
    p = audit.penilaian.get(auditor=t.pengguna, pernyataan=butir[0])
    with pytest.raises(layanan.PenilaianTerkunci):
        layanan.simpan_penilaian(audit, t, butir[0].pk, "KTS", "x", "y", p.versi)


def test_konflik_versi_penilaian(audit, tim_auditor, butir):
    t = tim_auditor[1]
    layanan.pastikan_penilaian(audit, t.pengguna)
    layanan.simpan_penilaian(audit, t, butir[0].pk, "SESUAI", "A", "", 1)
    with pytest.raises(layanan.KonflikVersi):
        layanan.simpan_penilaian(audit, t, butir[0].pk, "OB", "B", "C", 1)


def test_penilaian_belum_dibuka_sebelum_ser_dikirim(tim, admin_lpm, auditor):
    audit = simpan_audit(**tim, oleh=admin_lpm)
    with pytest.raises(layanan.PenilaianTerkunci):
        layanan.simpan_penilaian(audit, audit.penugasan.get(pengguna=auditor[0]), audit.pernyataan_berlaku()[0].pk, "SESUAI", "x", "", 1)


# --- Butir tidak berlaku (BR-03) -----------------------------------------------------

def test_butir_tidak_berlaku_keluar_dari_pembagi(audit, tim_auditor, butir):
    layanan.tandai_tidak_berlaku(audit, tim_auditor[0], butir[3].pk, "Unit tidak menyelenggarakan kegiatan ini")
    for t in tim_auditor:
        isi(audit, t, [4, 4, 3, None], butir)  # butir 1.4 tidak perlu dinilai
    h = segarkan(audit).hasil_tahap(HasilPerhitungan.Tahap.AWAL)
    assert h.jumlah_butir == 3
    assert set(h.nilai_auditor.values()) == {"91.67"}  # 11 / (4×3) × 100


def test_hanya_ketua_menandai_tidak_berlaku(audit, tim_auditor, butir):
    with pytest.raises(PermissionError):
        layanan.tandai_tidak_berlaku(audit, tim_auditor[1], butir[0].pk, "x")


def test_batal_tidak_berlaku_membuka_kunci_auditor_yang_belum_menilai(audit, tim_auditor, butir):
    layanan.tandai_tidak_berlaku(audit, tim_auditor[0], butir[3].pk, "alasan")
    isi(audit, tim_auditor[1], [3, 3, 3, None], butir)
    layanan.batal_tidak_berlaku(audit, tim_auditor[0], butir[3].pk)
    tim_auditor[1].refresh_from_db()
    assert tim_auditor[1].dikunci_pada is None
    assert layanan.ringkasan(audit, tim_auditor[1])[0][0] == butir[3]


# --- Butir seri (BR-13) ----------------------------------------------------------------

def test_butir_seri_menunggu_ketua_lalu_dihitung(audit, tim_auditor, butir):
    isi(audit, tim_auditor[0], [1, 3, 3, 3], butir)
    isi(audit, tim_auditor[1], [2, 3, 3, 3], butir)
    isi(audit, tim_auditor[2], [3, 3, 3, 3], butir)
    audit = segarkan(audit)
    assert audit.status == S.REKONSILIASI
    assert [k.pernyataan for k in layanan.butir_seri(audit)] == [butir[0]]
    with pytest.raises(ValidationError, match="Alasan"):
        layanan.tetapkan_seri(audit, tim_auditor[0], butir[0].pk, "OB", "")
    with pytest.raises(PermissionError):
        layanan.tetapkan_seri(audit, tim_auditor[1], butir[0].pk, "OB", "x")
    layanan.tetapkan_seri(audit, tim_auditor[0], butir[0].pk, "OB", "Dokumen ada tetapi belum lengkap")
    audit = segarkan(audit)
    assert audit.status == S.PERUMUSAN_TEMUAN
    k = audit.kategori_final.get(pernyataan=butir[0])
    assert (k.kategori, k.cara) == ("OB", KategoriFinal.Cara.KETUA)
    assert audit.hasil_tahap(HasilPerhitungan.Tahap.AWAL).jumlah_ob == 1


# --- Independensi dan akses (BR-04, Bab 4, NFR-08) -------------------------------------

def test_auditor_belum_mengunci_tidak_melihat_skor_lain(client, audit, tim_auditor, butir):
    isi(audit, tim_auditor[1], [3, 3, 3, 3], butir)
    client.force_login(tim_auditor[2].pengguna)
    resp = client.get(reverse("audits:penilaian", args=[audit.pk]))
    assert resp.status_code == 200
    assert resp.context["lihat_lain"] is False and list(resp.context["penilaian_lain"]) == []
    assert "Dasar 1.1" not in resp.content.decode()
    assert client.get(reverse("audits:perbedaan", args=[audit.pk])).status_code == 403


def test_auditor_melihat_kategori_auditee_sejak_awal(client, audit, tim_auditor, butir):
    # BR-01 (revisi 31 Okt 2026): auditor mencocokkan pilihan auditee dengan bukti sebelum menilai.
    client.force_login(tim_auditor[2].pengguna)
    resp = client.get(reverse("audits:penilaian", args=[audit.pk]) + f"?butir={butir[0].pk}")
    assert resp.status_code == 200
    isi_halaman = resp.content.decode()
    assert "Kategori pilihan auditee" in isi_halaman and "Sesuai" in isi_halaman


def test_kategori_auditee_tidak_memengaruhi_nilai(audit, tim_auditor, butir):
    # Bab 6: N, D, NE hanya dari penilaian auditor.
    for t in tim_auditor:
        isi(audit, t, [3, 3, 3, 3], butir)
    sebelum = layanan.hitung(segarkan(audit), HasilPerhitungan.Tahap.AWAL)
    audit.jawaban_ser.update(kategori="KTS")
    sesudah = layanan.hitung(segarkan(audit), HasilPerhitungan.Tahap.AWAL)
    assert (sesudah.rata_rata, sesudah.deviasi, sesudah.ne) == (sebelum.rata_rata, sebelum.deviasi, sebelum.ne)


def test_ketua_juga_baru_melihat_setelah_mengunci(client, audit, tim_auditor, butir):
    # Keputusan 31 Okt 2026 (BR-04 diutamakan atas tabel Bab 4)
    isi(audit, tim_auditor[1], [3, 3, 3, 3], butir)
    client.force_login(tim_auditor[0].pengguna)
    assert client.get(reverse("audits:perbedaan", args=[audit.pk])).status_code == 403
    isi(audit, tim_auditor[0], [3, 3, 3, 3], butir)
    assert client.get(reverse("audits:perbedaan", args=[audit.pk])).status_code == 200


def test_auditor_setelah_mengunci_melihat_tabel_perbedaan(client, audit, tim_auditor, butir):
    audit = contoh_brd(audit, tim_auditor, butir)
    client.force_login(tim_auditor[2].pengguna)
    resp = client.get(reverse("audits:perbedaan", args=[audit.pk]))
    assert resp.status_code == 200
    berbeda = [r["butir"].kode for r in resp.context["baris"] if r["berbeda"]]
    assert berbeda == ["1.2", "1.3", "1.4"]  # BR-09


def test_admin_lpm_melihat_perbedaan_kapan_saja(client, audit, admin_lpm):
    client.force_login(admin_lpm)
    assert client.get(reverse("audits:perbedaan", args=[audit.pk])).status_code == 200


def test_auditee_tidak_bisa_membuka_penilaian(client, audit, auditee):
    client.force_login(auditee)
    assert client.get(reverse("audits:penilaian", args=[audit.pk])).status_code == 403
    assert client.get(reverse("audits:perbedaan", args=[audit.pk])).status_code == 403


def test_endpoint_simpan_dan_terkunci(client, audit, tim_auditor, butir):
    t = tim_auditor[1]
    client.force_login(t.pengguna)
    client.get(reverse("audits:penilaian", args=[audit.pk]))
    url = reverse("audits:penilaian_simpan", args=[audit.pk, butir[0].pk])
    r = client.post(url, {"kategori": "OB", "dasar_penilaian": "Dasar", "kondisi_faktual": "", "versi": 1})
    assert r.status_code == 200 and r.json()["lengkap"] is False  # OB tanpa kondisi faktual
    assert client.post(url, {"kategori": "X", "dasar_penilaian": "", "versi": 2}).status_code == 400
    isi(audit, t, [3, 3, 3, 3], butir)
    assert client.post(url, {"kategori": "KTS", "dasar_penilaian": "x", "versi": 99}).status_code == 423


def test_hasil_hanya_untuk_ketua_dan_admin(client, audit, tim_auditor, butir, admin_lpm):
    audit = contoh_brd(audit, tim_auditor, butir)
    for orang, ada in ((tim_auditor[0].pengguna, True), (admin_lpm, True), (tim_auditor[1].pengguna, False)):
        client.force_login(orang)
        resp = client.get(reverse("audits:detail", args=[audit.pk]))
        assert bool(resp.context["hasil"]) is ada


def test_halaman_kunci_dan_rekonsiliasi_tampil(client, audit, tim_auditor, butir):
    client.force_login(tim_auditor[0].pengguna)
    assert client.get(reverse("audits:penilaian_kunci", args=[audit.pk])).status_code == 200
    assert client.get(reverse("audits:rekonsiliasi", args=[audit.pk])).status_code == 200
    client.force_login(tim_auditor[1].pengguna)
    assert client.get(reverse("audits:rekonsiliasi", args=[audit.pk])).status_code == 403


# --- Audit Lapangan opsi b (FR-29, FR-30, BR-12) --------------------------------------

def test_audit_lapangan_revisi_lalu_hitung_ulang(client, audit, tim_auditor, butir):
    audit = contoh_brd(audit, tim_auditor, butir)
    penyumbang = layanan.butir_penyumbang(audit)
    assert [b.kode for b in penyumbang] == ["1.2", "1.3", "1.4"]

    with pytest.raises(PermissionError):
        layanan.buka_revisi_al(audit, tim_auditor[1], [b.pk for b in penyumbang])
    layanan.buka_revisi_al(audit, tim_auditor[0], [b.pk for b in penyumbang])
    audit = segarkan(audit)
    assert audit.revisi_al_dibuka and all(t.dikunci_pada is None for t in layanan.tim_auditor(audit))

    with pytest.raises(ValidationError, match="belum mengunci"):
        layanan.selesaikan_al(audit, tim_auditor[0], "catatan")

    # Butir yang tidak dibuka (1.1) tetap terkunci
    t = audit.penugasan.get(pk=tim_auditor[1].pk)
    p = audit.penilaian.get(auditor=t.pengguna, pernyataan=butir[0])
    with pytest.raises(layanan.PenilaianTerkunci, match="tidak dapat dinilai"):
        layanan.simpan_penilaian(audit, t, butir[0].pk, "KTS", "x", "y", p.versi)

    # Setelah AL, auditor menyamakan penilaian: semua Sesuai kecuali 1.3 Pelampauan
    for t in layanan.tim_auditor(audit):
        isi(audit, t, [None, 3, 4, 3], butir)
    audit = segarkan(audit)
    assert not audit.revisi_al_dibuka and audit.status == S.PERLU_AUDIT_LAPANGAN

    with pytest.raises(ValidationError, match="wajib"):
        layanan.selesaikan_al(audit, tim_auditor[0], "  ")
    layanan.selesaikan_al(audit, tim_auditor[0], "Bukti 1.4 terverifikasi lengkap saat kunjungan.")
    audit = segarkan(audit)
    assert audit.status == S.PERUMUSAN_TEMUAN
    awal = audit.hasil_tahap(HasilPerhitungan.Tahap.AWAL)
    setelah = audit.hasil_tahap(HasilPerhitungan.Tahap.SETELAH_AL)
    assert awal.ne == Decimal("77.03")  # NE awal tetap tersimpan (BR-12)
    assert setelah.deviasi == Decimal("0.00")
    assert setelah.ne == Decimal("81.50")  # 13/16×100 = 81,25 + 0,25
    assert audit.catatan_follow_up.startswith("Bukti 1.4")

    client.force_login(tim_auditor[0].pengguna)
    assert client.get(reverse("audits:audit_lapangan", args=[audit.pk])).status_code == 200


def test_halaman_audit_lapangan_untuk_ketua_dan_admin(client, audit, tim_auditor, butir, admin_lpm, periode):
    periode.cp_lpm = buat_pengguna("CPLPM", peran=Peran.ADMIN, telepon="0812")
    periode.save()
    audit = contoh_brd(audit, tim_auditor, butir)
    client.force_login(admin_lpm)
    isi_halaman = client.get(reverse("audits:audit_lapangan", args=[audit.pk])).content.decode()
    assert "CPLPM" in isi_halaman and "0812" in isi_halaman
    detail = client.get(reverse("audits:detail", args=[audit.pk])).content.decode()
    assert "Perlu Audit Lapangan" in detail and "CPLPM" in detail
    client.force_login(tim_auditor[1].pengguna)
    assert client.get(reverse("audits:audit_lapangan", args=[audit.pk])).status_code == 403


def test_buka_revisi_lewat_halaman(client, audit, tim_auditor, butir):
    audit = contoh_brd(audit, tim_auditor, butir)
    client.force_login(tim_auditor[0].pengguna)
    r = client.post(reverse("audits:audit_lapangan", args=[audit.pk]), {"aksi": "buka_revisi", "butir": [butir[3].pk]})
    assert r.status_code == 302
    assert segarkan(audit).butir_revisi_al == [butir[3].pk]


# --- Reset kunci (Bab 4) -----------------------------------------------------------------

def test_reset_kunci_saat_rekonsiliasi(audit, tim_auditor, butir):
    isi(audit, tim_auditor[0], [1, 3, 3, 3], butir)
    isi(audit, tim_auditor[1], [2, 3, 3, 3], butir)
    isi(audit, tim_auditor[2], [3, 3, 3, 3], butir)
    audit = segarkan(audit)
    master = buat_pengguna("Kepala", peran=Peran.MASTER_ADMIN)
    with pytest.raises(ValidationError, match="Alasan"):
        layanan.reset_kunci(audit, tim_auditor[2], master, "")
    layanan.reset_kunci(audit, audit.penugasan.get(pk=tim_auditor[2].pk), master, "Salah pilih kategori 1.1")
    audit = segarkan(audit)
    assert audit.status == S.PENILAIAN_AUDITOR
    assert not audit.kategori_final.exists()
    assert audit.riwayat_status.last().ke == S.PENILAIAN_AUDITOR


@pytest.mark.parametrize("peran, status", [(Peran.MASTER_ADMIN, 200), (Peran.ADMIN, 403)])
def test_reset_kunci_hanya_master_admin(client, audit, tim_auditor, butir, peran, status):
    isi(audit, tim_auditor[1], [3, 3, 3, 3], butir)
    client.force_login(buat_pengguna("Uji", peran=peran))
    assert client.get(reverse("audits:reset_kunci", args=[audit.pk, tim_auditor[1].pk])).status_code == status


def test_buka_kunci_ser_mereset_kunci_auditor(audit, tim_auditor, butir):
    isi(audit, tim_auditor[1], [3, 3, 3, 3], butir)
    ser.buka_kunci(audit, buat_pengguna("Kepala", peran=Peran.MASTER_ADMIN), "Revisi SER")
    tim_auditor[1].refresh_from_db()
    assert tim_auditor[1].dikunci_pada is None
    assert Penilaian.objects.filter(auditor=tim_auditor[1].pengguna).exclude(kategori="").count() == 4  # draf tetap
