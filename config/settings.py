"""
Pengaturan Django untuk AMITRA.

Semua nilai yang berbeda antar-lingkungan (development, staging, produksi)
dibaca dari variabel lingkungan atau file `.env` di akar proyek (NFR-15).
"""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path):
    """Muat KEY=VALUE dari file .env tanpa menimpa variabel yang sudah ada."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


_load_env_file(BASE_DIR / ".env")

SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = env_bool("DEBUG")
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "django_q",
    # App AMITRA. `scoring` sengaja tidak terdaftar: isinya fungsi murni tanpa model.
    "accounts",
    "masterdata",
    "audits",
    "findings",
    "documents",
    "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "accounts.jejak.JejakMiddleware",
    "accounts.middleware.PeranMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.akun",
                "notifications.context_processors.notifikasi",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database: SQLite di development, PostgreSQL di staging/produksi.
DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}
# Path SQLite relatif (mis. sqlite:///db.sqlite3) dihitung dari akar proyek, bukan folder kerja.
if DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    _sqlite_name = DATABASES["default"]["NAME"]
    if _sqlite_name and _sqlite_name != ":memory:" and not Path(_sqlite_name).is_absolute():
        DATABASES["default"]["NAME"] = str(BASE_DIR / _sqlite_name)


AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # login Admin Django (akun pengembang)
    "allauth.account.auth_backends.AuthenticationBackend",
]
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "beranda"
ACCOUNT_LOGOUT_REDIRECT_URL = "account_login"


# Login Google dibatasi domain email kampus (FR-01).
# Login email + password untuk tamu (FR-02) ditunda sampai antrean email tersedia.
DOMAIN_EMAIL_KAMPUS = env_list("DOMAIN_EMAIL_KAMPUS")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

ACCOUNT_LOGIN_METHODS = {"email"}
# password1 wajib ada agar form login menampilkan kolom password (login tamu, FR-02);
# pendaftaran mandiri tetap ditutup di AdapterAkun.is_open_for_signup.
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = "none"  # email sudah diverifikasi Google dan dicek adapter
# Login password hanya untuk akun tamu (FR-02); dibatasi di accounts.adapters.AdapterAkun.
SOCIALACCOUNT_ONLY = False
ACCOUNT_ADAPTER = "accounts.adapters.AdapterAkun"
SOCIALACCOUNT_ADAPTER = "accounts.adapters.AdapterAkunSosial"
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True  # akun yang dibuat Admin tersambung lewat email
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_STORE_TOKENS = False
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online", "prompt": "select_account"},
        "APPS": (
            [{"client_id": GOOGLE_CLIENT_ID, "secret": GOOGLE_CLIENT_SECRET, "key": ""}]
            if GOOGLE_CLIENT_ID
            else []
        ),
    }
}

# Antrean Django-Q2: PDF, Excel, dan email tidak pernah dibuat di request web (NFR-03, NFR-04).
# Development memakai broker ORM; produksi mengisi REDIS_URL.
Q_CLUSTER = {
    "name": "siami",
    "workers": int(os.environ.get("Q_WORKERS") or 2),
    "timeout": 120,
    "retry": 180,
    "max_attempts": 3,
    "catch_up": False,
}
if os.environ.get("REDIS_URL"):
    Q_CLUSTER["redis"] = os.environ["REDIS_URL"]
else:
    Q_CLUSTER["orm"] = "default"

# Email: development ke console; produksi SMTP Google Workspace. Dikirim lewat antrean (notifications).
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND") or "django.core.mail.backends.console.EmailBackend"  # kosong = console
EMAIL_HOST = os.environ.get("EMAIL_HOST") or "smtp.gmail.com"
EMAIL_PORT = int(os.environ.get("EMAIL_PORT") or 587)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "AMITRA LPM <no-reply@localhost>")
# Audit log: percayai X-Forwarded-For hanya bila aplikasi berada di belakang Nginx sendiri.
PERCAYA_PROXY = env_bool("PERCAYA_PROXY", False)

# Alamat dasar untuk tautan di email.
SITUS_URL = os.environ.get("SITUS_URL", "http://localhost:8000")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Sesi: HttpOnly, SameSite, timeout idle 60 menit (NFR-07).
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# Produksi di belakang reverse proxy (Nginx/IIS/Caddy) yang menangani HTTPS. Tanpa header ini
# Django mengira koneksi HTTP, sehingga callback Google OAuth memakai http:// dan ditolak Google.
if PERCAYA_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    # Isi 31536000 setelah HTTPS stabil; HSTS sulit dibatalkan di browser pengguna.
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS") or 0)

# Galat ke stderr agar tercatat oleh systemd (Linux) atau NSSM (Windows).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL") or "WARNING"},
}


# Antarmuka berbahasa Indonesia (NFR-19).
LANGUAGE_CODE = "id"
TIME_ZONE = "Asia/Jakarta"
USE_I18N = True
USE_TZ = True


STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
# Produksi: arahkan ke disk data yang ikut di-backup. Tidak dilayani langsung oleh web server (NFR-08).
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT") or BASE_DIR / "media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
