"""Dashboard Admin, analitik (hanya audit Final), dan ekspor Excel/PDF lewat antrean.

FR-44, FR-45, FR-48 s.d. FR-51, BR-07, Bab 4, NFR-02, NFR-03, NFR-09.
"""

import io
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from openpyxl import load_workbook

from accounts.peran import Peran
from audits import analitik, grafik
from audits.dashboard import jumlah_butir_per_audit
from audits.layanan import simpan_audit
from audits.models import Audit
from audits.tests.conftest import buat_pengguna
from documents.models import Ekspor
from findings import layanan as findings
from masterdata.models import PernyataanStandar, Standar, TipeUnit

from .conftest import PDF_UJI

pytestmark = pytest.mark.django_db
CHECKLIST_KETUA = {k for k, _ in findings.CHECKLIST_KETUA}
CHECKLIST_AUDITEE = {k for k, _ in findings.CHECKLIST_AUDITEE}


def jadikan_final(audit, ketua, auditee, uraian="Uraian"):
    findings.sinkron_temuan(audit)
    for t in audit.temuan.all():
        findings.simpan_uraian(audit, ketua, t, uraian)
    findings.simpan_kesimpulan(audit, ketua, {"skor_a": 3, "skor_b": 3, "skor_c": 3, "penjelasan_a": "a",
                                              "penjelasan_b": "b", "penjelasan_c": "c"}, [])
    findings.ajukan_ke_auditee(audit, ketua, CHECKLIST_KETUA)
    findings.setujui(Audit.objects.get(pk=audit.pk), auditee, CHECKLIST_AUDITEE)
    return Audit.objects.get(pk=audit.pk)


@pytest.fixture
def audit_final(audit, ketua, penugasan_auditee):
    return jadikan_final(audit, ketua, penugasan_auditee)


@pytest.fixture
def viewer(db):
    return buat_pengguna("Rektor", peran=Peran.VIEWER)


# --- Dashboard (FR-45, BR-07, NFR-02) ---------------------------------------------------------

def test_jumlah_butir_dashboard_sama_dengan_berlaku_untuk(audit, standar, prodi, periode, lingkup, fakultas):
    turunan = Standar.objects.create(periode=periode, kode="T", nama="Turunan FT", lingkup=lingkup,
                                     sumber=Standar.Sumber.TURUNAN, unit_pengusul=fakultas)
    p = PernyataanStandar.objects.create(standar=turunan, kode="T.1", pernyataan="Turunan")
    p.tipe_unit.set([TipeUnit.PRODI_S1])
    audits = list(Audit.objects.filter(pk=audit.pk).select_related("unit").prefetch_related("lingkup"))
    assert jumlah_butir_per_audit(audits, periode)[audit.pk] == audit.pernyataan_berlaku().count() == 5


def test_dashboard_menampilkan_progres_dan_deviasi(client, audit, admin_lpm):
    client.force_login(admin_lpm)
    resp = client.get(reverse("audits:dashboard"))
    assert resp.status_code == 200
    b = resp.context["baris"][0]
    assert (b["ser_lengkap"], b["total_butir"]) == (4, 4)
    assert all(x["penugasan"].dikunci_pada for x in b["auditor"])
    assert b["hasil"].deviasi == Decimal("0.00") and not b["hasil"].deviasi_tinggi
    assert resp.context["ringkasan"]["persen_ser"] == 100
    kosong = client.get(reverse("audits:dashboard"), {"periode": audit.periode_id, "deviasi_tinggi": "on"})
    assert kosong.context["baris"] == []


@pytest.mark.parametrize("peran, kode", [(Peran.ADMIN, 200), (Peran.MASTER_ADMIN, 200), (Peran.VIEWER, 403), (Peran.PENGGUNA, 403)])
def test_akses_dashboard(client, audit, peran, kode):
    client.force_login(buat_pengguna("Uji", peran=peran))
    assert client.get(reverse("audits:dashboard")).status_code == kode


def test_dashboard_tidak_query_per_audit(client, audit, admin_lpm, tim, prodi_lain, auditor, auditee):
    client.force_login(admin_lpm)
    client.get(reverse("audits:dashboard"))  # pemanasan sesi/izin
    with CaptureQueriesContext(connection) as satu:
        client.get(reverse("audits:dashboard"))
    for i, unit in enumerate([prodi_lain]):
        simpan_audit(**{**tim, "unit": unit, "auditee": auditor[4]}, oleh=admin_lpm)
    from masterdata.models import Unit

    for i in range(3):
        u = Unit.objects.create(nama=f"Prodi {i}", kode=f"P{i}", tipe_id=TipeUnit.PRODI_S1, induk=prodi_lain.induk)
        simpan_audit(**{**tim, "unit": u, "auditee": buat_pengguna(f"Kaprodi{i}")}, oleh=admin_lpm)
    with CaptureQueriesContext(connection) as banyak:
        resp = client.get(reverse("audits:dashboard"))
    assert len(resp.context["baris"]) == 5
    assert len(banyak) <= len(satu) + 2  # bukan bertambah per audit


