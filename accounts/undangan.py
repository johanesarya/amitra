"""Undangan akun tamu: email berisi tautan untuk menetapkan password (FR-02)."""

from allauth.account.forms import default_token_generator
from allauth.account.utils import user_pk_to_url_str
from django.urls import reverse

from notifications.layanan import antre_email, email_dari_template, url_penuh


def tautan_tetapkan_password(user):
    path = reverse(
        "account_reset_password_from_key",
        kwargs={"uidb36": user_pk_to_url_str(user), "key": default_token_generator.make_token(user)},
    )
    return url_penuh(path)


def kirim_undangan(user):
    if not user.akun_tamu:
        raise ValueError("Undangan hanya untuk akun tamu.")
    teks, html = email_dari_template("undangan_tamu", {"pengguna": user, "tautan": tautan_tetapkan_password(user)})
    return antre_email(
        penerima=user.email, pengguna=user, jenis="UNDANGAN_TAMU", subjek="[AMITRA] Undangan akun tamu",
        isi_teks=teks, isi_html=html,
    )
