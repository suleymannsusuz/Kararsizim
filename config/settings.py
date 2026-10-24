"""Django settings for kararsızım. Values come from environment variables (.env locally)."""

import os
import sys
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def env_bool(name, default=False):
    """Tanımsız ya da boş değişken varsayılana düşer (panelden boş bırakılan değer bir şeyi kapatmasın)."""
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    return value.lower() in ("1", "true", "yes")


DEBUG = env_bool("DJANGO_DEBUG")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("DJANGO_SECRET_KEY ortam değişkeni tanımlı olmalı.")
    SECRET_KEY = "dev-only-insecure-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Vercel build/çalışma ortamında VERCEL=1 tanımlıdır. Üretim ve önizleme adresleri sistem
# değişkenlerinden okunur, böylece alan adı elle yazılmadan Host ve CSRF kontrolleri geçer.
# (DJANGO_ALLOWED_HOSTS / DJANGO_CSRF_TRUSTED_ORIGINS ile özel alan adı da eklenebilir.)
ON_VERCEL = env_bool("VERCEL")
if ON_VERCEL:
    for variable in ("VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_URL", "VERCEL_BRANCH_URL"):
        host = os.environ.get(variable, "").strip()
        if host:
            ALLOWED_HOSTS.append(host)
            CSRF_TRUSTED_ORIGINS.append(f"https://{host}")

# Canlı güvenlik ayarları: Vercel'de otomatik açılır, başka bir barındırmada DJANGO_SECURE=True ile.
# Yerelde (DEBUG=False olsa bile http://localhost ile denenebilsin diye) kapalı kalır.
if not DEBUG and env_bool("DJANGO_SECURE", ON_VERCEL):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "accounts",
    "polls",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# DATABASE_URL boşsa yerelde SQLite kullanılır. Testler uzak veritabanına asla bağlanmaz
# (Supabase havuzu test veritabanı oluşturmaya izin vermez, canlı veriye de dokunulmamalı).
RUNNING_TESTS = len(sys.argv) > 1 and sys.argv[1] == "test"
DATABASE_URL = "" if RUNNING_TESTS else os.environ.get("DATABASE_URL", "")
USING_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

# Supabase transaction pooler (6543): bağlantılar havuzda tutulmaz ve sunucu taraflı
# imleçler kapatılır; Supabase SSL gerektirir (yerel Postgres için DATABASE_SSL_REQUIRE=False).
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL or f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=0,
        disable_server_side_cursors=USING_POSTGRES,
        ssl_require=USING_POSTGRES and env_bool("DATABASE_SSL_REQUIRE", True),
    )
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "tr"
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/giris/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
