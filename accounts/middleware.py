from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class PeranMiddleware:
    """FR-03: pengguna "Menunggu Peran" hanya boleh membuka halaman status dan logout."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.menunggu_peran and not self._bebas(request.path):
            return redirect("accounts:menunggu")
        return self.get_response(request)

    @staticmethod
    def _bebas(path):
        bebas = [reverse("accounts:menunggu"), reverse("account_logout"), settings.STATIC_URL, settings.MEDIA_URL]
        return any(path.startswith(p if p.startswith("/") else f"/{p}") for p in bebas)
