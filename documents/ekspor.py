"""Isi berkas rapor, rekap periode, dan data mentah (FR-44, FR-48, FR-51). Dipanggil dari tugas antrean saja."""

import io

from django.template.loader import render_to_string
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font

from audits import analitik, grafik
from audits.models import Audit
from masterdata.excel import tulis_baris
from masterdata.models import PengaturanInstitusi, Periode

from .pdf import data_uri, render_pdf


def _ya_tidak(nilai):
    return "" if nilai is None else ("Memenuhi KKM" if nilai else "Belum Memenuhi KKM")


def _judul(ws, teks_judul, kolom):
    ws.append([teks_judul])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append([f"Dibuat {timezone.localtime():%d-%m-%Y %H.%M} oleh SI-AMI"])
    ws.append([])
    ws.append(kolom)
    for sel in ws[ws.max_row]:
        sel.font = Font(bold=True)
    # Koordinat teks: ws.cell() akan membuat sel kosong dan menggeser baris data.
    ws.freeze_panes = f"A{ws.max_row + 1}"


def _sheet_rapor(ws, judul, baris):
    maks_auditor = max((len(b["auditor"]) for b in baris), default=0)
    kolom = ["No.", "Unit", "Tipe", "Fakultas", "Status"]
    for i in range(1, maks_auditor + 1):
        kolom += [f"Auditor {i}", f"N auditor {i}"]
    kolom += ["Deviasi (D)", "NE awal", "NE final", "Status KKM", "NK", "Hasil akhir",
              "Kelebihan", "KTS", "OB", "Peluang", "PTK", "PTK rencana diisi"]
    _judul(ws, judul, kolom)
    for i, b in enumerate(baris, start=1):
        nilai = [i, str(b["unit"]), str(b["unit"].tipe), str(b["fakultas"] or ""), b["audit"].get_status_display()]
        for orang, n in b["auditor"]:
            nilai += [str(orang), float(n) if n else None]
        nilai += [None, None] * (maks_auditor - len(b["auditor"]))
        nilai += [
            b["deviasi"], b["ne_awal"], b["ne"], _ya_tidak(b["memenuhi_kkm"]), b["nk"],
            b["hasil_akhir"] if b["hasil_akhir"] is not None else "Menunggu keputusan LPM",
            b["kelebihan"], b["kts"], b["ob"], b["peluang"], b["ptk_total"], b["ptk_direncanakan"],
        ]
        tulis_baris(ws, nilai)
    ws.column_dimensions["B"].width = 34


def _sheet_temuan(ws, audits):
    _judul(ws, "Daftar temuan", ["Unit", "Jenis", "Kode PTK", "Butir", "Uraian"])
    for a in audits.prefetch_related("temuan__pernyataan", "temuan__ptk"):
        for t in a.temuan.all():
            ptk = getattr(t, "ptk", None) if t.jenis in ("KTS", "OB") else None
            tulis_baris(ws, [str(a.unit), t.get_jenis_display(), ptk.kode if ptk else "",
                             t.pernyataan.kode if t.pernyataan_id else "", t.uraian])
    ws.column_dimensions["E"].width = 80


def _sheet_butir(ws, data):
    _judul(ws, "Skor per butir (rata-rata kategori final)", ["Butir", "Pernyataan", "Rata-rata", "KTS", "OB", "Sesuai", "Pelampauan", "n"])
    awal = ws.max_row + 1
    for r in data["baris"]:
        j = r["jumlah"]
        tulis_baris(ws, [r["butir"].kode, r["butir"].pernyataan, float(r["rata"]), j["KTS"], j["OB"], j["SESUAI"], j["PELAMPAUAN"], r["n"]])
    akhir = ws.max_row
    ws.column_dimensions["B"].width = 60
    if akhir >= awal:
        chart = BarChart()
        chart.title = "Rata-rata skor per butir"
        chart.y_axis.title = "Skor"
        chart.y_axis.scaling.min = 0
        chart.y_axis.scaling.max = data["skor_maks"]
        chart.add_data(Reference(ws, min_col=3, min_row=awal - 1, max_row=akhir), titles_from_data=True)
        chart.set_categories(Reference(ws, min_col=1, min_row=awal, max_row=akhir))
        chart.width, chart.height = max(18, (akhir - awal) * 0.6), 9
        ws.add_chart(chart, "J5")


def _simpan(wb):
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def rapor(parameter):
    judul, audits = analitik.cakupan_rapor(parameter)
    wb = Workbook()
    _sheet_rapor(wb.active, f"Rapor AMI {judul}", analitik.baris_rapor(audits))
    wb.active.title = "Rapor"
    _sheet_temuan(wb.create_sheet("Temuan"), audits)
    return _simpan(wb)


def rekap_periode(parameter):
    """FR-44 / BRD 8.2: semua auditee dalam satu periode, dengan grafik per butir (Excel dan PDF)."""
    periode = Periode.objects.get(pk=parameter["periode"])
    audits = analitik.audit_final(periode)
    baris = analitik.baris_rapor(audits)
    butir = analitik.per_butir(audits, periode)
    wb = Workbook()
    wb.active.title = "Rekap"
    _sheet_rapor(wb.active, f"Rekapitulasi AMI {periode}", baris)
    _sheet_butir(wb.create_sheet("Per butir"), butir)
    _sheet_temuan(wb.create_sheet("Temuan"), audits)
    institusi = PengaturanInstitusi.muat()
    html = render_to_string(
        "documents/pdf/rekap.html",
        {
            "periode": periode, "baris": baris, "butir": butir, "institusi": institusi, "logo": data_uri(institusi.logo),
            "svg_butir": grafik.batang_per_butir(butir["baris"], butir["skor_maks"], butir["skor_sesuai"]),
            "pengaturan": {"judul": "Rekapitulasi Audit Mutu Internal", "nomor_formulir": ""},
            "unit": periode, "tanggal_cetak": timezone.localdate(),
        },
    )
    return _simpan(wb), render_pdf(html)


