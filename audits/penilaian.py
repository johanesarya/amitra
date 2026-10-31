"""Penilaian auditor, rekonsiliasi, dan Audit Lapangan (FR-25 s.d. FR-31, BR-02 s.d. BR-13).

Semua rumus memanggil `scoring` dengan parameter Pengaturan periode; modul ini
hanya mengumpulkan data dan menyimpan hasil.
"""

from collections import defaultdict
from fractions import Fraction

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from scoring.parameter import Kategori
from scoring.rumus import (
    bulatkan,
    butir_penyumbang_deviasi,
    deviasi,
    hitung_jumlah_temuan,
    kategori_mayoritas,
    memenuhi_kkm,
    nilai_auditor,
    nilai_efektif,
    perlu_audit_lapangan,
    rata_rata,
)

from . import status
from .sinyal import kunci_penilaian_direset
from .models import Audit, HasilPerhitungan, KategoriFinal, Penilaian, Penugasan

S = Audit.Status
STATUS_SETELAH_FINAL = frozenset({S.FINAL, S.TINDAK_LANJUT_PTK, S.DITUTUP})


class PenilaianTerkunci(Exception):
    pass


class KonflikVersi(Exception):
    def __init__(self, penilaian):
        super().__init__("Penilaian butir ini sudah diubah di tab atau perangkat lain.")
        self.penilaian = penilaian


# --- Data dasar -----------------------------------------------------------------------

def tim_auditor(audit):
    return list(
        audit.penugasan.filter(peran=Penugasan.Peran.AUDITOR).select_related("pengguna").order_by("-ketua", "pengguna__nama")
    )


def id_tidak_berlaku(audit):
    return set(audit.kategori_final.filter(cara=KategoriFinal.Cara.TIDAK_BERLAKU).values_list("pernyataan_id", flat=True))


def butir_dinilai(audit):
    """Butir berlaku yang wajib dinilai (BR-03: tanpa butir tidak berlaku)."""
    tb = id_tidak_berlaku(audit)
    return [p for p in audit.pernyataan_berlaku() if p.pk not in tb]


def penilaian_terbuka(audit):
    return audit.status == S.PENILAIAN_AUDITOR or (audit.status == S.PERLU_AUDIT_LAPANGAN and audit.revisi_al_dibuka)


def butir_bisa_diubah(audit, pernyataan_id):
    if audit.status == S.PENILAIAN_AUDITOR:
        return pernyataan_id not in id_tidak_berlaku(audit)
    if audit.status == S.PERLU_AUDIT_LAPANGAN and audit.revisi_al_dibuka:
        return pernyataan_id in audit.butir_revisi_al
    return False


def boleh_lihat_penilaian_lain(user, audit, penugasan):
    """BR-04 dan keputusan 31 Okt 2026: auditor (termasuk ketua) baru melihat skor anggota lain
    setelah mengunci penilaiannya sendiri; staf LPM kapan saja."""
    if user.has_perm("audits.view_audit"):
        return True
    if penugasan is not None and penugasan.peran == Penugasan.Peran.AUDITEE:
        # Bab 4: auditee melihat skor auditor setelah Final.
        return audit.status in STATUS_SETELAH_FINAL
    if penugasan is None:
        # FR-24: auditee unit ini (termasuk pimpinan baru) melihat riwayat audit Final.
        from .akses import akses_riwayat_unit

        return akses_riwayat_unit(user, audit)
    if penugasan.peran != Penugasan.Peran.AUDITOR:
        return False
    return penugasan.dikunci_pada is not None or audit.hasil.exists()


# --- Isian penilaian ----------------------------------------------------------------

def pastikan_penilaian(audit, auditor):
    ada = set(audit.penilaian.filter(auditor=auditor).values_list("pernyataan_id", flat=True))
    Penilaian.objects.bulk_create(
        [Penilaian(audit=audit, pernyataan=p, auditor=auditor) for p in audit.pernyataan_berlaku() if p.pk not in ada],
        ignore_conflicts=True,
    )


