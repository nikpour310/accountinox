import os
from pathlib import Path
import environ
from django.core.exceptions import ImproperlyConfigured
import logging

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
# read .env if present
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

DEBUG = env('DEBUG')

SECRET_KEY = env('DJANGO_SECRET_KEY', default='change-me')
if not DEBUG and SECRET_KEY == 'change-me':
    raise ImproperlyConfigured(
        'DJANGO_SECRET_KEY must be set in production (do not use the default).'
    )

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['127.0.0.1', 'localhost', 'testserver'])
SITE_URL = env('SITE_URL', default='').strip().rstrip('/')
# SITE_BASE_URL: canonical base for building absolute URLs used in templates, robots, sitemap
# Read from env `SITE_BASE_URL` if provided, otherwise fall back to SITE_URL (both without trailing slash)
SITE_BASE_URL = env('SITE_BASE_URL', default=SITE_URL).strip().rstrip('/')
SUPPORT_PUSH_ENABLED = env.bool('SUPPORT_PUSH_ENABLED', default=False)
VAPID_PUBLIC_KEY = env('VAPID_PUBLIC_KEY', default='').strip()
VAPID_PRIVATE_KEY = env('VAPID_PRIVATE_KEY', default='').strip()
VAPID_SUBJECT = env('VAPID_SUBJECT', default='').strip()
ADMIN_BRAND_PRIMARY = env('ADMIN_BRAND_PRIMARY', default='').strip()
ADMIN_BRAND_SECONDARY = env('ADMIN_BRAND_SECONDARY', default='').strip()
ADMIN_BRAND_ACCENT = env('ADMIN_BRAND_ACCENT', default='').strip()

INSTALLED_APPS = [
    'apps.core.admin_site.AccountinoxAdminConfig',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.humanize',

    # third party
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'django_ratelimit',

    # local apps
    'apps.core',
    'apps.accounts',
    'apps.shop',
    'apps.blog',
    'apps.support',
]

SITE_ID = 1

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'apps.core.middleware.VaryAcceptMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.site_settings',
                'apps.accounts.context_processors.panel_sidebar',
            ],
        },
    }
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database: MySQL if env provided, else sqlite for local dev
if env('DATABASE_URL', default=None):
    DATABASES = {'default': env.db()}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'fa'
TIME_ZONE = 'Asia/Tehran'
USE_I18N = True
USE_L10N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

# Production: use manifest storage for long-term caching of static files
# This creates hashed filenames (e.g., app.abc123.css) which improves CDN/browser caching
import sys
if not DEBUG and 'runserver' not in sys.argv:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
)

ACCOUNT_EMAIL_VERIFICATION = 'optional'
# Use custom adapter to avoid sending email confirmation on login
ACCOUNT_ADAPTER = 'apps.accounts.adapters.NoConfirmationOnLoginAdapter'
# Note: ACCOUNT_LOGIN_METHODS specifies auth method; ACCOUNT_SIGNUP_FIELDS specifies form fields
# The warning about conflict can be safely ignored (allauth legacy vs new config style)
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email', 'username']
# Use custom signup form to capture phone and store in Profile
# Temporarily disabled to avoid import-time circular import during test collection.
# If you want to enable this in production, ensure allauth is importable
# before importing this module or move the form to a module that doesn't
# trigger circular imports at startup.
# ACCOUNT_SIGNUP_FORM_CLASS = 'apps.accounts.forms_allauth.CustomSignupForm'

# Email backend: console in dev, SMTP in production
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
    EMAIL_HOST = env('EMAIL_HOST', default='localhost')
    EMAIL_PORT = env.int('EMAIL_PORT', default=587)
    EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
    EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
    DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@accountinox.com')

# Allauth social provider settings loaded via env
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': env('GOOGLE_CLIENT_ID', default=''),
            'secret': env('GOOGLE_SECRET', default=''),
            'key': ''
        }
    }
}

# Security defaults
#SESSION_COOKIE_SECURE = not DEBUG
#CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=not DEBUG)

# Rate limiting defaults (login endpoints will use decorators)

