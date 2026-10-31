"""Data untuk template dokumen (BRD 8.2). Tidak ada perhitungan baru: semua angka dari HasilPerhitungan."""

import io

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from audits import penilaian as penilaian_layanan
from audits.models import HasilPerhitungan, Penugasan
from findings import tindak_lanjut
from findings.models import Kesimpulan, Temuan
from masterdata.excel import tulis_baris
from masterdata.models import PengaturanInstitusi, TahapanPeriode, TujuanAudit

from .models import JenisDokumen, PengaturanDokumen
from .pdf import data_uri


def _tim(audit):
    tim = list(audit.penugasan.select_related("pengguna").order_by("peran", "-ketua", "pengguna__nama"))
    return {
        "tim": tim,
        "auditee": next((p.pengguna for p in tim if p.peran == Penugasan.Peran.AUDITEE), None),
        "ketua": next((p.pengguna for p in tim if p.ketua), None),
        "anggota": [p.pengguna for p in tim if p.peran == Penugasan.Peran.AUDITOR and not p.ketua],
    }


def _hasil(audit):
    return (
        audit.hasil_tahap(HasilPerhitungan.Tahap.FINAL)
        or audit.hasil_tahap(HasilPerhitungan.Tahap.SETELAH_AL)
        or audit.hasil_tahap(HasilPerhitungan.Tahap.AWAL)
    )


def _temuan(audit):
    temuan = list(audit.temuan.select_related("pernyataan__standar", "ptk"))
    return {
        "kelebihan": [t for t in temuan if t.jenis == Temuan.Jenis.KELEBIHAN],
        "kts_ob": [t for t in temuan if t.jenis in Temuan.JENIS_PTK],
        "peluang": [t for t in temuan if t.jenis == Temuan.Jenis.PELUANG],
    }


def daftar_tilik(audit):
    """Baris Daftar Tilik: butir, isian auditee, bukti, penilaian semua auditor, kategori final."""
    params = audit.periode.parameter()
    auditor, baris = penilaian_layanan.tabel_perbedaan(audit)
    jawaban = {j.pernyataan_id: j for j in audit.jawaban_ser.prefetch_related("bukti")}
    for r in baris:
        r["jawaban"] = jawaban.get(r["butir"].pk)
        r["sel"] = [
            {
                "penilaian": p,
                "skor": params.skor(p.kategori) if p and p.kategori and not r["tidak_berlaku"] else None,
            }
            for _, p in r["penilaian"]
        ]
    hasil = _hasil(audit)
    nilai = [(a.pengguna, hasil.nilai_auditor.get(str(a.pengguna_id)) if hasil else None) for a in auditor]
    return {"auditor": auditor, "baris": baris, "nilai_auditor": nilai}


def konteks(dokumen):
    audit = dokumen.audit
    institusi = PengaturanInstitusi.muat()
    k = {
        "dokumen": dokumen,
        "audit": audit,
        "unit": audit.unit,
        "periode": audit.periode,
        "lingkup": list(audit.lingkup.all()),
        "institusi": institusi,
        "logo": data_uri(institusi.logo),
        "pengaturan": PengaturanDokumen.untuk(dokumen.jenis),
        "nomor": dokumen.nomor_aktif(),
        "tanggal_cetak": timezone.localdate(),
        "cp_lpm": audit.periode.cp_lpm,
        **_tim(audit),
    }
    jenis = dokumen.jenis
    if jenis in (JenisDokumen.DAFTAR_TILIK, JenisDokumen.LAPORAN_AMI):
        k.update(daftar_tilik(audit))
    if jenis in (JenisDokumen.TEMUAN, JenisDokumen.LAPORAN_AMI):
        k.update(_temuan(audit))
    if jenis == JenisDokumen.PTK:
        k["ptk"] = dokumen.ptk
    if jenis in (JenisDokumen.BERITA_ACARA, JenisDokumen.LAPORAN_AMI):
        k["hasil_awal"] = audit.hasil_tahap(HasilPerhitungan.Tahap.AWAL)
        k["hasil_al"] = audit.hasil_tahap(HasilPerhitungan.Tahap.SETELAH_AL)
    if jenis == JenisDokumen.LAPORAN_AMI:
        kesimpulan = Kesimpulan.objects.filter(audit=audit).prefetch_related("tujuan_tercapai").first()
        opsi = dict(audit.periode.pengaturan.opsi_kesimpulan())
        tercapai = set(kesimpulan.tujuan_tercapai.values_list("pk", flat=True)) if kesimpulan else set()
        k.update(
            {
                "kesimpulan": kesimpulan,
                "label_a": opsi.get(kesimpulan.skor_a) if kesimpulan else None,
                "label_b": opsi.get(kesimpulan.skor_b) if kesimpulan else None,
                "label_c": opsi.get(kesimpulan.skor_c) if kesimpulan else None,
                "tujuan": [(t, t.pk in tercapai) for t in TujuanAudit.objects.filter(aktif=True)],
                "hasil": _hasil(audit),
                "daftar_ptk": list(audit.ptk.select_related("temuan__pernyataan")),
                # Lampiran D: verifikasi PTK periode lalu (FR-37).
                "ptk_lalu": tindak_lanjut.ptk_periode_lalu(audit),
                "jadwal": list(audit.periode.tahapan.all()),
                "jenis_tahapan": TahapanPeriode.Jenis,
            }
        )
    return k


def excel_daftar_tilik(audit):
    """Daftar Tilik versi Excel (BRD 8.2), dibuat di antrean bersama PDF-nya."""
    data = daftar_tilik(audit)
    wb = Workbook()
    ws = wb.active
    ws.title = "Daftar Tilik"
    ws.append([f"Daftar Tilik — {audit.unit} — {audit.periode}"])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append([])
    judul = ["Kode", "Pernyataan standar", "Hasil/penjelasan auditee", "Bukti"]
    for a in data["auditor"]:
        nama = str(a.pengguna)
        judul += [f"{nama} — kategori", f"{nama} — skor", f"{nama} — dasar penilaian", f"{nama} — kondisi faktual"]
    judul.append("Kategori final")
    ws.append(judul)
    for sel in ws[3]:
        sel.font = Font(bold=True)
        sel.alignment = Alignment(wrap_text=True, vertical="top")
    for r in data["baris"]:
        j = r["jawaban"]
        baris = [
            r["butir"].kode,
            r["butir"].pernyataan,
            j.penjelasan if j else "",
            "\n".join(b.url or b.nama for b in j.bukti.all()) if j else "",
        ]
        for s in r["sel"]:
            p = s["penilaian"]
            baris += [
                p.get_kategori_display() if p else "",
                s["skor"],
                p.dasar_penilaian if p else "",
                p.kondisi_faktual if p else "",
            ]
        final = r["final"]
        baris.append("Tidak berlaku" if r["tidak_berlaku"] else (final.get_kategori_display() if final else ""))
        tulis_baris(ws, baris)
    ws.append([])
    # Nama auditor di kolom kategori, N di kolom skor masing-masing.
    ws.append(
        ["Nilai per auditor (N)", "", "", ""]
        + [v for orang, n in data["nilai_auditor"] for v in (str(orang), n, "", "")]
    )
    for kolom, lebar in zip("ABCD", (10, 50, 50, 40)):
        ws.column_dimensions[kolom].width = lebar
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