def _pastikan_bisa_ubah(audit, penugasan, pernyataan_id):
    if not penilaian_terbuka(audit):
        raise PenilaianTerkunci("Penilaian sedang tidak dibuka untuk audit ini.")
    if penugasan.dikunci_pada is not None:
        raise PenilaianTerkunci("Penilaian Anda sudah dikunci.")
    if not butir_bisa_diubah(audit, pernyataan_id):
        raise PenilaianTerkunci("Butir ini tidak dapat dinilai saat ini.")


@transaction.atomic
def simpan_penilaian(audit, penugasan, pernyataan_id, kategori, dasar, kondisi, versi):
    """Autosave satu butir dengan optimistic locking (NFR-05). Isian boleh belum lengkap."""
    _pastikan_bisa_ubah(audit, penugasan, pernyataan_id)
    if kategori and kategori not in Penilaian.Kategori.values:
        raise ValidationError("Kategori tidak dikenal.")
    if not audit.pernyataan_berlaku().filter(pk=pernyataan_id).exists():
        raise ValidationError("Butir ini tidak termasuk audit ini.")
    p, _ = Penilaian.objects.get_or_create(audit=audit, pernyataan_id=pernyataan_id, auditor=penugasan.pengguna)
    kategori_lama = p.kategori
    diubah = Penilaian.objects.filter(pk=p.pk, versi=versi).update(
        kategori=kategori or "", dasar_penilaian=dasar or "", kondisi_faktual=kondisi or "",
        versi=F("versi") + 1, diubah_pada=timezone.now(),
    )
    p.refresh_from_db()
    if not diubah:
        raise KonflikVersi(p)
    if p.kategori != kategori_lama:
        # NFR-10: perubahan skor; autosave teks dasar penilaian tidak dicatat agar log tidak membanjir.
        from accounts.jejak import catat
        from accounts.models import LogAudit

        catat(LogAudit.Aksi.SKOR_DIUBAH, objek=p, audit_id=audit.pk, aktor=penugasan.pengguna,
              data={"butir": p.pernyataan.kode, "auditor": penugasan.pengguna.email, "dari": kategori_lama, "ke": p.kategori})
    return p


def ringkasan(audit, penugasan):
    """Butir yang belum lengkap untuk auditor ini: [(butir, ["kategori", ...])]."""
    milik = {p.pernyataan_id: p for p in audit.penilaian.filter(auditor=penugasan.pengguna)}
    belum = []
    for butir in butir_dinilai(audit):
        p = milik.get(butir.pk)
        kurang = p.kurang if p else ["kategori", "dasar penilaian"]
        if kurang:
            belum.append((butir, kurang))
    return belum


@transaction.atomic
def kunci(audit, penugasan, oleh):
    """FR-27: auditor mengunci penilaiannya; bila semua sudah, lanjut ke rekonsiliasi."""
    # Kunci baris audit agar dua auditor terakhir yang mengunci bersamaan tidak saling melewatkan transisi.
    Audit.objects.select_for_update().filter(pk=audit.pk).first()
    penugasan.refresh_from_db()
    if not penilaian_terbuka(audit):
        raise PenilaianTerkunci("Penilaian sedang tidak dibuka untuk audit ini.")
    if penugasan.dikunci_pada is not None:
        raise PenilaianTerkunci("Penilaian Anda sudah dikunci.")
    belum = ringkasan(audit, penugasan)
    if belum:
        raise ValidationError(f"Masih ada {len(belum)} butir yang belum lengkap.")
    penugasan.dikunci_pada = timezone.now()
    penugasan.save(update_fields=["dikunci_pada"])
    status.catat(audit, oleh, f"Penilaian {penugasan.pengguna} dikunci.")
    if all(p.dikunci_pada for p in tim_auditor(audit)):
        _semua_terkunci(audit, oleh)


