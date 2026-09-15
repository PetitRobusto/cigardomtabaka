"""Django settings for cigardomtabaka_backend."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django...tion')

DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')

# 客户收款链接对外访问地址；环境变量优先，未配置时按开发/生产环境取默认值。
_configured_privnote_base_url = os.getenv('PRIVNOTE_BASE_URL', '').strip().rstrip('/')
PRIVNOTE_BASE_URL = _configured_privnote_base_url or (
    'http://192.168.0.97:8000' if DEBUG else 'https://cigardomtabaka.com'
)

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'cigars',
    'privnote',
    'price_tracker',
    'accounting',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'cigardomtabaka_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'cigardomtabaka_backend.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / ('cigars_dev.db' if DEBUG else 'cigars.db'),
        'OPTIONS': {
            'init_command': (
                'PRAGMA journal_mode=WAL;'
                'PRAGMA foreign_keys=ON;'
            ),
            'timeout': 20,
        },
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

AUTH_USER_MODEL = 'cigars.User'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Media files (cigar images)
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Payment QR snapshots and customer payment evidence are deliberately outside
# MEDIA_ROOT.  They are served only by token-aware privnote views.
PRIVATE_PAYMENT_MEDIA_ROOT = Path(
    os.getenv('PRIVATE_PAYMENT_MEDIA_ROOT', str(BASE_DIR / 'private_payment_media'))
)

# The public proof endpoint accepts at most five 5 MiB files.  Reject an
# oversized multipart body before Django parses it or spools files to disk;
# deploy-time reverse-proxy limits must be kept at or below this value too.
PAYMENT_SUBMISSION_MAX_REQUEST_BYTES = 26 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = PAYMENT_SUBMISSION_MAX_REQUEST_BYTES

# DRF
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# CORS (dev only — tighten in prod)
CORS_ALLOW_ALL_ORIGINS = DEBUG

# Short-lived Privnote observations. Deployment is Nginx -> Gunicorn Unix
# socket; TCP proxies require explicit configuration before trusting X-Real-IP.
PRIVNOTE_ACCESS_RETENTION_DAYS = int(os.getenv('PRIVNOTE_ACCESS_RETENTION_DAYS', '30'))
PRIVNOTE_TRUSTED_PROXIES = tuple(value.strip() for value in os.getenv('PRIVNOTE_TRUSTED_PROXIES', 'unix').split(',') if value.strip())

# Internal Telegram notifications.  Destinations are fixed deployment
# configuration; the application does not accept Telegram chat IDs from HTTP
# requests or use Telegram identity as website authentication.
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
# Fixed internal destinations approved by the owner.  Environment variables
# remain available as an emergency override without a code deployment.
TELEGRAM_BUSINESS_CHAT_ID = os.getenv('TELEGRAM_BUSINESS_CHAT_ID', '-1003900174592').strip()
TELEGRAM_ERROR_CHAT_ID = os.getenv('TELEGRAM_ERROR_CHAT_ID', '8206776258').strip()
INTERNAL_SITE_URL = os.getenv('INTERNAL_SITE_URL', '').strip().rstrip('/')
TELEGRAM_NOTIFICATION_MAX_ATTEMPTS = 3
TELEGRAM_NOTIFICATION_CONNECT_TIMEOUT = 2.0
TELEGRAM_NOTIFICATION_READ_TIMEOUT = 5.0
TELEGRAM_ERROR_COOLDOWN_SECONDS = 300

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
        'telegram_errors': {
            'class': 'internal_notifications.logging_handler.TelegramErrorHandler',
            'level': 'ERROR',
        },
    },
    'root': {
        'handlers': ['console', 'telegram_errors'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'telegram_errors'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['console', 'telegram_errors'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