# --- Analitik: hanya audit Final (FR-49, FR-50) -------------------------------------------------

def test_audit_belum_final_tidak_masuk_analitik(audit, periode):
    assert not analitik.audit_final(periode).exists()
    assert analitik.per_butir(analitik.audit_final(periode), periode)["baris"] == []


def test_grafik_per_butir_dari_kategori_final(audit_final, periode):
    data = analitik.per_butir(analitik.audit_final(periode), periode)
    assert [(r["butir"].kode, r["rata"], r["n"]) for r in data["baris"]] == [
        ("1.1", Decimal("3.00"), 1), ("1.2", Decimal("4.00"), 1), ("1.3", Decimal("1.00"), 1), ("1.4", Decimal("2.00"), 1),
    ]
    assert data["baris"][2]["jumlah"]["KTS"] == 1
    svg = grafik.batang_per_butir(data["baris"], data["skor_maks"], data["skor_sesuai"])
    assert svg.startswith("<svg") and "1.3: 1.00 (n = 1)" in svg


def test_svg_meloloskan_teks(audit_final, periode):
    data = analitik.per_butir(analitik.audit_final(periode), periode)
    data["baris"][0]["butir"].kode = "<script>"
    assert "<script>" not in grafik.batang_per_butir(data["baris"], 4, 3)


def test_tren_unit(audit_final, prodi):
    baris = analitik.tren_unit(prodi)
    assert len(baris) == 1
    r = baris[0]
    assert (r["ne"], r["kts"], r["ob"], r["kelebihan"], r["memenuhi_kkm"]) == (Decimal("61.95"), 1, 1, 1, False)
    assert "KKM 75" in grafik.tren(baris)


def test_baris_rapor(audit_final):
    b = analitik.baris_rapor(analitik.audit_final(audit_final.periode))[0]
    assert b["ne"] == Decimal("61.95") and b["nk"] == Decimal("75.00") and b["ptk_total"] == 2
    assert [str(n) for _, n in b["auditor"]] == ["62.50", "62.50", "62.50"]
    assert b["hasil_akhir"] is None  # proporsi NE/NK belum ditetapkan


# --- Hak akses analitik (Bab 4) ------------------------------------------------------------------

def test_viewer_melihat_analitik_tetapi_tidak_membuka_audit(client, audit_final, viewer, prodi):
    client.force_login(viewer)
    assert client.get(reverse("beranda")).url == reverse("analitik:beranda")
    resp = client.get(reverse("analitik:beranda"))
    assert resp.status_code == 200 and resp.context["jumlah_audit"] == 1
    assert client.get(reverse("analitik:tren", args=[prodi.pk])).status_code == 200
    assert client.get(reverse("audits:detail", args=[audit_final.pk])).status_code == 403
    assert client.get(reverse("audits:ser", args=[audit_final.pk])).status_code == 403


def test_auditee_hanya_unitnya(client, audit_final, auditee, prodi_lain):
    client.force_login(auditee)
    resp = client.get(reverse("analitik:beranda"))
    assert resp.status_code == 200 and resp.context["boleh_semua"] is False
    assert list(resp.context["form"].fields["unit"].queryset) == [audit_final.unit]
    assert client.get(reverse("analitik:tren", args=[prodi_lain.pk])).status_code == 403


def test_pengguna_tanpa_hak_ditolak(client, audit_final):
    client.force_login(buat_pengguna("Orang"))
    assert client.get(reverse("analitik:beranda")).status_code == 403


# --- Ekspor lewat antrean (FR-44, FR-48, FR-51, NFR-03) --------------------------------------------

def minta(client, data, capture):
    with capture(execute=True):
        return client.post(reverse("ekspor:minta"), data)


def test_rapor_fakultas_oleh_viewer(client, audit_final, viewer, fakultas, django_capture_on_commit_callbacks):
    client.force_login(viewer)
    r = minta(client, {"jenis": "RAPOR", "periode": audit_final.periode_id, "fakultas": fakultas.pk}, django_capture_on_commit_callbacks)
    assert r.status_code == 302
    e = Ekspor.objects.get()
    assert e.status == "SIAP" and e.judul.startswith("Rapor Fakultas Teknik")
    resp = client.get(reverse("ekspor:unduh", args=[e.pk, "excel"]))
    wb = load_workbook(io.BytesIO(b"".join(resp.streaming_content)))
    ws = wb["Rapor"]
    header = [c.value for c in ws[4]]
    assert header[:5] == ["No.", "Unit", "Tipe", "Fakultas", "Status"] and "NE final" in header
    baris = [c.value for c in ws[5]]
    assert baris[1] == "Teknik Elektro" and float(baris[header.index("NE final")]) == 61.95
    assert baris[header.index("Hasil akhir")] == "Menunggu keputusan LPM"
    assert wb["Temuan"].max_row == 4 + 3  # judul + 3 temuan


