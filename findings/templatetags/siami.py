from django import template

register = template.Library()

# Warna lencana skala 1–4 (BRD 6.1); sama untuk kategori auditee dan auditor.
KELAS_KATEGORI = {
    "KTS": "bg-red-50 text-red-700 ring-red-600/20",
    "OB": "bg-amber-50 text-amber-800 ring-amber-600/25",
    "SESUAI": "bg-green-50 text-green-700 ring-green-600/20",
    "PELAMPAUAN": "bg-blue-50 text-blue-700 ring-blue-600/20",
}

# Warna lencana 10 status audit (BRD 6.6).
KELAS_STATUS = {
    "BELUM_MULAI": "bg-slate-100 text-slate-700 ring-slate-500/20",
    "PENGISIAN_SER": "bg-sky-50 text-sky-800 ring-sky-600/20",
    "PENILAIAN_AUDITOR": "bg-indigo-50 text-indigo-700 ring-indigo-600/20",
    "REKONSILIASI": "bg-primer-50 text-primer-700 ring-primer-600/20",
    "PERLU_AUDIT_LAPANGAN": "bg-amber-50 text-amber-800 ring-amber-600/25",
    "PERUMUSAN_TEMUAN": "bg-cyan-50 text-cyan-800 ring-cyan-600/20",
    "MENUNGGU_PERSETUJUAN": "bg-orange-50 text-orange-800 ring-orange-600/20",
    "FINAL": "bg-green-50 text-green-700 ring-green-600/20",
    "TINDAK_LANJUT_PTK": "bg-teal-50 text-teal-800 ring-teal-600/20",
    "DITUTUP": "bg-slate-200 text-slate-700 ring-slate-500/20",
}

NETRAL = "bg-slate-50 text-slate-600 ring-slate-500/20"


@register.filter
def ambil(kamus, kunci):
    """{{ kamus|ambil:kunci }} — ambil nilai dict dengan kunci variabel."""
    try:
        return kamus.get(kunci)
    except AttributeError:
        return None


@register.filter
def kelas_kategori(nilai):
    """Kelas warna lencana untuk kategori KTS/OB/SESUAI/PELAMPAUAN."""
    return KELAS_KATEGORI.get(nilai or "", NETRAL)


@register.filter
def kelas_status(nilai):
    """Kelas warna lencana untuk status audit."""
    return KELAS_STATUS.get(nilai or "", NETRAL)


@register.filter
def inisial(user):
    """Satu sampai dua huruf awal nama untuk avatar."""
    nama = (user.get_full_name() or user.email or "?").split()
    return "".join(k[0] for k in nama[:2]).upper()


@register.inclusion_tag("_stepper.html")
def stepper(audit):
    """Stepper enam langkah dan langkah berikutnya (NFR-20)."""
    from audits.status import LANGKAH_BERIKUTNYA
    from audits.status import stepper as langkah

    return {"audit": audit, "langkah": langkah(audit), "berikutnya": LANGKAH_BERIKUTNYA[audit.status]}
