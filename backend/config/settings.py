"""Базовые настройки Django-проекта.

Проект следует требованиям: Docker-only, Poetry, Swagger, JWT, Celery, Redis, PostgreSQL, Prometheus, JSON-логирование.
"""
from __future__ import annotations

import os
from pathlib import Path

import environ
import sentry_sdk


BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

DEBUG: bool = env("DJANGO_DEBUG")
SECRET_KEY = env("DJANGO_SECRET_KEY", default="please-change-me")
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])


# Приложения
INSTALLED_APPS = [
    # Метрики Prometheus (должны быть первыми)
    "django_prometheus",

    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Сторонние
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",

    # Проектные
    "api",
    "apps.users",
    "apps.catalog",
    "apps.marketing",
    "apps.orders",
    "apps.payments",
    "apps.vapi",
    "apps.scrapers",
    "apps.favorites",
    "apps.feedback",
    "apps.settings",
    "apps.pages",
    "apps.ai",
    "apps.recommendations",
]

# Кастомная модель пользователя
AUTH_USER_MODEL = 'users.User'

# Бэкенды аутентификации (поддержка входа по email, username и телефону)
AUTHENTICATION_BACKENDS = [
    'apps.users.backends.MultiFieldAuthBackend',  # Кастомный бэкенд (email, username, phone)
    'django.contrib.auth.backends.ModelBackend',  # Стандартный бэкенд Django (fallback)
]

MIDDLEWARE = [
    # Метрики Prometheus
    "django_prometheus.middleware.PrometheusBeforeMiddleware",

    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    # Кастомные middleware
    "apps.users.middleware.LanguageMiddleware",
    "apps.users.middleware.MobileDetectionMiddleware",

    # Метрики Prometheus
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# База данных
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://pharmaturk:pharmaturk@localhost:5432/pharmaturk",
    )
}


# Кэш и Celery брокер
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_TIME_LIMIT = 60 * 10
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
# Очередь ai для задач AI (воркер celery_ai слушает только её); recsys для рекомендаций
CELERY_TASK_ROUTES = {
    "apps.ai.tasks.*": {"queue": "ai"},
    "apps.recommendations.tasks.*": {"queue": "recsys"},
    "currency.*": {"queue": "celery"},
}
# Расписание Celery Beat. Подробности — см. CELERY_TASKS.md в корне проекта.
CELERY_BEAT_SCHEDULE = {
    # Валюта: обновление курсов каждые 4 часа
    "currency-update-rates": {
        "task": "currency.update_rates",
        "schedule": 60 * 60 * 4,
    },
    # Валюта: пересчёт цен товаров по курсам — раз в день
    "currency-update-prices": {
        "task": "currency.update_product_prices",
        "schedule": 60 * 60 * 24,
        "kwargs": {"batch_size": 200},
    },
    # refresh-stock: заглушка — отключено, доработаем после парсеров
    # "refresh-stock": {"task": "apps.catalog.tasks.refresh_stock", "schedule": 60 * 60 * 2},
    # VAPI: отключено — не используется. Включить при работе с VAPI API.
    # "vapi-sync-products": {"task": "apps.vapi.tasks.pull_products", "schedule": 60*60*6, "args": (1, 100)},
    # "vapi-sync-categories": {"task": "apps.vapi.tasks.sync_categories_and_brands", "schedule": 60*60*24},
    # "vapi-full-sync": {"task": "apps.vapi.tasks.full_catalog_sync", "schedule": 60*60*24*3, "args": (100,)},
    # run-all-scrapers: отключено, доработаем после парсеров
    # "run-all-scrapers": {"task": "apps.scrapers.tasks.run_all_active_scrapers", "schedule": 60 * 60 * 12},
    # Очистка старых сессий парсинга каждую неделю
    "cleanup-scraper-sessions": {
        "task": "apps.scrapers.tasks.cleanup_old_sessions",
        "schedule": 60 * 60 * 24 * 7,  # неделя
        "args": (30,),  # хранить 30 дней
    },
    # Поиск и объединение дубликатов — только ручной запуск (см. CELERY_TASKS.md)
    # "find-merge-duplicates": {
    #     "task": "apps.scrapers.tasks.find_and_merge_duplicates",
    #     "schedule": 60 * 60 * 24,  # день
    # },
    # Очистка неиспользуемых медиа из R2/локального хранилища ежедневно в 3:00
    "cleanup-orphaned-media": {
        "task": "catalog.cleanup_orphaned_media",
        "schedule": 60 * 60 * 24,  # день (можно заменить на crontab(0, 3) при наличии celery.schedules)
    },
    # AI: задачи, тратящие токены OpenAI, отключены — только ручной запуск через админку /admin/ai/manual-tasks/
    # AI: очистка старых логов (раз в неделю, не тратит токены)
    "ai-cleanup-old-logs": {
        "task": "apps.ai.tasks.cleanup_old_ai_logs",
        "schedule": 60 * 60 * 24 * 7,
        "kwargs": {"days": 30},
    },
    # RecSys: полная синхронизация векторов товаров в Qdrant (раз в сутки)
    "recsys-sync-all": {
        "task": "apps.recommendations.tasks.sync_all_products_to_qdrant",
        "schedule": 60 * 60 * 24 * 3,  # раз в 3 дня
    },
}


