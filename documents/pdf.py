"""Render HTML ke PDF dengan WeasyPrint. Hanya dipanggil dari tugas antrean (NFR-03)."""

import base64
import mimetypes


class PDFTidakTersedia(RuntimeError):
    pass


def render_pdf(html):
    try:
        from weasyprint import HTML
    except OSError as e:  # pustaka GTK/Pango tidak ditemukan
        raise PDFTidakTersedia(
            "WeasyPrint belum dapat dimuat karena pustaka Pango/GTK tidak ditemukan. "
            "Di Windows: pasang MSYS2, jalankan `pacman -S mingw-w64-x86_64-pango`, lalu isi "
            "WEASYPRINT_DLL_DIRECTORIES=C:\\msys64\\mingw64\\bin di .env."
        ) from e
    return HTML(string=html).write_pdf()


def data_uri(berkas):
    """Berkas dari storage sebagai data URI, agar PDF tidak bergantung pada URL/storage."""
    if not berkas:
        return ""
    jenis = mimetypes.guess_type(berkas.name)[0] or "application/octet-stream"
    with berkas.open("rb") as f:
        return f"data:{jenis};base64,{base64.b64encode(f.read()).decode()}"