def _semua_terkunci(audit, oleh):
    if audit.status == S.PENILAIAN_AUDITOR:
        status.ubah_status(audit, S.REKONSILIASI, oleh, alasan="Semua auditor telah mengunci penilaian.")
        tetapkan_mayoritas(audit)
        coba_selesaikan_rekonsiliasi(audit, oleh)
    elif audit.status == S.PERLU_AUDIT_LAPANGAN:
        audit.revisi_al_dibuka = False
        audit.save(update_fields=["revisi_al_dibuka", "diubah_pada"])
        tetapkan_mayoritas(audit)
        status.catat(audit, oleh, "Revisi penilaian pasca Audit Lapangan selesai; menunggu ketua menyelesaikan follow-up.")


def reset_kunci_semua(audit, oleh, alasan):
    """Dipanggil saat SER dibuka kembali: semua auditor menilai ulang isian yang berubah."""
    jumlah = audit.penugasan.filter(peran=Penugasan.Peran.AUDITOR, dikunci_pada__isnull=False).update(dikunci_pada=None)
    if jumlah:
        status.catat(audit, oleh, f"Kunci penilaian {jumlah} auditor direset: {alasan}")


@transaction.atomic
def reset_kunci(audit, penugasan, oleh, alasan):
    """Bab 4: Master Admin mereset kunci satu auditor dengan alasan."""
    alasan = (alasan or "").strip()
    if not alasan:
        raise ValidationError("Alasan wajib diisi.")
    if penugasan.dikunci_pada is None:
        raise ValidationError(f"Penilaian {penugasan.pengguna} belum dikunci.")
    if audit.status == S.REKONSILIASI:
        status.ubah_status(audit, S.PENILAIAN_AUDITOR, oleh, alasan=f"Reset kunci {penugasan.pengguna}: {alasan}")
        audit.kategori_final.exclude(cara=KategoriFinal.Cara.TIDAK_BERLAKU).delete()
    elif audit.status == S.PENILAIAN_AUDITOR:
        status.catat(audit, oleh, f"Reset kunci {penugasan.pengguna}: {alasan}")
    else:
        raise ValidationError(f"Kunci tidak dapat direset pada status {audit.get_status_display()}.")
    penugasan.dikunci_pada = None
    penugasan.save(update_fields=["dikunci_pada"])
    kunci_penilaian_direset.send(sender=Audit, audit=audit, penugasan=penugasan, alasan=alasan)


# --- Butir tidak berlaku (BR-03) -----------------------------------------------------

def _pastikan_ketua(penugasan):
    if penugasan is None or not penugasan.ketua:
        raise PermissionError("Hanya ketua auditor yang dapat melakukan tindakan ini.")


@transaction.atomic
def tandai_tidak_berlaku(audit, penugasan, pernyataan_id, alasan):
    _pastikan_ketua(penugasan)
    if audit.status != S.PENILAIAN_AUDITOR:
        raise ValidationError("Butir hanya dapat ditandai tidak berlaku selama Penilaian Auditor.")
    alasan = (alasan or "").strip()
    if not alasan:
        raise ValidationError("Alasan wajib diisi.")
    if not audit.pernyataan_berlaku().filter(pk=pernyataan_id).exists():
        raise ValidationError("Butir ini tidak termasuk audit ini.")
    if len(butir_dinilai(audit)) <= 1:
        raise ValidationError("Minimal satu butir harus tetap dinilai.")
    KategoriFinal.objects.update_or_create(
        audit=audit, pernyataan_id=pernyataan_id,
        defaults={"cara": KategoriFinal.Cara.TIDAK_BERLAKU, "kategori": "", "alasan": alasan,
                  "ditetapkan_oleh": penugasan.pengguna},
    )
    status.catat(audit, penugasan.pengguna, f"Butir ditandai tidak berlaku: {alasan}")