# i18n и локализация
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("ru", "Russian"),
]
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / 'locale']


# Статика/медиа
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Cloudflare R2 (опционально: если не заданы — используется локальное хранилище)
R2_ACCOUNT_ID = env("R2_ACCOUNT_ID", default="")
R2_ACCESS_KEY_ID = env("R2_ACCESS_KEY_ID", default="")
R2_SECRET_ACCESS_KEY = env("R2_SECRET_ACCESS_KEY", default="")
R2_BUCKET_NAME = env("R2_BUCKET_NAME", default="")
R2_PUBLIC_URL = env(
    "R2_PUBLIC_URL",
    default=f"https://{R2_BUCKET_NAME}.r2.dev" if R2_BUCKET_NAME else "",
)
R2_USE_SSL = env.bool("R2_USE_SSL", default=True)

# Storage backends: R2 для медиа при наличии учётных данных, иначе локальный диск
_USE_R2 = bool(R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME)

if _USE_R2:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
            "OPTIONS": {
                "access_key": R2_ACCESS_KEY_ID,
                "secret_key": R2_SECRET_ACCESS_KEY,
                "bucket_name": R2_BUCKET_NAME,
                "endpoint_url": f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
                "region_name": "auto",
                "file_overwrite": False,
                "custom_domain": (
                    R2_PUBLIC_URL.replace("https://", "").replace("http://", "") if R2_PUBLIC_URL else None
                ),
                "querystring_auth": False,
            },
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {
                "location": MEDIA_ROOT,
                "base_url": MEDIA_URL,
            },
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }


# DRF + JWT
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.AllowAny",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Turk-Export API",
    "DESCRIPTION": "MVP API для интернет-магазина турецких товаров",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}


# CORS и CSRF для продакшена (задать в .env)
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["https://localhost", "http://localhost"] if DEBUG else [],
)
CORS_ALLOW_ALL_ORIGINS = True if DEBUG else False
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-cart-session',  # Разрешаем заголовок для корзины
    'x-currency',  # Разрешаем заголовок для валюты
]


# Безопасность (базовые параметры для dev/QA)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_PROTECTION = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
X_FRAME_OPTIONS = "DENY"

# Отключаем автоматическое добавление завершающего слэша, чтобы не ломать POST-запросы
APPEND_SLASH = False

# Email/Company defaults
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@pharmaturk.local")
COMPANY_NAME = env("COMPANY_NAME", default="PharmaTurk")
COMPANY_SUPPORT_EMAIL = env("COMPANY_SUPPORT_EMAIL", default=DEFAULT_FROM_EMAIL)
COMPANY_SUPPORT_PHONE = env("COMPANY_SUPPORT_PHONE", default="+90 (000) 000-00-00")
COMPANY_ADDRESS = env("COMPANY_ADDRESS", default="Istanbul, Turkey")
COMPANY_SITE_URL = env("COMPANY_SITE_URL", default="https://pharmaturk.ru")
BOOKS_SEO_SITE_NAME = env("BOOKS_SEO_SITE_NAME", default=COMPANY_NAME)


# Sentry (неактивен, если DSN пуст)
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, enable_tracing=True)


# Логирование в JSON
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"}
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# JWT настройки
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': (
        'rest_framework_simplejwt.authentication.default_user_authentication_rule'
    ),

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}

# WhiteNoise: раздача статики через STORAGES["staticfiles"]

# AI Configuration
AI_CONFIG = {
    'MODEL': env("AI_MODEL", default="gpt-4o-mini"),
    'VISION_MODEL': env("AI_VISION_MODEL", default="gpt-4o-mini"),
    'EMBEDDING_MODEL': env("AI_EMBEDDING_MODEL", default="text-embedding-3-small"),
}

# R2 Configuration (Used for AI processing)
R2_CONFIG = {
    'endpoint_url': f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    'aws_access_key_id': R2_ACCESS_KEY_ID,
    'aws_secret_access_key': R2_SECRET_ACCESS_KEY,
    'region_name': 'auto',
    'bucket_name': R2_BUCKET_NAME,
}

AI_R2_SETTINGS = {
    'original_images_path': 'products/original/',
    'processed_images_path': 'products/processed/',
    'thumbnails_path': 'products/thumbs/',
    'temp_processing_path': 'temp/ai_processing/',
    'cdn_url': R2_PUBLIC_URL,
}

OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
