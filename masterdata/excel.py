"""Bantuan bersama untuk impor Excel: baca tabel, hasil per baris, dan template.

Dipakai impor standar (FR-09) dan plot massal (FR-15).
"""

from dataclasses import dataclass, field
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils.exceptions import InvalidFileException

UKURAN_MAKS = 2 * 1024 * 1024
BARIS_MAKS = 2000


class GalatImpor(Exception):
    """Galat tingkat berkas (bukan per baris)."""


@dataclass
class BarisImpor:
    nomor: int
    data: dict
    galat: list[str] = field(default_factory=list)
    status: str = ""


@dataclass
class HasilImpor:
    baris: list[BarisImpor]

    @property
    def ada_galat(self):
        return any(b.galat for b in self.baris)

    @property
    def jumlah_galat(self):
        return sum(1 for b in self.baris if b.galat)


def tulis_baris(ws, nilai):
    """Tambah baris; teks pengguna yang diawali = tetap teks, bukan rumus Excel (formula injection, NFR-09)."""
    ws.append(list(nilai))
    for sel in ws[ws.max_row]:
        if isinstance(sel.value, str) and sel.value.startswith("="):
            sel.data_type = "s"


def teks(nilai):
    if nilai is None:
        return ""
    if isinstance(nilai, float) and nilai.is_integer():
        return str(int(nilai))
    return str(nilai).strip()


def baca_tabel(berkas, kolom, nama_sheet) -> list[tuple[int, dict]]:
    """Baca berkas .xlsx menjadi daftar (nomor baris Excel, dict kolom → teks).

    `kolom` berupa daftar (kunci, label judul). Sheet `nama_sheet` dipakai bila
    ada, selain itu sheet pertama.
    """
    if not berkas.name.lower().endswith(".xlsx"):
        raise GalatImpor("Berkas harus berformat Excel .xlsx.")
    if berkas.size > UKURAN_MAKS:
        raise GalatImpor("Ukuran berkas maksimal 2 MB.")
    try:
        wb = load_workbook(berkas, read_only=True, data_only=True)
    except (InvalidFileException, BadZipFile, KeyError, OSError, ValueError) as e:
        raise GalatImpor("Berkas bukan Excel .xlsx yang valid.") from e

    try:
        ws = wb[nama_sheet] if nama_sheet in wb.sheetnames else wb.worksheets[0]
        baris_iter = ws.iter_rows(values_only=True)
        header = [teks(h).lower() for h in next(baris_iter, ())]
        posisi = {}
        hilang = []
        for kunci, label in kolom:
            if label.lower() in header:
                posisi[kunci] = header.index(label.lower())
            else:
                hilang.append(label)
        if hilang:
            raise GalatImpor("Kolom tidak ditemukan di baris judul: " + ", ".join(hilang) + ". Gunakan template impor.")

        hasil = []
        for nomor, sel in enumerate(baris_iter, start=2):
            data = {k: teks(sel[i]) if i < len(sel) else "" for k, i in posisi.items()}
            if not any(data.values()):
                continue
            hasil.append((nomor, data))
            if len(hasil) > BARIS_MAKS:
                raise GalatImpor(f"Jumlah baris melebihi batas {BARIS_MAKS}. Pecah menjadi beberapa berkas.")
    finally:
        wb.close()
    if not hasil:
        raise GalatImpor("Tidak ada baris data di bawah baris judul.")
    return hasil


def buat_template(nama_sheet, kolom, petunjuk, kolom_teks=(), lebar=None, baris_tebal=(1,)) -> Workbook:
    """Template impor kosong dengan sheet data dan sheet "Petunjuk"."""
    lebar = lebar or {}
    wb = Workbook()
    ws = wb.active
    ws.title = nama_sheet
    ws.append([label for _, label in kolom])
    for sel in ws[1]:
        sel.font = Font(bold=True)
    for i, (kunci, _) in enumerate(kolom, start=1):
        huruf = ws.cell(row=1, column=i).column_letter
        ws.column_dimensions[huruf].width = lebar.get(kunci, 18)
        if kunci in kolom_teks:
            # Kode seperti "2.10" harus teks agar tidak berubah menjadi angka 2.1.
            for baris in range(2, BARIS_MAKS + 2):
                ws.cell(row=baris, column=i).number_format = "@"
    ws.freeze_panes = "A2"

    sheet_petunjuk = wb.create_sheet("Petunjuk")
    sheet_petunjuk.column_dimensions["A"].width = 28
    sheet_petunjuk.column_dimensions["B"].width = 90
    for baris in petunjuk:
        sheet_petunjuk.append(baris)
    for r in baris_tebal:
        for sel in sheet_petunjuk[r]:
            sel.font = Font(bold=True)
    return wb
