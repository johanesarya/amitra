"""Audit log tak terhapus (NFR-10, Bab 4)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.urls import reverse
from django.utils import timezone

from accounts import jejak
from accounts.models import LogAudit, SegelLog
from accounts.peran import Peran
from audits import ser
from audits.tests.conftest import buat_pengguna

pytestmark = pytest.mark.django_db
A = LogAudit.Aksi


def log(aksi, **filter_):
    return LogAudit.objects.filter(aksi=aksi, **filter_)


# --- Tak terhapus ------------------------------------------------------------------------

@pytest.fixture
def satu_log(db):
    return jejak.catat(A.CATATAN_AUDIT, data={"x": 1}, alasan="uji")


def test_kode_menolak_ubah_dan_hapus(satu_log):
    satu_log.alasan = "diubah"
    with pytest.raises(ValueError):
        satu_log.save()
    with pytest.raises(ValueError):
        satu_log.delete()
    with pytest.raises(ValueError):
        LogAudit.objects.filter(pk=satu_log.pk).update(alasan="x")
    with pytest.raises(ValueError):
        LogAudit.objects.all().delete()


@pytest.mark.parametrize("sql", ["UPDATE accounts_logaudit SET alasan = 'x'", "DELETE FROM accounts_logaudit"])
def test_database_menolak_sql_mentah(satu_log, sql):
    with pytest.raises(DatabaseError, match="tidak dapat diubah"):
        with transaction.atomic(), connection.cursor() as c:
            c.execute(sql)
    assert LogAudit.objects.get(pk=satu_log.pk).alasan == "uji"


def test_segel_dan_periksa_mendeteksi_manipulasi(satu_log):
    jejak.catat(A.CATATAN_AUDIT, alasan="kedua")
    assert jejak.segel() == 2 and jejak.segel() == 0
    assert jejak.periksa() == []
    # Simulasi penyerang yang mematikan trigger lalu mengubah isi.
    with connection.cursor() as c:
        c.execute("DROP TRIGGER accounts_logaudit_tolak_update")
        c.execute("UPDATE accounts_logaudit SET alasan = 'dipalsukan' WHERE id = %s", [satu_log.pk])
    masalah = jejak.periksa()
    assert any(f"Log #{satu_log.pk}" in m for m in masalah)
    with pytest.raises(CommandError, match="masalah"):
        call_command("periksa_log")


def test_rantai_putus_bila_log_tersegel_dihapus(satu_log):
    jejak.catat(A.CATATAN_AUDIT, alasan="kedua")
    jejak.segel()
    with connection.cursor() as c:
        c.execute("DROP TRIGGER accounts_logaudit_tolak_delete")
        c.execute("DROP TRIGGER accounts_segellog_tolak_delete")
        c.execute("DELETE FROM accounts_segellog WHERE log_id = %s", [satu_log.pk])
        c.execute("DELETE FROM accounts_logaudit WHERE id = %s", [satu_log.pk])
    assert any("rantai putus" in m for m in jejak.periksa())


def test_hash_stabil_untuk_nilai_desimal(db):
    catatan = jejak.catat(A.HASIL_DIHITUNG, data={"ne": Decimal("77.03")})
    assert LogAudit.objects.get(pk=catatan.pk).hitung_hash() == catatan.hash_isi


def test_pengguna_dengan_log_tidak_bisa_dihapus(db):
    from django.db.models import ProtectedError

    u = buat_pengguna("Ani")
    jejak.catat(A.CATATAN_AUDIT, aktor=u)
    with pytest.raises(ProtectedError):
        u.delete()


# --- Peristiwa yang dicatat ----------------------------------------------------------------

def test_login_berhasil_gagal_dan_logout_dengan_ip(client, db):
    tamu = buat_pengguna("Tamu", akun_tamu=True)
    tamu.set_password("RahasiaTamu!2026")
    tamu.save()
    client.post(reverse("account_login"), {"login": "tamu@unika.ac.id", "password": "salah"}, REMOTE_ADDR="10.0.0.7")
    gagal = log(A.LOGIN_GAGAL).get()
    assert gagal.aktor_email == "tamu@unika.ac.id" and gagal.ip == "10.0.0.7" and "salah" not in str(gagal.data)
    client.post(reverse("account_login"), {"login": "tamu@unika.ac.id", "password": "RahasiaTamu!2026"}, REMOTE_ADDR="10.0.0.7")
    assert log(A.LOGIN, aktor=tamu).get().ip == "10.0.0.7"
    client.post(reverse("account_logout"))
    assert log(A.LOGOUT, aktor=tamu).exists()


def test_login_password_akun_kampus_tercatat_gagal(client, db):
    dosen = buat_pengguna("Dosen")
    dosen.set_password("RahasiaDosen!2026")
    dosen.save()
    client.post(reverse("account_login"), {"login": "dosen@unika.ac.id", "password": "RahasiaDosen!2026"})
    assert "akun kampus" in log(A.LOGIN_GAGAL).get().data["sebab"]


def test_perubahan_peran_mencatat_aktor_dan_nilai(client, db):
    master = buat_pengguna("Kepala", peran=Peran.MASTER_ADMIN)
    target = buat_pengguna("Baru", peran=Peran.MENUNGGU)
    client.force_login(master)
    client.post(reverse("admin:accounts_user_changelist"), {"action": "tetapkan_admin", "_selected_action": [target.pk]})
    entri = log(A.PERAN_DIUBAH, objek_id=str(target.pk)).get()
    assert entri.aktor == master
    assert entri.data["peran"] == {"dari": "MENUNGGU", "ke": "ADMIN"}


def test_last_login_tidak_dianggap_perubahan_peran(db):
    u = buat_pengguna("Ani")
    u.last_login = timezone.now()
    u.save(update_fields=["last_login"])
    assert not log(A.PERAN_DIUBAH).exists()


def test_status_audit_buka_kunci_dan_reset_tercatat_dengan_alasan(audit_dinilai):
    master = buat_pengguna("Kepala", peran=Peran.MASTER_ADMIN)
    ser.buka_kunci(audit_dinilai, master, "Bukti salah unggah")
    entri = log(A.STATUS_AUDIT, audit_id=audit_dinilai.pk, aktor=master).get()
    assert entri.data == {"dari": "PENILAIAN_AUDITOR", "ke": "PENGISIAN_SER"} and "Bukti salah unggah" in entri.alasan


def test_perubahan_kategori_dicatat_tetapi_autosave_teks_tidak(audit_dinilai):
    from audits import penilaian as pl

    t = pl.tim_auditor(audit_dinilai)[1]
    pl.pastikan_penilaian(audit_dinilai, t.pengguna)
    b = audit_dinilai.pernyataan_berlaku().first()
    p = audit_dinilai.penilaian.get(auditor=t.pengguna, pernyataan=b)
    p = pl.simpan_penilaian(audit_dinilai, t, b.pk, "SESUAI", "Dasar awal", "", p.versi)
    p = pl.simpan_penilaian(audit_dinilai, t, b.pk, "SESUAI", "Dasar diperbaiki", "", p.versi)
    p = pl.simpan_penilaian(audit_dinilai, t, b.pk, "OB", "Dasar", "Kondisi", p.versi)
    entri = list(log(A.SKOR_DIUBAH, audit_id=audit_dinilai.pk).order_by("id"))
    assert [(e.data["dari"], e.data["ke"]) for e in entri] == [("", "SESUAI"), ("SESUAI", "OB")]


def test_hasil_perhitungan_dan_kategori_final_tercatat(audit, ketua):
    from findings import layanan

    hasil = log(A.HASIL_DIHITUNG, audit_id=audit.pk).get()
    assert hasil.data["tahap"] == "AWAL" and hasil.data["ne"] == "61.95"
    b = audit.pernyataan_berlaku().get(kode="1.4")
    layanan.ubah_kategori_final(audit, ketua, b.pk, "SESUAI", "SOP ditemukan")
    k = log(A.KATEGORI_FINAL, audit_id=audit.pk).get()
    assert k.data["dari"] == "OB" and k.data["ke"] == "SESUAI" and k.alasan == "SOP ditemukan"


def test_pengaturan_tim_dan_hapus_audit_tercatat(tim, admin_lpm, periode):
    from audits.layanan import simpan_audit

    periode.pengaturan.kkm = Decimal("80")
    periode.pengaturan.save()
    assert log(A.PENGATURAN_DIUBAH).first().data["kolom"]["kkm"] == {"dari": "75.00", "ke": "80"}  # terbaru lebih dulu
    a = simpan_audit(**tim, oleh=admin_lpm)
    assert {x["email"] for x in log(A.TIM_DISIMPAN, audit_id=a.pk).get().data["tim"]} == {
        "kaprodi@unika.ac.id", "ani@unika.ac.id", "budi@unika.ac.id", "citra@unika.ac.id",
    }
    pk = a.pk
    a.delete()
    assert log(A.AUDIT_DIHAPUS, audit_id=pk).exists()


# --- Akses dan ekspor (Bab 4) ---------------------------------------------------------------

@pytest.mark.parametrize("peran, kode", [(Peran.MASTER_ADMIN, 200), (Peran.ADMIN, 200), (Peran.PENGGUNA, 302), (Peran.VIEWER, 302)])
def test_akses_halaman_log(client, satu_log, peran, kode):
    client.force_login(buat_pengguna("Uji", peran=peran))
    assert client.get(reverse("admin:accounts_logaudit_changelist")).status_code == kode


def test_admin_hanya_melihat_tanpa_ubah_atau_ekspor(client, satu_log):
    client.force_login(buat_pengguna("Staf", peran=Peran.ADMIN))
    isi = client.get(reverse("admin:accounts_logaudit_changelist")).content.decode()
    assert "Ekspor Excel" not in isi
    assert client.post(reverse("admin:accounts_logaudit_delete", args=[satu_log.pk]), {"post": "yes"}).status_code == 403
    assert client.post(reverse("ekspor:minta"), {"jenis": "LOG", "dari": "2026-01-01", "sampai": "2026-12-31"}).status_code == 403


def test_filter_log_per_audit(client, audit_dinilai):
    client.force_login(buat_pengguna("Staf", peran=Peran.ADMIN))
    resp = client.get(reverse("admin:accounts_logaudit_changelist"), {"audit_id": audit_dinilai.pk})
    assert resp.status_code == 200
    assert all(e.audit_id == audit_dinilai.pk for e in resp.context["cl"].result_list)


def test_master_admin_ekspor_log(client, satu_log, django_capture_on_commit_callbacks):
    from documents.models import Ekspor
    from openpyxl import load_workbook

    client.force_login(buat_pengguna("Kepala", peran=Peran.MASTER_ADMIN))
    hari_ini = timezone.localdate()
    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("ekspor:minta"), {"jenis": "LOG", "dari": str(hari_ini - timedelta(days=1)), "sampai": str(hari_ini)})
    e = Ekspor.objects.get(jenis="LOG")
    assert e.status == "SIAP"
    ws = load_workbook(e.berkas.path)["Log audit"]
    assert [c.value for c in ws[4]][:3] == ["Waktu", "Aksi", "Aktor"]
    assert any(ws.cell(row=r, column=7).value == "uji" for r in range(5, ws.max_row + 1))


def test_pasang_jadwal_segel_log(db):
    from django_q.models import Schedule

    call_command("pasang_jadwal")
    s = Schedule.objects.get(name="segel-log")
    assert s.func == "accounts.jejak.segel" and s.schedule_type == Schedule.MINUTES and s.minutes == 10
    assert SegelLog.objects.count() == 0  # jadwal tidak langsung menyegel
