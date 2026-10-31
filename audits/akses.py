"""Hak akses berbasis penugasan (NFR-08).

Setiap view audit memakai `ambil_audit()` atau `@perlu_akses_audit`, sehingga
akses diperiksa di server, bukan hanya dengan menyembunyikan menu.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from .models import Audit, Penugasan

IZIN_LIHAT_SEMUA = "audits.view_audit"  # Master Admin dan Admin (Bab 4)


def penugasan_pengguna(user, audit):
    return audit.penugasan.filter(pengguna=user).first() if user.is_authenticated else None


def akses_riwayat_unit(user, audit):
    """FR-24 (keputusan 31 Okt 2026): siapa pun yang pernah/sedang menjadi auditee suatu unit dapat
    membuka audit unit itu yang sudah Final, hanya-baca (termasuk pimpinan unit yang baru)."""
    from .penilaian import STATUS_SETELAH_FINAL

    return (
        user.is_authenticated
        and audit.status in STATUS_SETELAH_FINAL
        and Penugasan.objects.filter(pengguna=user, peran=Penugasan.Peran.AUDITEE, audit__unit_id=audit.unit_id).exists()
    )


def ambil_audit(user, pk, peran=None, queryset=None):
    """Kembalikan (audit, penugasan). Staf LPM berizin melihat semua audit;
    selain itu pengguna harus ditugaskan di audit tersebut (dengan peran tertentu),
    atau — untuk melihat saja — auditee unit itu pada audit yang sudah Final (FR-24)."""
    audit = get_object_or_404(queryset if queryset is not None else Audit.objects.all(), pk=pk)
    penugasan = penugasan_pengguna(user, audit)
    if user.has_perm(IZIN_LIHAT_SEMUA) and peran is None:
        return audit, penugasan
    if penugasan is None:
        if peran is None and akses_riwayat_unit(user, audit):
            return audit, None
        raise PermissionDenied("Anda tidak ditugaskan di audit ini.")
    if peran is not None:
        diizinkan = {peran} if isinstance(peran, str) else set(peran)
        if "KETUA" in diizinkan and penugasan.ketua:
            return audit, penugasan
        if penugasan.peran not in diizinkan:
            raise PermissionDenied("Peran Anda di audit ini tidak mengizinkan tindakan tersebut.")
    return audit, penugasan


def perlu_akses_audit(peran=None):
    """Decorator view `(request, pk)`; mengisi `request.audit` dan `request.penugasan`."""

    def dekorator(view):
        @login_required
        @wraps(view)
        def bungkus(request, pk, *args, **kwargs):
            request.audit, request.penugasan = ambil_audit(request.user, pk, peran=peran)
            return view(request, pk, *args, **kwargs)

        return bungkus

    return dekorator
