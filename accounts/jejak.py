"""Pencatatan audit log (NFR-10). Ringan: satu INSERT per peristiwa; rantai hash dibuat berkala.

Aktor, IP, dan peramban diambil dari request yang sedang berjalan (JejakMiddleware), sehingga
layanan cukup memanggil `catat(...)` tanpa meneruskan request.
"""

import hashlib
import json
from contextvars import ContextVar

from django.conf import settings
from django.db import IntegrityError, transaction

_request = ContextVar("siami_request", default=None)


class JejakMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request.set(request)
        try:
            return self.get_response(request)
        finally:
            _request.reset(token)


def _ip(request):
    if request is None:
        return None
    if getattr(settings, "PERCAYA_PROXY", False):
        diteruskan = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if diteruskan:
            return diteruskan.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def _aman_json(data):
    # Nilai seperti Decimal/tanggal disimpan sebagai teks agar hash tetap sama saat diperiksa ulang.
    return json.loads(json.dumps(data or {}, default=str, ensure_ascii=False))


def catat(aksi, *, objek=None, audit_id=None, data=None, alasan="", aktor=None, aktor_email=None, request=None):
    from .models import LogAudit

    request = request or _request.get()
    if aktor is None and request is not None:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            aktor = user
    return LogAudit.objects.create(
        aksi=aksi,
        aktor=aktor,
        aktor_email=(aktor_email if aktor_email is not None else (aktor.email if aktor else ""))[:254],
        objek_jenis=objek._meta.label if objek is not None else "",
        objek_id=str(objek.pk) if objek is not None and objek.pk is not None else "",
        objek_nama=str(objek)[:250] if objek is not None else "",
        audit_id=audit_id,
        data=_aman_json(data),
        alasan=alasan or "",
        ip=_ip(request),
        peramban=(request.META.get("HTTP_USER_AGENT", "") if request is not None else "")[:250],
    )


# --- Segel: rantai hash berkala ---------------------------------------------------------

def _rantai(sebelumnya, log):
    return hashlib.sha256(f"{sebelumnya}|{log.pk}|{log.hash_isi}".encode()).hexdigest()


def segel(batas=5000):
    """Dijadwalkan tiap 10 menit (pasang_jadwal): sambungkan log baru ke rantai hash."""
    from .models import LogAudit, SegelLog

    terakhir = SegelLog.objects.select_related("log").order_by("-log_id").first()
    sebelumnya = terakhir.hash_rantai if terakhir else ""
    dari = terakhir.log_id if terakhir else 0
    jumlah = 0
    for log in LogAudit.objects.filter(pk__gt=dari).order_by("pk")[:batas]:
        sebelumnya = _rantai(sebelumnya, log)
        try:
            with transaction.atomic():
                SegelLog.objects.create(log=log, hash_rantai=sebelumnya)
        except IntegrityError:
            break  # proses segel lain berjalan bersamaan; lanjut di putaran berikutnya
        jumlah += 1
    return jumlah


def periksa():
    """Daftar masalah: isi baris berubah, atau rantai segel putus (baris disegel diubah/dihapus)."""
    from .models import LogAudit, SegelLog

    masalah = []
    for log in LogAudit.objects.order_by("pk").iterator():
        if log.hitung_hash() != log.hash_isi:
            masalah.append(f"Log #{log.pk}: isi tidak cocok dengan hash (diubah).")
    sebelumnya = ""
    for s in SegelLog.objects.select_related("log").order_by("log_id").iterator():
        sebelumnya = _rantai(sebelumnya, s.log)
        if sebelumnya != s.hash_rantai:
            masalah.append(f"Segel log #{s.log_id}: rantai putus (ada log disegel yang diubah atau dihapus).")
            sebelumnya = s.hash_rantai  # lanjutkan dari segel ini agar masalah berikutnya tetap terdeteksi
    return masalah
