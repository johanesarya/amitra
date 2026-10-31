"""Akun, peran global, dan login Google (FR-01, FR-03, FR-04, Bab 4, NFR-08)."""

import pytest
from allauth.account.models import EmailAddress
from allauth.core import context
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from allauth.socialaccount.helpers import complete_social_login
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.urls import reverse

from accounts.adapters import AdapterAkunSosial, email_diizinkan
from accounts.peran import IZIN_GRUP, Peran

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture(autouse=True)
def domain_kampus(settings):
    settings.DOMAIN_EMAIL_KAMPUS = ["unika.ac.id"]


@pytest.fixture
def google_siap(settings):
    settings.GOOGLE_CLIENT_ID = "id-uji"
    settings.SOCIALACCOUNT_PROVIDERS = {
        "google": {"APPS": [{"client_id": "id-uji", "secret": "rahasia", "key": ""}]}
    }


# --- Domain email (FR-01) -----------------------------------------------------------

@pytest.mark.parametrize(
    "email, hasil",
    [
        ("dosen@unika.ac.id", True),
        ("Dosen@UNIKA.AC.ID", True),
        ("orang@gmail.com", False),
        ("x@unika.ac.id.evil.com", False),
        ("x@sub.unika.ac.id", False),
        ("x@evilunika.ac.id", False),
        ("a@b@unika.ac.id", False),
        ("", False),
        (None, False),
    ],
)
def test_email_diizinkan(email, hasil):
    assert email_diizinkan(email) is hasil


def test_beberapa_domain(settings):
    settings.DOMAIN_EMAIL_KAMPUS = ["unika.ac.id", "student.unika.ac.id"]
    assert email_diizinkan("mhs@student.unika.ac.id")


def test_daftar_domain_kosong_menolak_semua(settings):
    settings.DOMAIN_EMAIL_KAMPUS = []
    assert not email_diizinkan("dosen@unika.ac.id")


# --- Alur login Google -------------------------------------------------------------

def _request(rf):
    request = rf.get("/akun/google/login/callback/")
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = AnonymousUser()
    return request


def _sociallogin(email, terverifikasi=True, uid="g-1", request=None):
    provider = get_social_adapter().get_provider(request, "google") if request is not None else None
    return SocialLogin(
        provider=provider,
        user=User(email=email),
        account=SocialAccount(provider="google", uid=uid, extra_data={"email": email}),
        email_addresses=[EmailAddress(email=email, verified=terverifikasi, primary=True)],
    )


def _login(rf, email, **kwargs):
    request = _request(rf)
    with context.request_context(request):  # biasanya dipasang AccountMiddleware
        return complete_social_login(request, _sociallogin(email, request=request, **kwargs))


def test_login_google_pengguna_baru_menunggu_peran(rf, google_siap):
    resp = _login(rf, "baru@unika.ac.id")
    assert resp.status_code == 302
    user = User.objects.get(email="baru@unika.ac.id")
    assert user.peran == Peran.MENUNGGU  # FR-03
    assert not user.is_staff
    assert SocialAccount.objects.filter(user=user, provider="google").exists()


def test_login_google_domain_lain_ditolak(rf, google_siap):
    resp = _login(rf, "orang@gmail.com")
    assert resp.status_code == 403
    assert "tidak diizinkan" in resp.content.decode()
    assert not User.objects.exists()


def test_login_google_email_belum_terverifikasi_ditolak(rf, google_siap):
    resp = _login(rf, "dosen@unika.ac.id", terverifikasi=False)
    assert resp.status_code == 403
    assert not User.objects.exists()


def test_akun_buatan_admin_tersambung_lewat_email(rf, google_siap):
    lama = User.objects.create_user("dosen@unika.ac.id", nama="Dosen Lama", peran=Peran.PENGGUNA)
    resp = _login(rf, "dosen@unika.ac.id")
    assert resp.status_code == 302
    assert User.objects.count() == 1
    assert SocialAccount.objects.get(provider="google").user == lama