def test_unduhan_orang_lain_tidak_bisa_diambil(client, audit_final, viewer, fakultas, django_capture_on_commit_callbacks):
    client.force_login(viewer)
    minta(client, {"jenis": "RAPOR", "periode": audit_final.periode_id, "fakultas": fakultas.pk}, django_capture_on_commit_callbacks)
    e = Ekspor.objects.get()
    client.force_login(buat_pengguna("Rektor2", peran=Peran.VIEWER))
    assert client.get(reverse("ekspor:unduh", args=[e.pk, "excel"])).status_code == 404


def test_auditee_rapor_unitnya_saja(client, audit_final, auditee, fakultas, django_capture_on_commit_callbacks):
    client.force_login(auditee)
    ok = minta(client, {"jenis": "RAPOR", "periode": audit_final.periode_id, "unit": audit_final.unit_id}, django_capture_on_commit_callbacks)
    assert ok.status_code == 302 and Ekspor.objects.get().status == "SIAP"
    assert client.post(reverse("ekspor:minta"), {"jenis": "RAPOR", "periode": audit_final.periode_id, "fakultas": fakultas.pk}).status_code == 403
    assert client.post(reverse("ekspor:minta"), {"jenis": "REKAP_PERIODE", "periode": audit_final.periode_id}).status_code == 403


def test_rekap_periode_excel_dan_pdf(client, audit_final, admin_lpm, django_capture_on_commit_callbacks):
    client.force_login(admin_lpm)
    with mock.patch("documents.ekspor.render_pdf", return_value=PDF_UJI) as render:
        minta(client, {"jenis": "REKAP_PERIODE", "periode": audit_final.periode_id}, django_capture_on_commit_callbacks)
    e = Ekspor.objects.get()
    assert e.status == "SIAP" and e.berkas and e.berkas_pdf
    html = render.call_args.args[0]
    assert "<svg" in html and "Teknik Elektro" in html
    wb = load_workbook(e.berkas.path)
    assert wb.sheetnames == ["Rekap", "Per butir", "Temuan"] and wb["Per butir"]._charts


def test_data_mentah_hanya_admin(client, audit_final, admin_lpm, viewer, django_capture_on_commit_callbacks):
    client.force_login(viewer)
    assert client.post(reverse("ekspor:minta"), {"jenis": "DATA_AUDIT", "audit": audit_final.pk}).status_code == 403
    client.force_login(admin_lpm)
    minta(client, {"jenis": "DATA_AUDIT", "audit": audit_final.pk}, django_capture_on_commit_callbacks)
    wb = load_workbook(Ekspor.objects.get().berkas.path)
    assert wb.sheetnames == ["SER", "Penilaian", "Kategori final", "Hasil", "PTK"]
    assert wb["Penilaian"].max_row - 4 == 12  # 4 butir × 3 auditor


def test_ekspor_tidak_dibuat_di_request_web(client, audit_final, viewer, fakultas):
    client.force_login(viewer)
    client.post(reverse("ekspor:minta"), {"jenis": "RAPOR", "periode": audit_final.periode_id, "fakultas": fakultas.pk})
    e = Ekspor.objects.get()
    assert e.status == "DIANTRE" and not e.berkas  # menunggu worker
    isi = client.get(reverse("ekspor:daftar")).content.decode()
    assert 'hx-trigger="every 3s"' in isi


def test_teks_pengguna_diawali_sama_dengan_tidak_menjadi_rumus(audit, ketua, penugasan_auditee, admin_lpm, client, django_capture_on_commit_callbacks):
    # NFR-09: formula injection
    audit = jadikan_final(audit, ketua, penugasan_auditee, uraian='=HYPERLINK("http://jahat","klik")')
    client.force_login(admin_lpm)
    minta(client, {"jenis": "RAPOR", "periode": audit.periode_id, "unit": audit.unit_id}, django_capture_on_commit_callbacks)
    ws = load_workbook(Ekspor.objects.get().berkas.path)["Temuan"]
    sel = ws.cell(row=5, column=5)
    assert sel.value.startswith("=HYPERLINK") and sel.data_type == "s"
