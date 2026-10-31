"""Penerbitan dan koreksi nomor surat (FR-39, BR-15).

Keputusan 31 Okt 2026: nomor diterbitkan saat ketua meneruskan hasil ke auditee,
dapat dikoreksi Admin sampai Final, lalu terkunci. Penghitung direset tiap tahun
kalender dan terpisah per pola. Nomor batal tidak dipakai ulang.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from audits.models import HasilPerhitungan
from audits.penilaian import STATUS_SETELAH_FINAL

from .models import JenisDokumen, NomorSurat, PenghitungNomor, PolaNomorSurat

ROMAWI = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def pola_untuk(jenis, unit):
    """Pola khusus kategori unit bila ada, selain itu pola umum jenis tersebut."""
    if unit.kategori_surat_id:
        pola = PolaNomorSurat.objects.filter(jenis=jenis, kategori_id=unit.kategori_surat_id).first()
        if pola:
            return pola
    return PolaNomorSurat.objects.filter(jenis=jenis, kategori__isnull=True).first()


def render_pola(pola, nomor, tanggal, unit):
    return pola.format(
        nomor=f"{nomor:03d}",
        bulan_romawi=ROMAWI[tanggal.month - 1],
        bulan=f"{tanggal.month:02d}",
        tahun=tanggal.year,
        kode_unit=unit.kode,
        kode_fakultas=unit.induk.kode if unit.induk_id else unit.kode,
        kategori=unit.kategori_surat.kode if unit.kategori_surat_id else "-",
    )


def nomor_terkunci(audit):
    return audit.status in STATUS_SETELAH_FINAL


def aktif(audit, jenis, ptk=None):
    qs = audit.nomor_surat.filter(jenis=jenis, status=NomorSurat.Status.AKTIF)
    return qs.filter(ptk=ptk).first() if ptk is not None else qs.filter(ptk__isnull=True).first()


@transaction.atomic
def terbitkan(audit, jenis, ptk=None):
    """Terbitkan nomor bila belum ada. Kembalikan None bila pola belum diatur LPM."""
    ada = aktif(audit, jenis, ptk)
    if ada is not None:
        return ada
    unit = audit.unit
    pola = pola_untuk(jenis, unit)
    if pola is None:
        return None
    tanggal = timezone.localdate()
    PenghitungNomor.objects.get_or_create(pola=pola, tahun=tanggal.year)
    # Kunci baris penghitung agar penerbitan bersamaan tidak menghasilkan nomor sama.
    penghitung = PenghitungNomor.objects.select_for_update().get(pola=pola, tahun=tanggal.year)
    penghitung.terakhir += 1
    penghitung.save(update_fields=["terakhir"])
    teks = render_pola(pola.pola, penghitung.terakhir, tanggal, unit)
    if NomorSurat.objects.filter(teks=teks, status=NomorSurat.Status.AKTIF).exists():
        # Dibatalkan bersama kenaikan penghitung (transaksi ini) agar nomor tidak terbuang.
        raise ValidationError(f"Pola {pola.pola} menghasilkan nomor {teks} yang sudah dipakai. Periksa pola nomor surat.")
    nomor = NomorSurat.objects.create(
        audit=audit, jenis=jenis, ptk=ptk, pola=pola, tahun=tanggal.year, nomor_urut=penghitung.terakhir, teks=teks,
    )
    if ptk is not None:
        ptk.nomor_surat = nomor.teks
        ptk.save(update_fields=["nomor_surat"])
    return nomor


def jenis_bernomor_untuk(audit):
    jenis = [JenisDokumen.LAPORAN_AMI]
    if audit.hasil_tahap(HasilPerhitungan.Tahap.SETELAH_AL):
        jenis.append(JenisDokumen.BERITA_ACARA)
    return jenis


@transaction.atomic
def terbitkan_untuk_audit(audit):
    """Nomor untuk setiap PTK, Laporan AMI, dan Berita Acara (bila ada Audit Lapangan).

    Nomor PTK yang PTK-nya sudah hilang (mis. setelah keberatan) ditandai batal.
    Mengembalikan daftar jenis yang belum bisa diberi nomor karena pola belum diatur.
    """
    audit.nomor_surat.filter(jenis=JenisDokumen.PTK, ptk__isnull=True, status=NomorSurat.Status.AKTIF).update(
        status=NomorSurat.Status.BATAL, alasan_koreksi="PTK dibatalkan setelah perumusan ulang."
    )
    belum = set()
    tugas = [(JenisDokumen.PTK, p) for p in audit.ptk.all()] + [(j, None) for j in jenis_bernomor_untuk(audit)]
    for jenis, ptk in tugas:
        label = JenisDokumen(jenis).label
        try:
            if terbitkan(audit, jenis, ptk) is None:
                belum.add(label)
        except ValidationError:
            # Kesalahan konfigurasi pola tidak boleh menggagalkan alur audit; Admin menerbitkan ulang.
            belum.add(f"{label} (nomor bentrok, periksa pola)")
    return sorted(belum)


@transaction.atomic
def koreksi(nomor, teks_baru, alasan, oleh):
    """FR-39: Admin mengoreksi nomor sebelum Final, dengan alasan; nomor tetap unik."""
    if nomor_terkunci(nomor.audit):
        raise ValidationError("Nomor surat terkunci karena audit sudah Final.")
    if nomor.status != NomorSurat.Status.AKTIF:
        raise ValidationError("Nomor yang sudah batal tidak dapat dikoreksi.")
    teks_baru = (teks_baru or "").strip()
    alasan = (alasan or "").strip()
    if not teks_baru:
        raise ValidationError("Nomor surat baru wajib diisi.")
    if not alasan:
        raise ValidationError("Alasan koreksi wajib diisi.")
    if NomorSurat.objects.filter(teks=teks_baru, status=NomorSurat.Status.AKTIF).exclude(pk=nomor.pk).exists():
        raise ValidationError(f"Nomor {teks_baru} sudah dipakai dokumen lain.")
    lama = nomor.teks
    nomor.teks, nomor.alasan_koreksi, nomor.dikoreksi_oleh = teks_baru, alasan, oleh
    nomor.save(update_fields=["teks", "alasan_koreksi", "dikoreksi_oleh"])
    from accounts.jejak import catat
    from accounts.models import LogAudit

    catat(LogAudit.Aksi.NOMOR_DIKOREKSI, objek=nomor, audit_id=nomor.audit_id, aktor=oleh,
          data={"jenis": nomor.jenis, "dari": lama, "ke": teks_baru}, alasan=alasan)
    if nomor.ptk_id:
        nomor.ptk.nomor_surat = teks_baru
        nomor.ptk.save(update_fields=["nomor_surat"])
    return nomor