@transaction.atomic
def batal_tidak_berlaku(audit, penugasan, pernyataan_id):
    _pastikan_ketua(penugasan)
    if audit.status != S.PENILAIAN_AUDITOR:
        raise ValidationError("Tanda tidak berlaku hanya dapat dibatalkan selama Penilaian Auditor.")
    audit.kategori_final.filter(pernyataan_id=pernyataan_id, cara=KategoriFinal.Cara.TIDAK_BERLAKU).delete()
    # Auditor yang sudah mengunci tanpa menilai butir ini harus melengkapinya.
    for p in tim_auditor(audit):
        if p.dikunci_pada is None:
            continue
        pen = audit.penilaian.filter(auditor=p.pengguna, pernyataan_id=pernyataan_id).first()
        if pen is None or not pen.lengkap:
            p.dikunci_pada = None
            p.save(update_fields=["dikunci_pada"])
            status.catat(audit, penugasan.pengguna, f"Kunci {p.pengguna} dibuka: butir kembali berlaku dan belum dinilai.")
    status.catat(audit, penugasan.pengguna, "Tanda tidak berlaku pada butir dibatalkan.")


# --- Rekonsiliasi (BR-13, FR-28) -------------------------------------------------------

def _penilaian_per_butir(audit, butir_ids):
    hasil = defaultdict(dict)  # butir → {id auditor: kategori}
    for p in audit.penilaian.filter(pernyataan_id__in=butir_ids):
        hasil[p.pernyataan_id][p.auditor_id] = p.kategori
    return hasil


def tetapkan_mayoritas(audit):
    """BR-13: kategori terbanyak per butir. Bila seri, penetapan ketua sebelumnya dipertahankan
    selama kategorinya masih salah satu yang seri; selain itu butir menunggu ketua."""
    auditor_ids = [p.pengguna_id for p in tim_auditor(audit)]
    butir = butir_dinilai(audit)
    per_butir = _penilaian_per_butir(audit, [b.pk for b in butir])
    lama = {k.pernyataan_id: k for k in audit.kategori_final.exclude(cara=KategoriFinal.Cara.TIDAK_BERLAKU)}
    for b in butir:
        suara = [Kategori(per_butir[b.pk][a]) for a in auditor_ids]
        modus = kategori_mayoritas(suara)
        k = lama.get(b.pk)
        if modus is not None:
            KategoriFinal.objects.update_or_create(
                audit=audit, pernyataan=b,
                defaults={"kategori": modus.value, "cara": KategoriFinal.Cara.MAYORITAS, "alasan": "", "ditetapkan_oleh": None},
            )
        elif k is not None and k.cara == KategoriFinal.Cara.KETUA and k.kategori in {s.value for s in suara}:
            continue
        else:
            KategoriFinal.objects.update_or_create(
                audit=audit, pernyataan=b,
                defaults={"kategori": "", "cara": KategoriFinal.Cara.KETUA, "alasan": "", "ditetapkan_oleh": None},
            )


def butir_seri(audit):
    return [k for k in audit.kategori_final.select_related("pernyataan__standar") if k.seri]


@transaction.atomic
def tetapkan_seri(audit, penugasan, pernyataan_id, kategori, alasan):
    """BR-13: ketua menetapkan kategori butir tanpa satu kategori terbanyak, alasan wajib."""
    _pastikan_ketua(penugasan)
    if audit.status not in (S.REKONSILIASI, S.PERLU_AUDIT_LAPANGAN):
        raise ValidationError("Kategori butir seri hanya ditetapkan saat Rekonsiliasi atau Audit Lapangan.")
    if kategori not in Penilaian.Kategori.values:
        raise ValidationError("Pilih kategori.")
    alasan = (alasan or "").strip()
    if not alasan:
        raise ValidationError("Alasan penetapan wajib diisi.")
    k = audit.kategori_final.filter(pernyataan_id=pernyataan_id).exclude(cara=KategoriFinal.Cara.TIDAK_BERLAKU).first()
    if k is None or k.cara != KategoriFinal.Cara.KETUA:
        raise ValidationError("Butir ini tidak memerlukan penetapan ketua.")
    k.kategori, k.alasan, k.ditetapkan_oleh = kategori, alasan, penugasan.pengguna
    k.save()
    from accounts.jejak import catat
    from accounts.models import LogAudit

    catat(LogAudit.Aksi.KATEGORI_FINAL, objek=k, audit_id=audit.pk, aktor=penugasan.pengguna,
          data={"butir": k.pernyataan.kode, "ke": kategori, "cara": "seri"}, alasan=alasan)
    if audit.status == S.REKONSILIASI:
        coba_selesaikan_rekonsiliasi(audit, penugasan.pengguna)


