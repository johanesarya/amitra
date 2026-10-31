"""Perumusan temuan sampai Final (FR-32 s.d. FR-38, BR-12, BR-14 s.d. BR-18)."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from audits import penilaian as penilaian_layanan
from audits import status
from audits.models import Audit, HasilPerhitungan, KategoriFinal, Penilaian, Penugasan
from scoring.rumus import bulatkan, hasil_akhir, konversi_skala_100, nilai_kesimpulan

from .models import PTK, Kesimpulan, Persetujuan, Temuan, Usulan
from .sinyal import ptk_diperbarui

S = Audit.Status

# BR-14: kategori final → jenis temuan
JENIS_DARI_KATEGORI = {
    Penilaian.Kategori.PELAMPAUAN: Temuan.Jenis.KELEBIHAN,
    Penilaian.Kategori.KTS: Temuan.Jenis.KTS,
    Penilaian.Kategori.OB: Temuan.Jenis.OB,
}

CHECKLIST_KETUA = [
    ("kategori", "Kategori final setiap butir sudah disepakati tim auditor."),
    ("temuan", "Uraian setiap temuan sesuai kondisi faktual dan bukti."),
    ("kesimpulan", "Kesimpulan A, B, C dan Tujuan Audit sudah dinilai."),
    ("teruskan", "Saya menyetujui hasil ini untuk diteruskan kepada auditee."),
]
CHECKLIST_AUDITEE = [
    ("baca", "Saya telah membaca seluruh temuan dan kesimpulan audit."),
    ("ptk", "Saya memahami PTK yang wajib ditindaklanjuti unit saya."),
    ("setuju", "Saya menyetujui hasil Audit Mutu Internal ini."),
]


def _pastikan_ketua(penugasan):
    if penugasan is None or not penugasan.ketua:
        raise PermissionError("Hanya ketua auditor yang dapat melakukan tindakan ini.")


def _pastikan_perumusan(audit):
    if audit.status != S.PERUMUSAN_TEMUAN:
        raise ValidationError("Tindakan ini hanya dapat dilakukan saat Perumusan Temuan.")


# --- Temuan otomatis (FR-33, BR-14) ---------------------------------------------------

def sinkron_temuan(audit):
    """Samakan temuan Kelebihan/KTS/OB dengan kategori final. Uraian dipertahankan bila
    butirnya tetap menjadi temuan; temuan yang tidak lagi berlaku dihapus beserta PTK-nya."""
    urutan = {p.pk: i for i, p in enumerate(audit.pernyataan_berlaku())}
    perlu = {}
    for k in audit.kategori_final.exclude(cara=KategoriFinal.Cara.TIDAK_BERLAKU):
        jenis = JENIS_DARI_KATEGORI.get(k.kategori)
        if jenis:
            perlu[k.pernyataan_id] = jenis
    ada = {t.pernyataan_id: t for t in audit.temuan.exclude(jenis=Temuan.Jenis.PELUANG)}
    for pid, t in ada.items():
        if pid not in perlu:
            t.delete()
    for pid, jenis in perlu.items():
        t = ada.get(pid)
        if t is None:
            Temuan.objects.create(audit=audit, pernyataan_id=pid, jenis=jenis, urutan=urutan.get(pid, 0))
        elif t.jenis != jenis or t.urutan != urutan.get(pid, 0):
            t.jenis, t.urutan = jenis, urutan.get(pid, 0)
            t.save(update_fields=["jenis", "urutan", "diubah_pada"])
            if jenis not in Temuan.JENIS_PTK:
                PTK.objects.filter(temuan=t).delete()


def usulan_uraian(audit, temuan):
    """Kondisi faktual / dasar penilaian auditor yang memilih kategori temuan ini."""
    kategori = {v: k for k, v in JENIS_DARI_KATEGORI.items()}.get(temuan.jenis)
    if not kategori or not temuan.pernyataan_id:
        return []
    return [
        (p.auditor, p.kondisi_faktual or p.dasar_penilaian)
        for p in audit.penilaian.filter(pernyataan_id=temuan.pernyataan_id, kategori=kategori).select_related("auditor")
    ]


@transaction.atomic
def ubah_kategori_final(audit, penugasan, pernyataan_id, kategori, alasan):
    """FR-32: ketua menetapkan kategori final setelah diskusi tim, alasan wajib bila berubah."""
    _pastikan_ketua(penugasan)
    _pastikan_perumusan(audit)
    if kategori not in Penilaian.Kategori.values:
        raise ValidationError("Pilih kategori.")
    k = audit.kategori_final.exclude(cara=KategoriFinal.Cara.TIDAK_BERLAKU).filter(pernyataan_id=pernyataan_id).first()
    if k is None:
        raise ValidationError("Butir ini tidak memiliki kategori final.")
    if k.kategori == kategori:
        return k
    alasan = (alasan or "").strip()
    if not alasan:
        raise ValidationError("Alasan perubahan kategori wajib diisi.")
    lama = k.kategori
    k.kategori, k.cara, k.alasan, k.ditetapkan_oleh = kategori, KategoriFinal.Cara.KETUA, alasan, penugasan.pengguna
    k.save()
    from accounts.jejak import catat
    from accounts.models import LogAudit

    catat(LogAudit.Aksi.KATEGORI_FINAL, objek=k, audit_id=audit.pk, aktor=penugasan.pengguna,
          data={"butir": k.pernyataan.kode, "dari": lama, "ke": kategori, "cara": "FR-32"}, alasan=alasan)
    sinkron_temuan(audit)
    status.catat(audit, penugasan.pengguna, f"Kategori final butir {k.pernyataan.kode} diubah: {alasan}")
    return k


def simpan_uraian(audit, penugasan, temuan, uraian):
    _pastikan_ketua(penugasan)
    _pastikan_perumusan(audit)
    temuan.uraian = (uraian or "").strip()
    temuan.diubah_oleh = penugasan.pengguna
    temuan.save(update_fields=["uraian", "diubah_oleh", "diubah_pada"])


def tambah_peluang(audit, penugasan, uraian, oleh=None):
    _pastikan_ketua(penugasan)
    _pastikan_perumusan(audit)
    uraian = (uraian or "").strip()
    if not uraian:
        raise ValidationError("Uraian Peluang Peningkatan wajib diisi.")
    terakhir = audit.temuan.aggregate(m=Max("urutan"))["m"] or 0
    return Temuan.objects.create(
        audit=audit, jenis=Temuan.Jenis.PELUANG, uraian=uraian, urutan=terakhir + 1000, diubah_oleh=penugasan.pengguna
    )


def hapus_peluang(audit, penugasan, temuan):
    _pastikan_ketua(penugasan)
    _pastikan_perumusan(audit)
    if temuan.otomatis:
        raise ValidationError("Temuan otomatis berubah lewat kategori final, bukan dihapus.")
    temuan.delete()


# --- Usulan anggota (Bab 4) -----------------------------------------------------------

def ajukan_usulan(audit, penugasan, jenis, isi, temuan=None):
    if penugasan is None or penugasan.peran != Penugasan.Peran.AUDITOR:
        raise PermissionError("Hanya auditor tim yang dapat mengusulkan.")
    _pastikan_perumusan(audit)
    isi = (isi or "").strip()
    if not isi:
        raise ValidationError("Isi usulan wajib diisi.")
    if jenis == Usulan.Jenis.URAIAN and (temuan is None or not temuan.otomatis):
        raise ValidationError("Pilih temuan yang diusulkan uraiannya.")
    return Usulan.objects.create(
        audit=audit, oleh=penugasan.pengguna, jenis=jenis, isi=isi,
        temuan=temuan if jenis == Usulan.Jenis.URAIAN else None,
    )


@transaction.atomic
def tanggapi_usulan(audit, penugasan, usulan, terima):
    _pastikan_ketua(penugasan)
    _pastikan_perumusan(audit)
    if usulan.status != Usulan.Status.DIAJUKAN:
        raise ValidationError("Usulan ini sudah ditanggapi.")
    if terima:
        if usulan.jenis == Usulan.Jenis.PELUANG:
            tambah_peluang(audit, penugasan, usulan.isi)
        else:
            t = usulan.temuan
            t.uraian = f"{t.uraian}\n{usulan.isi}".strip() if t.uraian else usulan.isi
            t.diubah_oleh = penugasan.pengguna
            t.save(update_fields=["uraian", "diubah_oleh", "diubah_pada"])
    usulan.status = Usulan.Status.DITERIMA if terima else Usulan.Status.DITOLAK
    usulan.ditanggapi_oleh = penugasan.pengguna
    usulan.save(update_fields=["status", "ditanggapi_oleh"])


# --- Kesimpulan (FR-34) -----------------------------------------------------------------

def simpan_kesimpulan(audit, penugasan, data, tujuan_ids):
    _pastikan_ketua(penugasan)
    _pastikan_perumusan(audit)
    skala = {s for s, _ in audit.periode.pengaturan.opsi_kesimpulan()}
    k, _ = Kesimpulan.objects.get_or_create(audit=audit)
    for huruf in "abc":
        nilai = data.get(f"skor_{huruf}")
        nilai = int(nilai) if nilai not in (None, "") else None
        if nilai is not None and nilai not in skala:
            raise ValidationError(f"Skor Kesimpulan {huruf.upper()} di luar skala.")
        setattr(k, f"skor_{huruf}", nilai)
        setattr(k, f"penjelasan_{huruf}", (data.get(f"penjelasan_{huruf}") or "").strip())
    k.c_tidak_berlaku = bool(data.get("c_tidak_berlaku"))
    if k.c_tidak_berlaku:
        k.skor_c = None
    k.diubah_oleh = penugasan.pengguna
    k.save()
    k.tujuan_tercapai.set(tujuan_ids)
    return k


# --- Checklist ketua dan perhitungan final ---------------------------------------------

def keberatan_belum_ditanggapi(audit):
    return audit.persetujuan.filter(
        pihak=Persetujuan.Pihak.AUDITEE, keputusan=Persetujuan.Keputusan.KEBERATAN, tanggapan=""
    ).first()


def syarat_ketua(audit):
    """Daftar syarat yang belum terpenuhi sebelum ketua dapat mencentang checklist."""
    belum = []
    if penilaian_layanan.butir_seri(audit):
        belum.append("Masih ada butir tanpa kategori final.")
    kosong = [t for t in audit.temuan.select_related("pernyataan") if not t.uraian.strip()]
    if kosong:
        belum.append(f"{len(kosong)} temuan belum memiliki uraian.")
    k = Kesimpulan.objects.filter(audit=audit).first()
    if k is None:
        belum.append("Kesimpulan A, B, dan C belum diisi.")
    elif k.kurang:
        belum.append(f"{', '.join(k.kurang)} belum lengkap (skor dan penjelasan).")
    if keberatan_belum_ditanggapi(audit):
        belum.append("Keberatan auditee belum ditanggapi.")
    return belum


def hitung_final(audit, oleh):
    """NE final dari kategori final, NK dari Kesimpulan, dan hasil akhir (BR-12, BR-12a, BR-12b)."""
    hasil = penilaian_layanan.hitung(audit, HasilPerhitungan.Tahap.FINAL, oleh)
    params = audit.periode.parameter()
    k = audit.kesimpulan
    nk = nilai_kesimpulan(
        konversi_skala_100(k.skor_a, params),
        konversi_skala_100(k.skor_b, params),
        None if k.c_tidak_berlaku else konversi_skala_100(k.skor_c, params),
        params,
    )
    hasil.nk = bulatkan(nk)
    hasil.hasil_akhir = bulatkan(hasil_akhir(hasil.ne_eksak, nk, params)) if params.proporsi_ne is not None else None
    hasil.save(update_fields=["nk", "hasil_akhir"])
    return hasil


def _nomori_ptk(audit):
    """BR-15: satu PTK per temuan KTS/OB, nomor berurutan per audit mengikuti urutan butir."""
    temuan = list(audit.temuan.filter(jenis__in=Temuan.JENIS_PTK).order_by("urutan", "id"))
    # Geser dulu agar penomoran ulang tidak bentrok dengan constraint unik.
    for p in audit.ptk.all():
        p.nomor_urut += 100000
        p.save(update_fields=["nomor_urut"])
    for i, t in enumerate(temuan, start=1):
        ptk = PTK.objects.filter(temuan=t).first()
        if ptk is None:
            PTK.objects.create(audit=audit, temuan=t, nomor_urut=i)
        else:
            ptk.nomor_urut = i
            ptk.save(update_fields=["nomor_urut"])


@transaction.atomic
def ajukan_ke_auditee(audit, penugasan, dicentang):
    """FR-38: checklist ketua → Menunggu Persetujuan Auditee."""
    _pastikan_ketua(penugasan)
    _pastikan_perumusan(audit)
    sinkron_temuan(audit)
    belum = syarat_ketua(audit)
    if belum:
        raise ValidationError(belum)
    kurang = [label for kunci, label in CHECKLIST_KETUA if kunci not in dicentang]
    if kurang:
        raise ValidationError("Centang semua item checklist ketua.")
    hasil = hitung_final(audit, penugasan.pengguna)
    _nomori_ptk(audit)
    Persetujuan.objects.create(
        audit=audit, pihak=Persetujuan.Pihak.KETUA, oleh=penugasan.pengguna,
        keputusan=Persetujuan.Keputusan.SETUJU, checklist=sorted(dicentang),
    )
    status.ubah_status(
        audit, S.MENUNGGU_PERSETUJUAN, penugasan.pengguna,
        alasan=f"Checklist ketua lengkap. NE final {hasil.ne}, NK {hasil.nk}.",
    )
    return hasil


# --- Persetujuan auditee dan keberatan (FR-38, BR-18) -------------------------------------

def sudah_keberatan(audit):
    return audit.persetujuan.filter(pihak=Persetujuan.Pihak.AUDITEE, keputusan=Persetujuan.Keputusan.KEBERATAN).exists()


def _pastikan_auditee(penugasan):
    if penugasan is None or penugasan.peran != Penugasan.Peran.AUDITEE:
        raise PermissionError("Hanya auditee yang dapat memberikan persetujuan.")


@transaction.atomic
def setujui(audit, penugasan, dicentang):
    _pastikan_auditee(penugasan)
    if audit.status != S.MENUNGGU_PERSETUJUAN:
        raise ValidationError("Audit tidak sedang menunggu persetujuan auditee.")
    if any(kunci not in dicentang for kunci, _ in CHECKLIST_AUDITEE):
        raise ValidationError("Centang semua item checklist persetujuan.")
    Persetujuan.objects.create(
        audit=audit, pihak=Persetujuan.Pihak.AUDITEE, oleh=penugasan.pengguna,
        keputusan=Persetujuan.Keputusan.SETUJU, checklist=sorted(dicentang),
    )
    # Pembuatan PDF dan email Final dikerjakan modul documents/notifications lewat antrean.
    status.ubah_status(audit, S.FINAL, penugasan.pengguna, alasan="Auditee menyetujui hasil AMI.")
    from .tindak_lanjut import tutup_bila_tanpa_ptk

    tutup_bila_tanpa_ptk(audit, penugasan.pengguna)


@transaction.atomic
def ajukan_keberatan(audit, penugasan, keberatan):
    """BR-18: keberatan tertulis sekali; audit kembali ke Perumusan Temuan."""
    _pastikan_auditee(penugasan)
    if audit.status != S.MENUNGGU_PERSETUJUAN:
        raise ValidationError("Audit tidak sedang menunggu persetujuan auditee.")
    if sudah_keberatan(audit):
        raise ValidationError("Keberatan hanya dapat diajukan sekali.")
    keberatan = (keberatan or "").strip()
    if not keberatan:
        raise ValidationError("Tuliskan isi keberatan Anda.")
    Persetujuan.objects.create(
        audit=audit, pihak=Persetujuan.Pihak.AUDITEE, oleh=penugasan.pengguna,
        keputusan=Persetujuan.Keputusan.KEBERATAN, keberatan=keberatan,
    )
    status.ubah_status(audit, S.PERUMUSAN_TEMUAN, penugasan.pengguna, alasan="Auditee mengajukan keberatan.")


def tanggapi_keberatan(audit, penugasan, tanggapan):
    from django.utils import timezone

    _pastikan_ketua(penugasan)
    _pastikan_perumusan(audit)
    p = keberatan_belum_ditanggapi(audit)
    if p is None:
        raise ValidationError("Tidak ada keberatan yang perlu ditanggapi.")
    tanggapan = (tanggapan or "").strip()
    if not tanggapan:
        raise ValidationError("Tanggapan wajib diisi.")
    p.tanggapan, p.ditanggapi_pada = tanggapan, timezone.now()
    p.save(update_fields=["tanggapan", "ditanggapi_pada"])


# --- PTK oleh auditee (FR-36) ---------------------------------------------------------

def isi_ptk(audit, penugasan, ptk, data):
    _pastikan_auditee(penugasan)
    if audit.status != S.FINAL:
        # Setelah rencana dikirim (Tindak Lanjut PTK) rencana terkunci; auditee mengisi realisasi.
        raise ValidationError("Rencana PTK diisi setelah hasil audit Final dan terkunci setelah dikirim.")
    ptk.akar_masalah = (data.get("akar_masalah") or "").strip()
    ptk.rencana_tindakan = (data.get("rencana_tindakan") or "").strip()
    ptk.target_tanggal = data.get("target_tanggal") or None
    ptk.pic = (data.get("pic") or "").strip()
    ptk.status = PTK.Status.DIRENCANAKAN if ptk.rencana_lengkap else PTK.Status.TERBUKA
    ptk.diubah_oleh = penugasan.pengguna
    ptk.save()
    ptk_diperbarui.send(sender=PTK, ptk=ptk)
    return ptk
