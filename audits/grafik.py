"""Grafik SVG ringan yang dibuat di server (FR-49, FR-50).

Tanpa JavaScript dan tanpa pustaka tambahan, sehingga tidak membebani halaman,
dan SVG yang sama dapat dipakai di PDF rekap (WeasyPrint).
"""

from html import escape

from django.utils.safestring import mark_safe

WARNA = {"KTS": "#b91c1c", "OB": "#d97706", "SESUAI": "#15803d", "PELAMPAUAN": "#1d4ed8"}
WARNA_GARIS = "#1d4ed8"


def _warna_skor(nilai, skor_sesuai):
    if nilai >= skor_sesuai:
        return WARNA["SESUAI"]
    if nilai >= skor_sesuai - 1:
        return WARNA["OB"]
    return WARNA["KTS"]


def batang_per_butir(baris, skor_maks, skor_sesuai, judul="Rata-rata skor kategori final per butir"):
    """Sumbu X butir, sumbu Y rata-rata skor (0 s.d. skor maksimal); garis acuan pada skor Sesuai."""
    if not baris:
        return ""
    kiri, atas, bawah, lebar_batang, jarak = 36, 16, 64, 16, 8
    tinggi_area = 180
    lebar = kiri + len(baris) * (lebar_batang + jarak) + 16
    tinggi = atas + tinggi_area + bawah
    y = lambda v: atas + tinggi_area - float(v) / skor_maks * tinggi_area  # noqa: E731

    bagian = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lebar} {tinggi}" width="{lebar}" height="{tinggi}" '
        f'role="img" aria-label="{escape(judul)}" font-family="Arial, sans-serif" font-size="10">',
        f"<title>{escape(judul)}</title>",
    ]
    for s in range(0, skor_maks + 1):
        bagian.append(f'<line x1="{kiri}" x2="{lebar - 8}" y1="{y(s):.1f}" y2="{y(s):.1f}" stroke="#e2e8f0"/>')
        bagian.append(f'<text x="{kiri - 6}" y="{y(s) + 3:.1f}" text-anchor="end" fill="#475569">{s}</text>')
    bagian.append(
        f'<line x1="{kiri}" x2="{lebar - 8}" y1="{y(skor_sesuai):.1f}" y2="{y(skor_sesuai):.1f}" '
        f'stroke="#15803d" stroke-dasharray="4 3"/>'
    )
    for i, r in enumerate(baris):
        x = kiri + jarak / 2 + i * (lebar_batang + jarak)
        nilai = float(r["rata"])
        warna = _warna_skor(nilai, skor_sesuai)
        kode = escape(r["butir"].kode)
        bagian.append(
            f'<rect x="{x:.1f}" y="{y(nilai):.1f}" width="{lebar_batang}" height="{y(0) - y(nilai):.1f}" fill="{warna}">'
            f"<title>{kode}: {r['rata']} (n = {r['n']})</title></rect>"
        )
        tx, ty = x + lebar_batang / 2, atas + tinggi_area + 8
        bagian.append(
            f'<text x="{tx:.1f}" y="{ty:.1f}" transform="rotate(-60 {tx:.1f} {ty:.1f})" text-anchor="end" fill="#334155">{kode}</text>'
        )
    bagian.append("</svg>")
    return mark_safe("".join(bagian))


def tren(baris, judul="Tren nilai efektif dan temuan"):
    """Garis NE (0–100, dengan garis KKM) dan batang bertumpuk jumlah KTS/OB/Kelebihan per periode."""
    if not baris:
        return ""
    kiri, atas, tinggi_ne, celah, tinggi_temuan, bawah = 40, 16, 150, 30, 90, 40
    lebar_kolom = 90
    lebar = kiri + len(baris) * lebar_kolom + 16
    tinggi = atas + tinggi_ne + celah + tinggi_temuan + bawah
    y_ne = lambda v: atas + tinggi_ne - float(v) / 100 * tinggi_ne  # noqa: E731
    maks_temuan = max(1, max(r["kts"] + r["ob"] + r["kelebihan"] for r in baris))
    dasar_temuan = atas + tinggi_ne + celah + tinggi_temuan
    skala_temuan = tinggi_temuan / maks_temuan
    cx = lambda i: kiri + lebar_kolom * i + lebar_kolom / 2  # noqa: E731

    bagian = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lebar} {tinggi}" width="{lebar}" height="{tinggi}" '
        f'role="img" aria-label="{escape(judul)}" font-family="Arial, sans-serif" font-size="10">',
        f"<title>{escape(judul)}</title>",
    ]
    for v in (0, 25, 50, 75, 100):
        bagian.append(f'<line x1="{kiri}" x2="{lebar - 8}" y1="{y_ne(v):.1f}" y2="{y_ne(v):.1f}" stroke="#e2e8f0"/>')
        bagian.append(f'<text x="{kiri - 6}" y="{y_ne(v) + 3:.1f}" text-anchor="end" fill="#475569">{v}</text>')
    kkm = float(baris[-1]["kkm"])
    bagian.append(
        f'<line x1="{kiri}" x2="{lebar - 8}" y1="{y_ne(kkm):.1f}" y2="{y_ne(kkm):.1f}" stroke="#b91c1c" stroke-dasharray="4 3"/>'
        f'<text x="{lebar - 8}" y="{y_ne(kkm) - 3:.1f}" text-anchor="end" fill="#b91c1c">KKM {kkm:g}</text>'
    )
    titik = " ".join(f"{cx(i):.1f},{y_ne(r['ne']):.1f}" for i, r in enumerate(baris))
    bagian.append(f'<polyline points="{titik}" fill="none" stroke="{WARNA_GARIS}" stroke-width="2"/>')
    for i, r in enumerate(baris):
        bagian.append(
            f'<circle cx="{cx(i):.1f}" cy="{y_ne(r["ne"]):.1f}" r="3.5" fill="{WARNA_GARIS}"><title>NE {r["ne"]}</title></circle>'
            f'<text x="{cx(i):.1f}" y="{y_ne(r["ne"]) - 7:.1f}" text-anchor="middle" fill="#0f172a">{r["ne"]}</text>'
        )
        y0 = dasar_temuan
        for kunci, warna in (("kts", WARNA["KTS"]), ("ob", WARNA["OB"]), ("kelebihan", WARNA["PELAMPAUAN"])):
            h = r[kunci] * skala_temuan
            if h:
                bagian.append(
                    f'<rect x="{cx(i) - 14:.1f}" y="{y0 - h:.1f}" width="28" height="{h:.1f}" fill="{warna}">'
                    f"<title>{kunci.upper()}: {r[kunci]}</title></rect>"
                )
                y0 -= h
        bagian.append(
            f'<text x="{cx(i):.1f}" y="{dasar_temuan + 14:.1f}" text-anchor="middle" fill="#334155">{escape(r["periode"].tahun_akademik)}</text>'
        )
    bagian.append(
        f'<text x="{kiri}" y="{atas + tinggi_ne + celah - 8:.1f}" fill="#475569">Jumlah temuan: '
        f'<tspan fill="{WARNA["KTS"]}">■ KTS</tspan> <tspan fill="{WARNA["OB"]}">■ OB</tspan> '
        f'<tspan fill="{WARNA["PELAMPAUAN"]}">■ Kelebihan</tspan></text>'
    )
    bagian.append("</svg>")
    return mark_safe("".join(bagian))