def test_akun_tersambung_tetap_ditolak_bila_domain_dikeluarkan(rf, google_siap, settings):
    _login(rf, "dosen@unika.ac.id")
    settings.DOMAIN_EMAIL_KAMPUS = ["kampus-baru.ac.id"]
    resp = _login(rf, "dosen@unika.ac.id")
    assert resp.status_code == 403


def test_populate_user_mengisi_nama_dan_peran(rf):
    sl = _sociallogin("a@unika.ac.id")
    user = AdapterAkunSosial().populate_user(_request(rf), sl, {"email": "a@unika.ac.id", "name": "Ani Wijaya"})
    assert user.nama == "Ani Wijaya" and user.peran == Peran.MENUNGGU


# --- Halaman login ----------------------------------------------------------------

def test_halaman_login_tanpa_kredensial_google(client):
    isi = client.get(reverse("account_login")).content.decode()
    assert "belum dikonfigurasi" in isi
    assert "Masuk dengan Google" not in isi


def test_halaman_login_dengan_google(client, google_siap):
    isi = client.get(reverse("account_login")).content.decode()
    assert "Masuk dengan Google" in isi


def test_pendaftaran_mandiri_ditutup(client):
    # Akun dibuat Master Admin; pengguna kampus masuk lewat Google.
    resp = client.post("/akun/signup/", {"email": "x@unika.ac.id", "password1": "Rahasia!234", "password2": "Rahasia!234"})
    assert resp.status_code == 200 and "signup_closed" in resp.templates[0].name
    assert not User.objects.exists()


def test_beranda_wajib_login(client):
    resp = client.get(reverse("beranda"))
    assert resp.status_code == 302 and reverse("account_login") in resp.url


# --- Menunggu peran (FR-03) --------------------------------------------------------

def test_pengguna_menunggu_dialihkan_ke_halaman_status(client):
    client.force_login(User.objects.create_user("baru@unika.ac.id"))
    resp = client.get(reverse("beranda"))
    assert resp.status_code == 302 and resp.url == reverse("accounts:menunggu")
    assert client.get(reverse("accounts:menunggu")).status_code == 200
    assert client.get(reverse("account_logout")).status_code == 200


def test_pengguna_berperan_membuka_beranda(client):
    client.force_login(User.objects.create_user("dosen@unika.ac.id", peran=Peran.PENGGUNA))
    resp = client.get(reverse("beranda"))
    assert resp.status_code == 200 and "Tugas Saya" in resp.content.decode()
    assert client.get(reverse("accounts:menunggu")).status_code == 302


def test_superuser_tidak_dianggap_menunggu():
    assert not User.objects.create_superuser("dev@unika.ac.id", "x").menunggu_peran


# --- Model dan sinkronisasi peran ---------------------------------------------------

def test_create_user_email_huruf_kecil_tanpa_password():
    user = User.objects.create_user("Dosen@Unika.AC.ID")
    assert user.email == "dosen@unika.ac.id"
    assert not user.has_usable_password()


def test_npp_kosong_boleh_lebih_dari_satu():
    User.objects.create_user("a@unika.ac.id", npp="")
    User.objects.create_user("b@unika.ac.id", npp="")
    assert User.objects.filter(npp__isnull=True).count() == 2


@pytest.mark.parametrize(
    "peran, staf, aktif, grup",
    [
        (Peran.MENUNGGU, False, True, []),
        (Peran.PENGGUNA, False, True, []),
        (Peran.VIEWER, False, True, ["Viewer"]),
        (Peran.ADMIN, True, True, ["Admin"]),
        (Peran.MASTER_ADMIN, True, True, ["Master Admin"]),
        (Peran.NONAKTIF, False, False, []),
    ],
)
def test_peran_disinkronkan_ke_status_dan_grup(peran, staf, aktif, grup):
    user = User.objects.create_user("x@unika.ac.id", peran=Peran.MASTER_ADMIN)
    user.peran = peran
    user.save()
    user.refresh_from_db()
    assert (user.is_staff, user.is_active) == (staf, aktif)
    assert list(user.groups.values_list("name", flat=True)) == grup