# Encryption key for sensitive inventory fields
FERNET_KEY = env('FERNET_KEY', default='')
OTP_HMAC_KEY = env('OTP_HMAC_KEY', default='')

# IPPanel SMS provider settings
IPPANEL_API_KEY = env('IPPANEL_API_KEY', default='')
IPPANEL_SENDER = env('IPPANEL_SENDER', default='')
IPPANEL_PATTERN_CODE = env('IPPANEL_PATTERN_CODE', default='')
IPPANEL_ORIGINATOR = env('IPPANEL_ORIGINATOR', default='')

# Enforce OTP_HMAC_KEY and FERNET_KEY in production
if not DEBUG:
    if not OTP_HMAC_KEY:
        raise ImproperlyConfigured(
            'OTP_HMAC_KEY must be set in production (set OTP_HMAC_KEY in environment).'
        )
    if not FERNET_KEY:
        raise ImproperlyConfigured(
            'FERNET_KEY must be set in production (set FERNET_KEY in environment).'
        )
    if SUPPORT_PUSH_ENABLED:
        missing_push_fields = [
            key for key, value in (
                ('VAPID_PUBLIC_KEY', VAPID_PUBLIC_KEY),
                ('VAPID_PRIVATE_KEY', VAPID_PRIVATE_KEY),
                ('VAPID_SUBJECT', VAPID_SUBJECT),
            )
            if not value
        ]
        if missing_push_fields:
            raise ImproperlyConfigured(
                'SUPPORT_PUSH_ENABLED=1 requires these env vars: '
                + ', '.join(missing_push_fields)
            )

# Cache: use Redis in production; locmem in dev (ok for single-threaded dev server)
# In production configure a real Redis instance and update CACHES accordingly in env
REDIS_URL = env('REDIS_URL', default='')
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'SOCKET_CONNECT_TIMEOUT': 5,
            }
        }
    }
else:
    # test/dev fallback — locmem (adequate for single-threaded dev/test)
    # For production with multiple processes, use Redis or Memcached
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'accountinox-cache',
        }
    }

# Silence django-ratelimit warnings about locmem in dev
SILENCED_SYSTEM_CHECKS = ['django_ratelimit.E003', 'django_ratelimit.W001']
# G-2: Production SSL/HTTPS Security Settings
# When behind a proxy (CloudFlare, cPanel proxy, etc.), set SECURE_PROXY_SSL_HEADER
SECURE_PROXY_SSL_HEADER = env('SECURE_PROXY_SSL_HEADER', default=None)
if SECURE_PROXY_SSL_HEADER:
    # Parse header name from env (e.g., "HTTP_X_FORWARDED_PROTO")
    SECURE_PROXY_SSL_HEADER = (SECURE_PROXY_SSL_HEADER.split(',')[0], SECURE_PROXY_SSL_HEADER.split(',')[1])

# Force HTTPS in production
if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
    
    # Strict Transport Security (HSTS) - Be cautious with these settings
    # Start conservative (1 hour) and increase after validation
    SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=3600)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False)
    SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=False)
else:
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0

# Additional security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# CSRF trusted origins for API calls across domains (if applicable)
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# Session and CSRF cookies (already set earlier, but reaffirmed)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# G-4: Logging configuration for production
import os
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOGS_DIR, 'django_error.log'),
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'file_info': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOGS_DIR, 'django_info.log'),
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 3,
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_error'] if DEBUG else ['file_error'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file_error'],
            'level': 'ERROR',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file_info'] if DEBUG else ['file_info'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Optional Sentry integration: enabled when SENTRY_DSN is provided in environment
SENTRY_DSN = env('SENTRY_DSN', default='').strip()
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration()],
            traces_sample_rate=env.float('SENTRY_TRACES_SAMPLE_RATE', default=0.0),
            send_default_pii=env.bool('SENTRY_SEND_PII', default=False),
            environment=env('SENTRY_ENVIRONMENT', default=''),
        )
        logging.getLogger('apps').info('Sentry initialized')
    except Exception:
        # avoid crashing startup if sentry is unavailable
        logging.getLogger('apps').exception('Failed to initialize Sentry')
