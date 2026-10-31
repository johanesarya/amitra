import pytest

from audits import penilaian as penilaian_layanan
from audits import ser
from audits.layanan import simpan_audit
from audits.tests.conftest import *  # noqa: F401,F403 — fixture tim, auditee, auditor, periode, dst.
from masterdata.models import PernyataanStandar, TipeUnit

SKOR = {1: "KTS", 2: "OB", 3: "SESUAI", 4: "PELAMPAUAN"}


def nilai_semua(audit, skor_per_auditor):
    """Isi dan kunci penilaian; skor_per_auditor = [[skor per butir], ...] sesuai urutan tim."""
    butir = list(audit.pernyataan_berlaku())
    for t, skor in zip(penilaian_layanan.tim_auditor(audit), skor_per_auditor):
        penilaian_layanan.pastikan_penilaian(audit, t.pengguna)
        for b, s in zip(butir, skor):
            p = audit.penilaian.get(auditor=t.pengguna, pernyataan=b)
            kondisi = f"Kondisi faktual {b.kode} oleh {t.pengguna}" if s in (1, 2) else ""
            penilaian_layanan.simpan_penilaian(audit, t, b.pk, SKOR[s], f"Dasar {b.kode}", kondisi, p.versi)
        t.refresh_from_db()
        audit.refresh_from_db()
        penilaian_layanan.kunci(audit, t, t.pengguna)
    audit.refresh_from_db()
    return audit


@pytest.fixture
def audit_dinilai(tim, admin_lpm, standar, auditee):
    """Audit 4 butir dengan SER terkirim, siap dinilai."""
    for i in (2, 3, 4):
        p = PernyataanStandar.objects.create(standar=standar, kode=f"1.{i}", pernyataan=f"Butir 1.{i}", urutan=i)
        p.tipe_unit.set([TipeUnit.PRODI_S1])
    audit = simpan_audit(**tim, oleh=admin_lpm)
    ser.pastikan_jawaban(audit)
    for b in audit.pernyataan_berlaku():
        ser.simpan_penjelasan(audit, b.pk, f"Penjelasan {b.kode}", 1, auditee)
        ser.tambah_tautan(audit, b.pk, "https://drive.google.com/file/d/x/view", auditee)
    ser.kirim(audit, auditee)
    audit.refresh_from_db()
    return audit


@pytest.fixture
def audit(audit_dinilai):
    """Perumusan Temuan: 1.1 Sesuai, 1.2 Pelampauan, 1.3 KTS, 1.4 OB (semua auditor sama, D = 0)."""
    return nilai_semua(audit_dinilai, [[3, 4, 1, 2]] * 3)


@pytest.fixture
def ketua(audit):
    return audit.penugasan.get(ketua=True)


@pytest.fixture
def anggota(audit):
    return audit.penugasan.filter(peran="AUDITOR", ketua=False).first()


@pytest.fixture
def penugasan_auditee(audit):
    return audit.penugasan.get(peran="AUDITEE")
