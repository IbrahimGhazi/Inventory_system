import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-g_n2+2bznu6e@1wel!i(&-4tp86_7lop5395ww+i4x%9*7^old'
)

DEBUG = os.environ.get('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'widget_tweaks',
    'sync.apps.SyncConfig',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'phonenumber_field',
    'crispy_forms',
    'crispy_bootstrap5',
    'imagekit',
    'django_extensions',
    'django_filters',
    'django_tables2',
    'store.apps.StoreConfig',
    'accounts.apps.AccountsConfig',
    'transactions.apps.TransactionsConfig',
    'invoice.apps.InvoiceConfig',
    'bills.apps.BillsConfig',
    'locations.apps.LocationsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'InventoryMS.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'InventoryMS.wsgi.application'

# ── DATABASE ──────────────────────────────────────────────────────────────────
# Railway/Supabase (DATABASE_URL set) → PostgreSQL, no REST sync needed
# Local offline machine (no DATABASE_URL) → SQLite + REST sync to Supabase
# ─────────────────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')

if DATABASE_URL:
    import dj_database_url
    _supabase_db = dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
    DATABASES = {
        'default':  _supabase_db,
        'supabase': _supabase_db,
    }
    SUPABASE_SYNC_ENABLED = False

else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME':   os.path.join(BASE_DIR, 'db.sqlite3'),
        },
        'supabase': {
            'ENGINE':   'django.db.backends.postgresql',
            'NAME':     'postgres',
            'USER':     os.environ.get('SUPABASE_DB_USER',     'postgres.xezlujdnvxkorvadfdoe'),
            'PASSWORD': os.environ.get('SUPABASE_DB_PASSWORD', 'v8]nP7`=6,N8+e+.£*'),
            'HOST':     os.environ.get('SUPABASE_DB_HOST',     'aws-1-ap-south-1.pooler.supabase.com'),
            'PORT':     '5432',
        },
    }
    SUPABASE_SYNC_ENABLED = True

# ── SUPABASE REST credentials (used only in local/offline mode) ───────────────
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://xezlujdnvxkorvadfdoe.supabase.co')
SUPABASE_KEY = os.environ.get(
    'SUPABASE_KEY',
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhlemx1amRudnhrb3J2YWRmZG9lIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIwOTIwOTQsImV4cCI6MjA4NzY2ODA5NH0.iHigTdnm4N3Ry7RUs0VBp9QkGHKY-IV73IF8h7RN1YQ'
)

# ── AUTH ──────────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL          = 'user-login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_URL         = 'logout'

# ── I18N ──────────────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'UTC'
USE_I18N      = True
USE_TZ        = True

# ── STATIC / MEDIA ────────────────────────────────────────────────────────────
STATIC_URL       = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT      = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_ROOT       = os.path.join(BASE_DIR, 'static/images')
MEDIA_URL        = '/images/'

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD        = 'django.db.models.BigAutoField'
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK      = 'bootstrap5'

_csrf_origins = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS    = [o for o in _csrf_origins.split(',') if o.strip()]
CSRF_COOKIE_SECURE      = False
SESSION_COOKIE_SECURE   = False
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
