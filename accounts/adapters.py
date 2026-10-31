from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.shortcuts import render

from .peran import Peran


def email_diizinkan(email):
    """FR-01: domain email harus persis salah satu DOMAIN_EMAIL_KAMPUS."""
    if not email or email.count("@") != 1:
        return False
    domain = email.rsplit("@", 1)[1].strip().lower()
    return domain in {d.lower() for d in settings.DOMAIN_EMAIL_KAMPUS}


class AdapterAkunSosial(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # Dipanggil setelah lookup, jadi berlaku juga untuk akun yang sudah ada.
        email = (sociallogin.user.email or "").strip()
        terverifikasi = any(
            a.verified and a.email.lower() == email.lower() for a in sociallogin.email_addresses
        )
        if not (terverifikasi and email_diizinkan(email)):
            raise ImmediateHttpResponse(
                render(
                    request,
                    "accounts/ditolak.html",
                    {"email": email, "domain": settings.DOMAIN_EMAIL_KAMPUS},
                    status=403,
                )
            )

    def is_open_for_signup(self, request, sociallogin):
        return True  # domain sudah diperiksa di pre_social_login

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.nama = data.get("name") or " ".join(filter(None, [data.get("first_name"), data.get("last_name")]))
        user.peran = Peran.MENUNGGU  # FR-03
        return user


def boleh_login_password(user):
    """FR-02: hanya akun tamu (dan akun pengembang) yang masuk dengan password; akun kampus lewat Google."""
    return user.akun_tamu or user.is_superuser


class AdapterAkun(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False  # akun dibuat Master Admin; pengguna kampus masuk lewat Google

    def authenticate(self, request, **credentials):
        user = super().authenticate(request, **credentials)
        if user is not None and not boleh_login_password(user):
            from .jejak import catat
            from .models import LogAudit

            catat(LogAudit.Aksi.LOGIN_GAGAL, aktor_email=user.email, request=request,
                  data={"email": user.email, "sebab": "akun kampus mencoba login dengan password"})
            self.authentication_failed(request, **credentials)
            return None
        return user

    def send_password_reset_mail(self, user, email, context):
        # Akun kampus tidak boleh punya jalur password (pembatasan domain FR-01 tidak bisa diakali).
        if boleh_login_password(user):
            super().send_password_reset_mail(user, email, context)

    def send_mail(self, template_prefix, email, context):
        """Semua email allauth dirender di sini lalu dikirim lewat antrean (NFR-04)."""
        from notifications.layanan import antre_email

        request = getattr(self, "request", None) or context.get("request")
        ctx = {"request": request, "email": email, "current_site": get_current_site(request)}
        ctx.update(context)
        msg = self.render_mail(template_prefix, email, ctx)
        html = next((isi for isi, jenis in getattr(msg, "alternatives", []) if jenis == "text/html"), "")
        antre_email(penerima=email, subjek=msg.subject, isi_teks=msg.body, isi_html=html, jenis="AKUN")
