"""Aturan tim audit: FR-13 (ganjil ≥ 3, satu ketua), FR-14 (konflik, beban), constraint DB."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from accounts.peran import Peran
from audits.layanan import alasan_konflik, beban_auditor, periksa_tim, simpan_audit
from audits.models import Audit, Penugasan
from masterdata.models import TipeUnit, Unit

from .conftest import buat_pengguna

pytestmark = pytest.mark.django_db


def galat(**tim):
    return " | ".join(periksa_tim(**tim))


def test_tim_valid_tanpa_galat(tim):
    assert periksa_tim(**tim) == []


def test_simpan_audit_membuat_tim(tim, admin_lpm):
    audit = simpan_audit(**tim, oleh=admin_lpm)
    assert audit.status == Audit.Status.BELUM_MULAI
    assert audit.dibuat_oleh == admin_lpm
    assert audit.auditee == tim["auditee"]
    assert set(audit.auditor) == set(tim["auditor"])
    assert audit.ketua == tim["ketua"]
    assert audit.penugasan.filter(ketua=True).count() == 1


# --- FR-13: jumlah auditor ganjil ≥ minimal Pengaturan -------------------------------

@pytest.mark.parametrize("jumlah, valid", [(1, False), (2, False), (3, True), (4, False), (5, True)])
def test_jumlah_auditor_ganjil_minimal_3(tim, auditor, jumlah, valid):
    tim.update(auditor=auditor[:jumlah], ketua=auditor[0])
    assert (periksa_tim(**tim) == []) is valid


def test_minimal_auditor_diambil_dari_pengaturan_periode(tim, periode):
    periode.pengaturan.minimal_auditor = 5
    periode.pengaturan.save()
    assert "minimal 5" in galat(**tim)


def test_ketua_wajib_dipilih(tim):
    tim["ketua"] = None
    assert "Pilih satu ketua auditor" in galat(**tim)


def test_ketua_harus_salah_satu_auditor(tim, auditor):
    tim["ketua"] = auditor[4]
    assert "Ketua auditor Eka harus salah satu auditor" in galat(**tim)


def test_auditee_tidak_boleh_merangkap_auditor(tim, auditee, auditor):
    tim.update(auditor=[auditee, auditor[0], auditor[1]])
    assert "Kaprodi tidak boleh menjadi auditee sekaligus auditor" in galat(**tim)


def test_auditor_ganda_ditolak(tim, auditor):
    tim["auditor"] = [auditor[0], auditor[0], auditor[1]]
    assert "lebih dari sekali" in galat(**tim)


# --- FR-14: konflik dan beban ---------------------------------------------------

def test_auditor_tidak_boleh_mengaudit_homebase(tim, auditor, prodi):
    auditor[1].homebase = prodi
    auditor[1].save()
    assert "Budi tidak boleh mengaudit Teknik Elektro karena unit tersebut adalah homebase-nya" in galat(**tim)


def test_auditor_tidak_boleh_mengaudit_unit_tempat_menjabat(tim, auditor, prodi):
    auditor[2].unit_jabatan.add(prodi)
    assert "Citra tidak boleh mengaudit Teknik Elektro karena ia menjabat di unit tersebut" in galat(**tim)


def test_homebase_di_fakultas_induk_bukan_konflik(tim, auditor, fakultas, prodi_lain):
    # Keputusan 31 Okt 2026: konflik hanya homebase/jabatan di unit itu sendiri.
    auditor[0].homebase = fakultas
    auditor[0].save()
    auditor[1].homebase = prodi_lain
    auditor[1].save()
    assert periksa_tim(**tim) == []


def test_alasan_konflik_none_untuk_unit_lain(auditor, prodi):
    assert alasan_konflik(auditor[0], prodi) is None


def test_beban_auditor_per_periode(tim, auditor, admin_lpm, prodi_lain, standar):
    simpan_audit(**tim, oleh=admin_lpm)
    simpan_audit(**{**tim, "unit": prodi_lain, "auditor": auditor[2:5], "ketua": auditor[2]}, oleh=admin_lpm)
    beban = beban_auditor(tim["periode"])
    assert beban[auditor[0].pk] == 1
    assert beban[auditor[2].pk] == 2  # Citra di dua audit
    assert tim["auditee"].pk not in beban  # auditee tidak dihitung


# --- Kelayakan pengguna, unit, dan lingkup --------------------------------------------

@pytest.mark.parametrize("peran", [Peran.MENUNGGU, Peran.VIEWER, Peran.NONAKTIF])
def test_pengguna_tanpa_peran_layak_tidak_bisa_diplot(tim, auditor, peran):
    auditor[1].peran = peran
    auditor[1].save()
    assert "Budi berperan" in galat(**tim)


def test_admin_lpm_boleh_diplot_sebagai_auditor(tim, admin_lpm, auditor):
    tim["auditor"] = [admin_lpm, auditor[0], auditor[1]]
    assert periksa_tim(**tim) == []


def test_lingkup_wajib(tim):
    tim["lingkup"] = []
    assert "minimal satu lingkup" in galat(**tim)


def test_unit_tanpa_pernyataan_berlaku_ditolak(tim):
    tim["unit"] = Unit.objects.create(nama="Biro Keuangan", kode="BK", tipe_id=TipeUnit.BIRO)
    assert "Belum ada pernyataan standar yang berlaku untuk Biro Keuangan" in galat(**tim)


def test_satu_audit_per_unit_per_periode(tim, admin_lpm):
    simpan_audit(**tim, oleh=admin_lpm)
    with pytest.raises(ValidationError, match="sudah memiliki audit"):
        simpan_audit(**tim, oleh=admin_lpm)


# --- Ubah tim ----------------------------------------------------------------------

def test_ubah_tim_mengganti_penugasan(tim, auditor, admin_lpm):
    audit = simpan_audit(**tim, oleh=admin_lpm)
    simpan_audit(**{**tim, "auditor": auditor[2:5], "ketua": auditor[4]}, oleh=admin_lpm, audit=audit)
    audit = Audit.objects.get(pk=audit.pk)
    assert set(audit.auditor) == set(auditor[2:5])
    assert audit.ketua == auditor[4]
    assert Penugasan.objects.filter(audit=audit).count() == 4


@pytest.mark.parametrize("status, boleh", [
    (Audit.Status.BELUM_MULAI, True),
    (Audit.Status.PENGISIAN_SER, True),
    (Audit.Status.PENILAIAN_AUDITOR, False),
    (Audit.Status.FINAL, False),
])
def test_tim_hanya_bisa_diubah_sebelum_penilaian(tim, admin_lpm, status, boleh):
    audit = simpan_audit(**tim, oleh=admin_lpm)
    audit.status = status
    audit.save()
    assert (periksa_tim(**tim, audit=audit) == []) is boleh


def test_galat_tidak_menyimpan_apa_pun(tim, auditor, admin_lpm):
    tim["auditor"] = auditor[:2]
    with pytest.raises(ValidationError):
        simpan_audit(**tim, oleh=admin_lpm)
    assert not Audit.objects.exists()


# --- Constraint database ---------------------------------------------------------

def test_db_menolak_dua_auditee(tim, admin_lpm, auditor):
    audit = simpan_audit(**tim, oleh=admin_lpm)
    with pytest.raises(IntegrityError):
        Penugasan.objects.create(audit=audit, pengguna=auditor[4], peran=Penugasan.Peran.AUDITEE)


def test_db_menolak_dua_ketua(tim, admin_lpm, auditor):
    audit = simpan_audit(**tim, oleh=admin_lpm)
    with pytest.raises(IntegrityError):
        Penugasan.objects.create(audit=audit, pengguna=auditor[4], peran=Penugasan.Peran.AUDITOR, ketua=True)


def test_db_menolak_ketua_yang_bukan_auditor(tim, admin_lpm):
    audit = simpan_audit(**tim, oleh=admin_lpm)
    orang = buat_pengguna("Fajar")
    with pytest.raises(IntegrityError):
        Penugasan.objects.create(audit=audit, pengguna=orang, peran=Penugasan.Peran.AUDITEE, ketua=True)


def test_pengaturan_periode_dipakai_bukan_angka_tetap(tim, periode):
    # Aturan proyek: angka aturan dari Pengaturan; minimal auditor 1 → 1 auditor valid
    periode.pengaturan.minimal_auditor = 1
    periode.pengaturan.kkm = Decimal("75")
    periode.pengaturan.save()
    tim["auditor"] = tim["auditor"][:1]
    assert periksa_tim(**tim) == []