def _data_mentah(audits, judul):
    params_cache = {}
    wb = Workbook()
    ws_ser = wb.active
    ws_ser.title = "SER"
    _judul(ws_ser, judul, ["Unit", "Butir", "Pernyataan", "Kategori auditee", "Hasil/penjelasan", "Bukti"])
    ws_nilai = wb.create_sheet("Penilaian")
    _judul(ws_nilai, "Penilaian auditor", ["Unit", "Butir", "Auditor", "Kategori", "Skor", "Dasar penilaian", "Kondisi faktual"])
    ws_final = wb.create_sheet("Kategori final")
    _judul(ws_final, "Kategori final", ["Unit", "Butir", "Kategori", "Cara penetapan", "Alasan"])
    ws_hasil = wb.create_sheet("Hasil")
    _judul(ws_hasil, "Hasil perhitungan", ["Unit", "Tahap", "Rata-rata", "D", "NE", "Status KKM", "NK", "Hasil akhir", "KTS", "OB", "Kelebihan"])
    ws_ptk = wb.create_sheet("PTK")
    _judul(ws_ptk, "PTK", ["Unit", "Kode", "Nomor surat", "Butir", "Akar masalah", "Rencana", "Target", "PIC", "Status"])

    for a in audits.prefetch_related(
        "jawaban_ser__pernyataan", "jawaban_ser__bukti", "penilaian__pernyataan", "penilaian__auditor",
        "kategori_final__pernyataan", "hasil", "ptk__temuan__pernyataan",
    ):
        unit = str(a.unit)
        if a.periode_id not in params_cache:
            params_cache[a.periode_id] = a.periode.parameter()
        params = params_cache[a.periode_id]
        for j in sorted(a.jawaban_ser.all(), key=lambda j: j.pernyataan.kode):
            tulis_baris(ws_ser, [unit, j.pernyataan.kode, j.pernyataan.pernyataan, j.get_kategori_display(), j.penjelasan,
                                 "\n".join(b.url or b.nama for b in j.bukti.all())])
        for p in sorted(a.penilaian.all(), key=lambda p: (p.pernyataan.kode, p.auditor.nama)):
            tulis_baris(ws_nilai, [unit, p.pernyataan.kode, str(p.auditor), p.get_kategori_display(),
                                   params.skor(p.kategori) if p.kategori else None, p.dasar_penilaian, p.kondisi_faktual])
        for k in sorted(a.kategori_final.all(), key=lambda k: k.pernyataan.kode):
            tulis_baris(ws_final, [unit, k.pernyataan.kode, k.get_kategori_display(), k.get_cara_display(), k.alasan])
        for h in a.hasil.all():
            tulis_baris(ws_hasil, [unit, h.get_tahap_display(), h.rata_rata, h.deviasi, h.ne, _ya_tidak(h.memenuhi_kkm),
                                   h.nk, h.hasil_akhir, h.jumlah_kts, h.jumlah_ob, h.jumlah_kelebihan])
        for p in a.ptk.all():
            tulis_baris(ws_ptk, [unit, p.kode, p.nomor_surat, p.temuan.pernyataan.kode if p.temuan.pernyataan_id else "",
                                 p.akar_masalah, p.rencana_tindakan, p.target_tanggal, p.pic, p.get_status_display()])
    return _simpan(wb)


def data_audit(parameter):
    a = Audit.objects.select_related("unit", "periode").get(pk=parameter["audit"])
    return _data_mentah(Audit.objects.filter(pk=a.pk).select_related("unit", "periode"), f"Data mentah AMI {a.unit} — {a.periode}")


def data_periode(parameter):
    periode = Periode.objects.get(pk=parameter["periode"])
    audits = Audit.objects.filter(periode=periode).select_related("unit", "periode").order_by("unit__nama")
    return _data_mentah(audits, f"Data mentah AMI {periode}")



def log_audit(parameter):
    """NFR-10: log audit dalam rentang tanggal (waktu lokal), khusus Master Admin."""
    from datetime import date, datetime, time, timedelta
    import json

    from accounts.models import LogAudit

    dari = timezone.make_aware(datetime.combine(date.fromisoformat(parameter["dari"]), time.min))
    sampai = timezone.make_aware(datetime.combine(date.fromisoformat(parameter["sampai"]) + timedelta(days=1), time.min))
    wb = Workbook()
    ws = wb.active
    ws.title = "Log audit"
    _judul(ws, f"Log audit {parameter['dari']} s.d. {parameter['sampai']}",
           ["Waktu", "Aksi", "Aktor", "Objek", "Id audit", "Data", "Alasan", "IP", "Hash isi"])
    for log in LogAudit.objects.filter(waktu__gte=dari, waktu__lt=sampai).order_by("waktu", "id").iterator():
        tulis_baris(ws, [
            timezone.localtime(log.waktu).strftime("%Y-%m-%d %H:%M:%S"), log.get_aksi_display(), log.aktor_email,
            log.objek_nama, log.audit_id, json.dumps(log.data, ensure_ascii=False), log.alasan, log.ip, log.hash_isi,
        ])
    ws.column_dimensions["F"].width = 60
    return _simpan(wb)