def test_grup_lain_tidak_dihapus_saat_sinkron():
    lain = Group.objects.create(name="Grup lain")
    user = User.objects.create_user("x@unika.ac.id", peran=Peran.ADMIN)
    user.groups.add(lain)
    user.peran = Peran.PENGGUNA
    user.save()
    assert list(user.groups.values_list("name", flat=True)) == ["Grup lain"]


def test_izin_grup_sesuai_pemetaan():
    for nama, daftar in IZIN_GRUP.items():
        izin = {f"{p.content_type.app_label}.{p.codename}" for p in Group.objects.get(name=nama).permissions.all()}
        assert izin == set(daftar)


# --- Hak akses Admin per peran (Bab 4, NFR-08) --------------------------------------

def _masuk(client, peran):
    user = User.objects.create_user(f"{peran.lower()}@unika.ac.id", peran=peran)
    client.force_login(user)
    return user


def test_admin_lpm_hanya_melihat_unit_dan_periode(client):
    _masuk(client, Peran.ADMIN)
    assert client.get(reverse("admin:masterdata_unit_changelist")).status_code == 200
    assert client.get(reverse("admin:masterdata_unit_add")).status_code == 403
    assert client.get(reverse("admin:masterdata_periode_add")).status_code == 403


def test_admin_lpm_mengelola_standar_dan_impor(client):
    _masuk(client, Peran.ADMIN)
    assert client.get(reverse("admin:masterdata_standar_add")).status_code == 200
    assert client.get(reverse("admin:masterdata_standar_impor")).status_code == 200


def test_admin_lpm_tidak_bisa_mengubah_pengguna(client):
    _masuk(client, Peran.ADMIN)
    target = User.objects.create_user("t@unika.ac.id")
    url = reverse("admin:accounts_user_change", args=[target.pk])
    assert client.get(url).status_code == 200  # lihat saja
    assert client.post(url, {"email": "t@unika.ac.id", "peran": Peran.MASTER_ADMIN}).status_code == 403
    target.refresh_from_db()
    assert target.peran == Peran.MENUNGGU


@pytest.mark.parametrize("peran", [Peran.PENGGUNA, Peran.VIEWER])
def test_pengguna_dan_viewer_tidak_bisa_membuka_admin(client, peran):
    _masuk(client, peran)
    resp = client.get(reverse("admin:masterdata_unit_changelist"))
    assert resp.status_code == 302 and reverse("admin:login") in resp.url


def test_master_admin_menetapkan_peran_lewat_aksi(client):
    saya = _masuk(client, Peran.MASTER_ADMIN)
    a = User.objects.create_user("a@unika.ac.id")
    b = User.objects.create_user("b@unika.ac.id")
    resp = client.post(
        reverse("admin:accounts_user_changelist"),
        {"action": "tetapkan_pengguna", "_selected_action": [a.pk, b.pk, saya.pk]},
    )
    assert resp.status_code == 302
    assert set(User.objects.filter(peran=Peran.PENGGUNA).values_list("email", flat=True)) == {
        "a@unika.ac.id", "b@unika.ac.id",
    }
    saya.refresh_from_db()
    assert saya.peran == Peran.MASTER_ADMIN  # peran sendiri tidak ikut berubah


def test_master_admin_menambah_pengguna_tanpa_password(client):
    _masuk(client, Peran.MASTER_ADMIN)
    resp = client.post(
        reverse("admin:accounts_user_add"),
        {"email": "Baru@Unika.ac.id", "nama": "Baru", "npp": "", "telepon": "", "homebase": "", "peran": Peran.PENGGUNA},
    )
    assert resp.status_code == 302, resp.content.decode()[:2000]
    user = User.objects.get(email="baru@unika.ac.id")
    assert user.peran == Peran.PENGGUNA and not user.has_usable_password()


def test_aksi_tetapkan_peran_tidak_tersedia_untuk_admin_lpm(client):
    _masuk(client, Peran.ADMIN)
    isi = client.get(reverse("admin:accounts_user_changelist")).content.decode()
    assert "tetapkan_pengguna" not in isi
