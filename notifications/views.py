from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Notifikasi


@login_required
def daftar(request):
    halaman = Paginator(request.user.notifikasi.select_related("audit__unit"), 30).get_page(request.GET.get("halaman"))
    return render(request, "notifications/daftar.html", {"halaman": halaman})


@login_required
def buka(request, pk):
    """Tandai dibaca lalu buka tautannya. Hanya notifikasi milik sendiri (NFR-08)."""
    n = get_object_or_404(Notifikasi, pk=pk, penerima=request.user)
    if n.dibaca_pada is None:
        n.dibaca_pada = timezone.now()
        n.save(update_fields=["dibaca_pada"])
    if n.tautan and url_has_allowed_host_and_scheme(n.tautan, allowed_hosts={request.get_host()}):
        return redirect(n.tautan)
    return redirect("notifications:daftar")


@require_POST
@login_required
def tandai_semua(request):
    request.user.notifikasi.filter(dibaca_pada__isnull=True).update(dibaca_pada=timezone.now())
    return redirect("notifications:daftar")