def hitung(audit, tahap, oleh=None):
    """FR-28: N per auditor, D, NE, KKM, dan syarat Audit Lapangan dari Pengaturan periode."""
    params = audit.periode.parameter()
    auditor = tim_auditor(audit)
    butir = butir_dinilai(audit)
    ids = [b.pk for b in butir]
    per_butir = _penilaian_per_butir(audit, ids)

    nilai = {}
    for p in auditor:
        skor = [params.skor(per_butir[b][p.pengguna_id]) for b in ids]
        nilai[p.pengguna_id] = nilai_auditor(skor, params)
    daftar_nilai = list(nilai.values())
    d = deviasi(daftar_nilai, params)

    kategori_final = {k.pernyataan_id: k.kategori for k in audit.kategori_final.exclude(cara=KategoriFinal.Cara.TIDAK_BERLAKU)}
    if any(not kategori_final.get(b) for b in ids):
        raise ValidationError("Masih ada butir seri yang belum ditetapkan ketua.")
    temuan = hitung_jumlah_temuan([Kategori(kategori_final[b]) for b in ids])
    ne = nilai_efektif(daftar_nilai, temuan, params)

    hasil, _ = HasilPerhitungan.objects.update_or_create(
        audit=audit,
        tahap=tahap,
        defaults={
            "nilai_auditor": {str(a): str(bulatkan(n)) for a, n in nilai.items()},
            "rata_rata": bulatkan(rata_rata(daftar_nilai)),
            "deviasi": bulatkan(d),
            "ne": bulatkan(ne),
            # Keputusan memakai nilai eksak, bukan nilai yang dibulatkan.
            "memenuhi_kkm": memenuhi_kkm(ne, params),
            "perlu_audit_lapangan": perlu_audit_lapangan(d, ne, params),
            "deviasi_tinggi": d > Fraction(params.ambang_deviasi),
            "jumlah_kts": temuan.kts,
            "jumlah_ob": temuan.ob,
            "jumlah_kelebihan": temuan.kelebihan,
            "jumlah_butir": len(ids),
            "parameter": {
                "skor": {k.value: v for k, v in params.skor_kategori.items()},
                "kkm": str(params.kkm),
                "ambang_deviasi": str(params.ambang_deviasi),
                "penyesuaian_kts": str(params.penyesuaian_kts),
                "penyesuaian_ob": str(params.penyesuaian_ob),
                "penyesuaian_kelebihan": str(params.penyesuaian_kelebihan),
            },
            "penilaian": {str(p.pengguna_id): {str(b): per_butir[b][p.pengguna_id] for b in ids} for p in auditor},
            "dihitung_oleh": oleh,
        },
    )
    hasil.ne_eksak = ne  # untuk perhitungan lanjutan (hasil akhir) tanpa galat pembulatan
    return hasil


def coba_selesaikan_rekonsiliasi(audit, oleh):
    """Bila tidak ada butir seri: hitung hasil awal lalu putuskan Audit Lapangan (BR-07, BR-08)."""
    if audit.status != S.REKONSILIASI or butir_seri(audit):
        return None
    hasil = hitung(audit, HasilPerhitungan.Tahap.AWAL, oleh)
    if hasil.perlu_audit_lapangan:
        status.ubah_status(
            audit, S.PERLU_AUDIT_LAPANGAN, oleh,
            alasan=f"D = {hasil.deviasi} melebihi ambang dan NE = {hasil.ne} memenuhi KKM.",
        )
    else:
        status.ubah_status(audit, S.PERUMUSAN_TEMUAN, oleh, alasan=f"D = {hasil.deviasi}, NE = {hasil.ne}.")
    return hasil


