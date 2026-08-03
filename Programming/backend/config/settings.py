import os
from pathlib import Path

import dj_database_url
from corsheaders.defaults import default_headers as cors_default_headers
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
# Process environment is authoritative in Kubernetes and CI. Local files are
# development fallbacks only and must never replace Vault/GitLab variables.
load_dotenv(BASE_DIR / ".env.local")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "aims-dev-secret-key")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "apps.users",
    "apps.products",
    "apps.carts",
    "apps.orders",
    "apps.payments",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
        "DIRS": [],
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

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise ImproperlyConfigured("DATABASE_URL is required. Set the Supabase Postgres connection string.")
if DATABASE_URL.startswith(("sqlite:", "sqlite3:")):
    raise ImproperlyConfigured("DATABASE_URL must point to Supabase Postgres, not SQLite.")

DATABASES = {
    "default": dj_database_url.parse(DATABASE_URL, conn_max_age=600)
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Bangkok"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
EMAIL_BACKEND = os.getenv("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@aims.local")

# PayPal settings (read from .env)
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
# Accept "true"/"false" (case-insensitive) or special value "mock"
_paypal_sandbox_raw = os.getenv("PAYPAL_SANDBOX", "true")
PAYPAL_SANDBOX = _paypal_sandbox_raw.lower() == "true" if isinstance(_paypal_sandbox_raw, str) else bool(_paypal_sandbox_raw)
PAYPAL_CURRENCY = os.getenv("PAYPAL_CURRENCY", "USD").upper()
PAYPAL_VND_PER_USD = os.getenv("PAYPAL_VND_PER_USD", "25000")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_PUBLISHABLE_KEY = (
    os.getenv("SUPABASE_PUBLISHABLE_KEY")
    or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
)
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# VietQR settings (read from .env)
VIETQR_ENV = os.getenv("VIETQR_ENV", "dev")
VIETQR_BASE_URL = os.getenv("VIETQR_BASE_URL", "https://dev.vietqr.org")
VIETQR_USERNAME = os.getenv("VIETQR_USERNAME")
VIETQR_PASSWORD = os.getenv("VIETQR_PASSWORD")
VIETQR_BANK_CODE = os.getenv("VIETQR_BANK_CODE")
VIETQR_BANK_ACCOUNT = os.getenv("VIETQR_BANK_ACCOUNT")
VIETQR_USER_BANK_NAME = os.getenv("VIETQR_USER_BANK_NAME")
VIETQR_CALLBACK_USERNAME = os.getenv("VIETQR_CALLBACK_USERNAME")
VIETQR_CALLBACK_PASSWORD = os.getenv("VIETQR_CALLBACK_PASSWORD")
VIETQR_CALLBACK_TOKEN_TTL_SECONDS = int(os.getenv("VIETQR_CALLBACK_TOKEN_TTL_SECONDS", "300"))
VIETQR_REQUEST_TIMEOUT = int(os.getenv("VIETQR_REQUEST_TIMEOUT", "10"))

# Validation for required VietQR config
if not all([
    VIETQR_USERNAME,
    VIETQR_PASSWORD,
    VIETQR_BANK_CODE,
    VIETQR_BANK_ACCOUNT,
    VIETQR_USER_BANK_NAME,
]):
    import warnings

    warnings.warn(
        "Missing required VietQR configuration. VietQR payment gateway will not work. "
        "Please set VIETQR_USERNAME, VIETQR_PASSWORD, VIETQR_BANK_CODE, "
        "VIETQR_BANK_ACCOUNT, VIETQR_USER_BANK_NAME in .env",
        RuntimeWarning,
    )

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

# The default CORS allow-list covers Authorization/Content-Type but NOT our custom
# headers. Without these the browser's preflight blocks every cart request
# ("Failed to fetch"), since the cart is keyed by an anonymous X-Cart-Token.
CORS_ALLOW_HEADERS = (
    *cors_default_headers,
    "x-cart-token",
    "x-manager-id",
)

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    # Resolve our token when present; otherwise the request stays anonymous.
    # No DEFAULT_PERMISSION_CLASSES on purpose: customer/public endpoints remain
    # open (AllowAny); only manager/admin views opt into role permissions.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.UsersTokenAuthentication",
    ],
}

# Email: defaults to the console backend so the demo prints messages to stdout
# (no SMTP needed). Override DJANGO_EMAIL_BACKEND + EMAIL_* in .env for real mail.
EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "false").lower() == "true"
DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL", "AIMS <no-reply@aims.local>")
# Mailbox that receives manager operational notices (manual refunds, etc.).
AIMS_MANAGER_NOTICE_EMAIL = os.getenv("AIMS_MANAGER_NOTICE_EMAIL", "manager@aims.local")