# --- Audit Lapangan (FR-29, FR-30, opsi b) -------------------------------------------

def butir_penyumbang(audit):
    """BR-09: butir dengan kategori berbeda antar-auditor."""
    butir = butir_dinilai(audit)
    per_butir = _penilaian_per_butir(audit, [b.pk for b in butir])
    ids = set(butir_penyumbang_deviasi({b.pk: list(per_butir[b.pk].values()) for b in butir}))
    return [b for b in butir if b.pk in ids]


@transaction.atomic
def buka_revisi_al(audit, penugasan, butir_ids):
    """Ketua membuka butir tertentu untuk direvisi auditor setelah Audit Lapangan."""
    _pastikan_ketua(penugasan)
    if audit.status != S.PERLU_AUDIT_LAPANGAN:
        raise ValidationError("Revisi hanya dapat dibuka saat status Perlu Audit Lapangan.")
    if audit.revisi_al_dibuka:
        raise ValidationError("Revisi sedang berjalan.")
    berlaku = {b.pk for b in butir_dinilai(audit)}
    butir_ids = sorted({int(b) for b in butir_ids})
    if not butir_ids:
        raise ValidationError("Pilih minimal satu butir yang akan direvisi.")
    if not set(butir_ids) <= berlaku:
        raise ValidationError("Ada butir yang tidak termasuk penilaian audit ini.")
    audit.revisi_al_dibuka = True
    audit.butir_revisi_al = butir_ids
    audit.save(update_fields=["revisi_al_dibuka", "butir_revisi_al", "diubah_pada"])
    audit.penugasan.filter(peran=Penugasan.Peran.AUDITOR).update(dikunci_pada=None)
    status.catat(audit, penugasan.pengguna, f"Revisi pasca Audit Lapangan dibuka untuk {len(butir_ids)} butir.")


@transaction.atomic
def selesaikan_al(audit, penugasan, catatan):
    """FR-30: catat follow-up, hitung hasil setelah Audit Lapangan, lalu Perumusan Temuan."""
    _pastikan_ketua(penugasan)
    if audit.status != S.PERLU_AUDIT_LAPANGAN:
        raise ValidationError("Audit ini tidak sedang dalam tahap Audit Lapangan.")
    if audit.revisi_al_dibuka:
        raise ValidationError("Masih ada auditor yang belum mengunci revisi penilaian.")
    catatan = (catatan or "").strip()
    if not catatan:
        raise ValidationError("Catatan follow-up Audit Lapangan wajib diisi.")
    if butir_seri(audit):
        raise ValidationError("Masih ada butir seri yang belum ditetapkan ketua.")
    hasil = hitung(audit, HasilPerhitungan.Tahap.SETELAH_AL, penugasan.pengguna)
    audit.catatan_follow_up = catatan
    audit.save(update_fields=["catatan_follow_up", "diubah_pada"])
    status.ubah_status(
        audit, S.PERUMUSAN_TEMUAN, penugasan.pengguna,
        alasan=f"Audit Lapangan selesai. D = {hasil.deviasi}, NE setelah Audit Lapangan = {hasil.ne}.",
    )
    return hasil


# --- Tabel perbedaan (FR-31) ---------------------------------------------------------

def tabel_perbedaan(audit):
    auditor = tim_auditor(audit)
    final = {k.pernyataan_id: k for k in audit.kategori_final.all()}
    semua = {(p.pernyataan_id, p.auditor_id): p for p in audit.penilaian.all()}
    baris = []
    for b in audit.pernyataan_berlaku():
        sel = [semua.get((b.pk, a.pengguna_id)) for a in auditor]
        kategori = {s.kategori for s in sel if s is not None and s.kategori}
        k = final.get(b.pk)
        baris.append({
            "butir": b,
            "penilaian": list(zip(auditor, sel)),  # [(penugasan, penilaian atau None)]
            "final": k,
            "tidak_berlaku": bool(k and k.tidak_berlaku),
            "berbeda": len(kategori) > 1,
        })
    return auditor, baris
