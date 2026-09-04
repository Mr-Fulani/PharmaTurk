"""Базовые настройки Django-проекта.

Проект следует требованиям: Docker-only, Poetry, Swagger, JWT, Celery, Redis, PostgreSQL, Prometheus, JSON-логирование.
"""
from __future__ import annotations

import os
from pathlib import Path

import environ
import sentry_sdk

from .security import (
    validate_production_settings,
    validate_database_url,
    validate_redis_separation,
    validate_telegram_webhook_settings,
)


BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

DEBUG: bool = env("DJANGO_DEBUG")
SECRET_KEY = env("DJANGO_SECRET_KEY", default="please-change-me")
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])
CRYPTO_DUMMY_MODE = env.bool("CRYPTO_DUMMY_MODE", default=False)

validate_production_settings(
    debug=DEBUG,
    secret_key=SECRET_KEY,
    allowed_hosts=ALLOWED_HOSTS,
    crypto_dummy_mode=CRYPTO_DUMMY_MODE,
)
validate_database_url(
    debug=DEBUG,
    database_url=env(
        "DATABASE_URL",
        default="postgres://mudaroba:mudaroba@localhost:5432/mudaroba",
    ),
)


# Приложения
INSTALLED_APPS = [
    # Метрики Prometheus (должны быть первыми)
    "django_prometheus",

    # Django
    "config.apps.MudarobaAdminConfig",
    "nested_admin",
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
    "api.apps.ApiConfig",
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
    "apps.monitoring.apps.MonitoringConfig",
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
        default="postgres://mudaroba:mudaroba@localhost:5432/mudaroba",
    )
}
# Переиспользуем соединения с Postgres вместо нового на каждый запрос
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"].setdefault("OPTIONS", {})["connect_timeout"] = env.int(
    "DB_CONNECT_TIMEOUT_SECONDS",
    default=5,
)


# Cache, Celery broker and result backend use separate logical databases. A
# cache eviction/clear must never delete queued tasks or their results.
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
REDIS_CACHE_URL = env("REDIS_CACHE_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND_URL = env("CELERY_RESULT_BACKEND_URL", default=REDIS_URL)
REDIS_CONNECT_TIMEOUT_SECONDS = env.float("REDIS_CONNECT_TIMEOUT_SECONDS", default=3.0)
REDIS_SOCKET_TIMEOUT_SECONDS = env.float("REDIS_SOCKET_TIMEOUT_SECONDS", default=3.0)
validate_redis_separation(
    debug=DEBUG,
    broker_url=REDIS_URL,
    cache_url=REDIS_CACHE_URL,
    result_url=CELERY_RESULT_BACKEND_URL,
)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
        "OPTIONS": {
            "socket_connect_timeout": REDIS_CONNECT_TIMEOUT_SECONDS,
            "socket_timeout": REDIS_SOCKET_TIMEOUT_SECONDS,
        },
    }
}

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = CELERY_RESULT_BACKEND_URL
CELERY_TASK_ALWAYS_EAGER = False
PRODUCTION_WATCHDOG_INTERVAL_SECONDS = env.int(
    "PRODUCTION_WATCHDOG_INTERVAL_SECONDS",
    default=300,
)
COINREMITTER_OUTBOX_DISPATCH_INTERVAL_SECONDS = env.int(
    "COINREMITTER_OUTBOX_DISPATCH_INTERVAL_SECONDS",
    default=60,
)
COINREMITTER_OUTBOX_DISPATCH_BATCH_SIZE = env.int(
    "COINREMITTER_OUTBOX_DISPATCH_BATCH_SIZE",
    default=100,
)
COINREMITTER_OUTBOX_REPUBLISH_SECONDS = env.int(
    "COINREMITTER_OUTBOX_REPUBLISH_SECONDS",
    default=300,
)
COINREMITTER_OUTBOX_STALE_SECONDS = env.int(
    "COINREMITTER_OUTBOX_STALE_SECONDS",
    default=180,
)
COINREMITTER_RECONCILIATION_INTERVAL_SECONDS = env.int(
    "COINREMITTER_RECONCILIATION_INTERVAL_SECONDS",
    default=300,
)
COINREMITTER_RECONCILIATION_BATCH_SIZE = env.int(
    "COINREMITTER_RECONCILIATION_BATCH_SIZE",
    default=10,
)
COINREMITTER_RECONCILIATION_MIN_AGE_MINUTES = env.int(
    "COINREMITTER_RECONCILIATION_MIN_AGE_MINUTES",
    default=10,
)
# Глобальный дефолт — 30 минут. Для скрейперов переопределяем ниже через CELERY_TASK_ANNOTATIONS.
CELERY_TASK_TIME_LIMIT = 60 * 30
ANONYMOUS_CART_TTL_DAYS = env.int("ANONYMOUS_CART_TTL_DAYS", default=30)
ANONYMOUS_CART_CLEANUP_BATCH_SIZE = env.int(
    "ANONYMOUS_CART_CLEANUP_BATCH_SIZE",
    default=500,
)
CELERY_TASK_SOFT_TIME_LIMIT = 60 * 25
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
# Redis возвращает неподтверждённую задачу в очередь после visibility timeout.
# Значение должно быть больше hard limit скрейпера, иначе долгий чанк может
# запуститься повторно ещё до завершения первого worker.
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 60 * 60 * 3}
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {"visibility_timeout": 60 * 60 * 3}
CELERY_VISIBILITY_TIMEOUT = 60 * 60 * 3
# При потере Redis worker прекращает late-ack задачи: их выполнит новый worker,
# вместо параллельной обработки старой и повторно доставленной копии.
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True
# Расширенные лимиты конкретно для scraper-задач (могут парсить сотни товаров с изображениями)
CELERY_TASK_ANNOTATIONS = {
    "apps.scrapers.tasks.run_scraper_task": {
        "time_limit": 60 * 60 * 2,       # hard limit: 2 часа
        "soft_time_limit": 60 * 60 * 1,  # soft limit: 1 час (можно перехватить SoftTimeLimitExceeded)
    },
    "apps.scrapers.tasks.run_instagram_scraper_task": {
        "time_limit": 60 * 60 * 2,
        "soft_time_limit": 60 * 60,
    },
    "apps.scrapers.tasks.run_stub_refresh_task": {
        "time_limit": 60 * 60 * 2,
        "soft_time_limit": 60 * 60,
    },
    "apps.monitoring.tasks.run_production_watchdog": {
        "time_limit": 60,
        "soft_time_limit": 45,
    },
    "apps.payments.tasks.create_coinremitter_invoice_request": {
        "time_limit": 90,
        "soft_time_limit": 75,
    },
    "apps.payments.tasks.reconcile_coinremitter_state": {
        "time_limit": 180,
        "soft_time_limit": 165,
    },
}
from celery.schedules import crontab

# Очереди изолированы: AI и тяжёлая векторизация не должны блокировать друг друга.
CELERY_TASK_ROUTES = {
    "apps.ai.tasks.*": {"queue": "ai"},
    "apps.recommendations.tasks.*": {"queue": "recsys"},
    "apps.payments.tasks.*": {"queue": "celery"},
    "apps.monitoring.tasks.*": {"queue": "celery"},
    "currency.*": {"queue": "celery"},
}
# Расписание Celery Beat. Подробности — см. CELERY_TASKS.md в корне проекта.
CELERY_BEAT_SCHEDULE = {
    "monitoring-production-watchdog": {
        "task": "apps.monitoring.tasks.run_production_watchdog",
        "schedule": PRODUCTION_WATCHDOG_INTERVAL_SECONDS,
    },
    "coinremitter-outbox-dispatch": {
        "task": "apps.payments.tasks.dispatch_pending_crypto_invoice_requests",
        "schedule": COINREMITTER_OUTBOX_DISPATCH_INTERVAL_SECONDS,
    },
    "coinremitter-reconciliation": {
        "task": "apps.payments.tasks.reconcile_coinremitter_state",
        "schedule": COINREMITTER_RECONCILIATION_INTERVAL_SECONDS,
    },
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
    # Ограничиваем storage amplification от брошенных гостевых корзин.
    "orders-cleanup-stale-anonymous-carts": {
        "task": "orders.cleanup_stale_anonymous_carts",
        "schedule": crontab(hour=4, minute=10),
        "kwargs": {
            "days": ANONYMOUS_CART_TTL_DAYS,
            "batch_size": ANONYMOUS_CART_CLEANUP_BATCH_SIZE,
        },
    },
    # Поиск кандидатов в дубликаты товаров — раз в неделю, с уведомлением админа
    "scrapers-weekly-duplicate-candidates": {
        "task": "apps.scrapers.tasks.find_and_merge_duplicates",
        "schedule": crontab(hour=4, minute=30, day_of_week=1),  # понедельник в 4:30
    },
    # Очистка неиспользуемых медиа из R2/локального хранилища ежедневно в 3:00
    "cleanup-orphaned-media": {
        "task": "catalog.cleanup_orphaned_media",
        "schedule": crontab(hour=3, minute=0),
    },
    # AI: задачи, тратящие токены OpenAI, отключены — только ручной запуск через админку /admin/ai/manual-tasks/
    # Крипто: пометить истёкшие инвойсы (каждые 10 мин)
    "payments-expire-crypto-invoices": {
        "task": "apps.payments.tasks.expire_pending_crypto_payments",
        "schedule": 60 * 10,
    },
    # AI: очистка старых логов (раз в неделю, не тратит токены)
    "ai-cleanup-old-logs": {
        "task": "apps.ai.tasks.cleanup_old_ai_logs",
        "schedule": 60 * 60 * 24 * 7,
        "kwargs": {"days": 30},
    },
    # RecSys: каждую ночь индексируем только новые/изменённые товары малыми пакетами.
    # Полная переиндексация остаётся только ручной операцией.
    "recsys-sync-stale-nightly": {
        "task": "apps.recommendations.tasks.sync_stale_products_to_qdrant",
        "schedule": crontab(hour=2, minute=15),
        "kwargs": {"batch_size": 25, "max_products": 200},
    },
    # Очистка временных файлов поиска по фото (каждый час)
    "cleanup-temp-images": {
        "task": "apps.recommendations.tasks.cleanup_temp_images",
        "schedule": 60 * 60,  # 1 hour
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

# Django 6 changes the default URL form-field scheme to HTTPS. Opt in now so
# validation is stable across the supported Django 5.2 -> 6.0 upgrade path.
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

# Storage configuration
USE_R2 = env.bool("USE_R2", default=bool(R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME))
R2_PREFIX = env("R2_PREFIX", default="dev/" if DEBUG else "").strip("/")

if USE_R2:
    # Пул соединений urllib3/botocore к R2: при множестве параллельных proxy_media не заполнять пул (предупреждение «pool is full»).
    from botocore.config import Config as BotoCoreConfig

    R2_BOTO_MAX_POOL_CONNECTIONS = env.int("R2_BOTO_MAX_POOL_CONNECTIONS", default=64)
    _r2_s3_client_config = BotoCoreConfig().merge(
        BotoCoreConfig(
            max_pool_connections=R2_BOTO_MAX_POOL_CONNECTIONS,
            connect_timeout=10,
            read_timeout=300,
        )
    )

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
                "location": R2_PREFIX,
                "client_config": _r2_s3_client_config,
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
# JWTSafeAuthentication: при невалидном/просроченном токене возвращает None (анонимный доступ),
# чтобы AllowAny-эндпоинты работали через ngrok при старом токене в cookies
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "api.authentication.JWTSafeAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Mudaroba API",
    "DESCRIPTION": "MVP API для интернет-магазина турецких товаров",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "PREPROCESSING_HOOKS": ["api.schema.canonicalize_compatibility_routes"],
    "ENUM_NAME_OVERRIDES": {
        "AIProcessingStatusEnum": "apps.ai.models.AIProcessingStatus",
        "CatalogCurrencyEnum": "apps.catalog.models.CURRENCY_CHOICES",
        "CatalogLocaleEnum": "apps.catalog.models.CategoryTranslation.LOCALE_CHOICES",
        "ExtendedCatalogLocaleEnum": (
            "apps.catalog.models.SportsProductTranslation.LOCALE_CHOICES"
        ),
    },
}


# Настройки SSL/Proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# CORS и CSRF для продакшена (задать в .env)
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["https://mudaroba.com", "https://www.mudaroba.com", "https://localhost", "http://localhost"] if DEBUG else ["https://mudaroba.com", "https://www.mudaroba.com"],
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
    'accept-language',  # Разрешаем заголовок для локализации
    'x-language',  # Разрешаем заголовок для локализации
]


# Безопасность (базовые параметры для dev/QA)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_PROTECTION = True
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=False,
)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
X_FRAME_OPTIONS = "DENY"
# Opt into Django 6's safer URLField default while this Django 5 transition
# setting still exists. Remove the setting itself during the Django 6 upgrade.
FORMS_URLFIELD_ASSUME_HTTPS = True

# Отключаем автоматическое добавление завершающего слэша, чтобы не ломать POST-запросы
APPEND_SLASH = False

# Email/Company defaults
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=30)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@mudaroba.local")
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
EMAIL_ADMIN = env("EMAIL_ADMIN", default=DEFAULT_FROM_EMAIL)
# Отправка писем через API (SendGrid или SMTP2GO)
EMAIL_API_PROVIDER = env("EMAIL_API_PROVIDER", default="")
EMAIL_API_FROM = env("EMAIL_API_FROM", default="")
EMAIL_API_TIMEOUT = env.int("EMAIL_API_TIMEOUT", default=15)
SENDGRID_API_KEY = env("SENDGRID_API_KEY", default="")
SMTP2GO_API_KEY = env("SMTP2GO_API_KEY", default="")
SMTP2GO_API_URL = env("SMTP2GO_API_URL", default="https://api.smtp2go.com/v3")
RESEND_API_KEY = env("RESEND_API_KEY", default="")
RESEND_API_URL = env("RESEND_API_URL", default="https://api.resend.com")
RESEND_USER_AGENT = env("RESEND_USER_AGENT", default="mudaroba/1.0")
COMPANY_NAME = env("COMPANY_NAME", default="Mudaroba")
COMPANY_SUPPORT_EMAIL = env("COMPANY_SUPPORT_EMAIL", default=DEFAULT_FROM_EMAIL)
COMPANY_SUPPORT_PHONE = env("COMPANY_SUPPORT_PHONE", default="+90 (000) 000-00-00")
COMPANY_ADDRESS = env("COMPANY_ADDRESS", default="Istanbul, Turkey")
COMPANY_SITE_URL = env("COMPANY_SITE_URL", default="https://mudaroba.com")
BOOKS_SEO_SITE_NAME = env("BOOKS_SEO_SITE_NAME", default=COMPANY_NAME)


# Прокси для парсеров (например турецкий residential/mobile для обхода
# репутационных блокировок Akamai на Zara). Пусто = прямое соединение.
SCRAPER_PROXY_URL = env("SCRAPER_PROXY_URL", default="")
# PEM bundle of the proxy CA when the provider performs TLS inspection.
# Certificate verification is never disabled automatically.
# Bright Data native proxy must use its port-44445 root from /app/certs.
SCRAPER_PROXY_CA_BUNDLE = env("SCRAPER_PROXY_CA_BUNDLE", default="")

# FLO can opt into Bright Data's CAPTCHA-solving REST transport, but only when
# an interactive caller explicitly requests it (product-card open or cart revalidate).
# Background scraping never opts in merely because this environment flag is true.
FLO_WEB_UNLOCKER_ENABLED = env.bool("FLO_WEB_UNLOCKER_ENABLED", default=False)
BRIGHTDATA_WEB_UNLOCKER_API_KEY = env(
    "BRIGHTDATA_WEB_UNLOCKER_API_KEY", default=""
)
BRIGHTDATA_WEB_UNLOCKER_ZONE = env("BRIGHTDATA_WEB_UNLOCKER_ZONE", default="")
FLO_WEB_UNLOCKER_COUNTRY = env("FLO_WEB_UNLOCKER_COUNTRY", default="tr")
FLO_WEB_UNLOCKER_RENDER = env.bool("FLO_WEB_UNLOCKER_RENDER", default=True)
FLO_WEB_UNLOCKER_EXPECT_TEXT = env(
    "FLO_WEB_UNLOCKER_EXPECT_TEXT", default=""
)
FLO_WEB_UNLOCKER_TIMEOUT_SECONDS = env.float(
    "FLO_WEB_UNLOCKER_TIMEOUT_SECONDS", default=60.0
)
FLO_WEB_UNLOCKER_MAX_RESPONSE_BYTES = env.int(
    "FLO_WEB_UNLOCKER_MAX_RESPONSE_BYTES", default=10 * 1024 * 1024
)

# Phase 2 source-offer recording. Disabled by default for a migration-first rollout:
# enabling the writer must be a separate deploy/config action after migration 0202.
SOURCE_OFFER_RECORDING_ENABLED = env.bool("SOURCE_OFFER_RECORDING_ENABLED", default=False)
SOURCE_OFFER_DEFAULT_PRIORITY = env.int("SOURCE_OFFER_DEFAULT_PRIORITY", default=100)
SOURCE_OFFER_SOURCE_PRIORITIES = env.json("SOURCE_OFFER_SOURCE_PRIORITIES", default={})

# Live supplier checks remain off until source-by-source rollout. Full scraper recording
# above is independent and can be enabled earlier.
SOURCE_OFFER_VERIFICATION_ENABLED = env.bool(
    "SOURCE_OFFER_VERIFICATION_ENABLED", default=False
)
SOURCE_OFFER_VERIFICATION_SOURCES = env.list(
    "SOURCE_OFFER_VERIFICATION_SOURCES", default=[]
)
# Sources in this list are catalogue/manual sources, not reliable live suppliers.
# They must never change cart/card price or availability, even if accidentally
# added to a live verification allowlist.
SOURCE_OFFER_MANUAL_ONLY_SOURCES = env.list(
    "SOURCE_OFFER_MANUAL_ONLY_SOURCES", default=["instagram"]
)
SOURCE_OFFER_REQUEST_TIMEOUT_SECONDS = env.float(
    "SOURCE_OFFER_REQUEST_TIMEOUT_SECONDS", default=5.0
)
SOURCE_OFFER_MAX_RETRIES = env.int("SOURCE_OFFER_MAX_RETRIES", default=1)
SOURCE_OFFER_RETRY_BACKOFF_SECONDS = env.float(
    "SOURCE_OFFER_RETRY_BACKOFF_SECONDS", default=0.1
)
SOURCE_OFFER_SUCCESS_CACHE_TTL = env.int("SOURCE_OFFER_SUCCESS_CACHE_TTL", default=120)
SOURCE_OFFER_ERROR_CACHE_TTL = env.int("SOURCE_OFFER_ERROR_CACHE_TTL", default=15)
SOURCE_OFFER_SINGLEFLIGHT_WAIT_SECONDS = env.float(
    "SOURCE_OFFER_SINGLEFLIGHT_WAIT_SECONDS", default=0.5
)
SOURCE_OFFER_CIRCUIT_FAILURE_THRESHOLD = env.int(
    "SOURCE_OFFER_CIRCUIT_FAILURE_THRESHOLD", default=5
)
SOURCE_OFFER_CIRCUIT_RECOVERY_SECONDS = env.int(
    "SOURCE_OFFER_CIRCUIT_RECOVERY_SECONDS", default=60
)
SOURCE_OFFER_DEFAULT_CONCURRENCY = env.int("SOURCE_OFFER_DEFAULT_CONCURRENCY", default=4)
SOURCE_OFFER_SOURCE_CONCURRENCY = env.json("SOURCE_OFFER_SOURCE_CONCURRENCY", default={})
SOURCE_OFFER_DEFAULT_RATE_PER_MINUTE = env.int(
    "SOURCE_OFFER_DEFAULT_RATE_PER_MINUTE", default=60
)
SOURCE_OFFER_SOURCE_RATE_PER_MINUTE = env.json(
    "SOURCE_OFFER_SOURCE_RATE_PER_MINUTE", default={}
)
# Demand-driven full-card refresh is isolated from checkout verification. It may
# update only importer-owned price/inventory fields of a persisted source offer.
PRODUCT_CARD_SOURCE_REFRESH_ENABLED = env.bool(
    "PRODUCT_CARD_SOURCE_REFRESH_ENABLED", default=False
)
PRODUCT_CARD_SOURCE_REFRESH_SOURCES = env.list(
    "PRODUCT_CARD_SOURCE_REFRESH_SOURCES", default=[]
)
PRODUCT_CARD_SOURCE_REFRESH_TIMEOUT_SECONDS = env.float(
    "PRODUCT_CARD_SOURCE_REFRESH_TIMEOUT_SECONDS", default=12.0
)
PRODUCT_CARD_SOURCE_REFRESH_MAX_RETRIES = env.int(
    "PRODUCT_CARD_SOURCE_REFRESH_MAX_RETRIES", default=1
)
PRODUCT_CARD_SOURCE_REFRESH_STATE_TTL_SECONDS = env.int(
    "PRODUCT_CARD_SOURCE_REFRESH_STATE_TTL_SECONDS", default=300
)
PRODUCT_CARD_SOURCE_REFRESH_ERROR_TTL_SECONDS = env.int(
    "PRODUCT_CARD_SOURCE_REFRESH_ERROR_TTL_SECONDS", default=30
)
PRODUCT_CARD_SOURCE_REFRESH_LOCK_SECONDS = env.int(
    "PRODUCT_CARD_SOURCE_REFRESH_LOCK_SECONDS", default=150
)
PRODUCT_CARD_SOURCE_REFRESH_MIN_PRICE_RATIO = env.float(
    "PRODUCT_CARD_SOURCE_REFRESH_MIN_PRICE_RATIO", default=0.05
)
PRODUCT_CARD_SOURCE_REFRESH_MAX_PRICE_RATIO = env.float(
    "PRODUCT_CARD_SOURCE_REFRESH_MAX_PRICE_RATIO", default=20.0
)
# Repeat full scrapes may still enrich Instagram content/media, but existing
# storefront prices remain manager-owned until a reliable price API is available.
SCRAPER_PRICE_REFRESH_DISABLED_SOURCES = env.list(
    "SCRAPER_PRICE_REFRESH_DISABLED_SOURCES", default=["instagram"]
)
# Fresh successful offer rows may override availability in public detail/YML
# output. Kept separate from cart enforcement and disabled for staged rollout.
SOURCE_OFFER_CATALOG_PROJECTION_ENABLED = env.bool(
    "SOURCE_OFFER_CATALOG_PROJECTION_ENABLED", default=False
)
# Cart enforcement is a separate rollout gate. Operators may exercise/observe the
# verification service before any existing cart behaviour changes.
SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = env.bool(
    "SOURCE_OFFER_CART_ENFORCEMENT_ENABLED", default=False
)
SOURCE_OFFER_RESERVATION_CAPABLE_SOURCES = env.list(
    "SOURCE_OFFER_RESERVATION_CAPABLE_SOURCES", default=[]
)
# Product types listed here may never fall back to legacy catalog stock when live
# supplier verification is enabled. Supplements are reference-catalog products until
# a dedicated, explicitly allowed stock adapter is configured.
SOURCE_OFFER_CART_REQUIRED_PRODUCT_TYPES = env.list(
    "SOURCE_OFFER_CART_REQUIRED_PRODUCT_TYPES", default=["supplements"]
)
SUPPLEMENT_STOCK_ADAPTER_SOURCES = env.list(
    "SUPPLEMENT_STOCK_ADAPTER_SOURCES", default=[]
)
# Demand-driven seller discovery for supplements.  This remains separate from
# the reference-price flag: only a strict match may create a payable source offer.
SUPPLEMENT_STOCK_DISCOVERY_ENABLED = env.bool(
    "SUPPLEMENT_STOCK_DISCOVERY_ENABLED", default=False
)
SUPPLEMENT_STOCK_DISCOVERY_REQUEST_TIMEOUT_SECONDS = env.int(
    "SUPPLEMENT_STOCK_DISCOVERY_REQUEST_TIMEOUT_SECONDS", default=12
)
SUPPLEMENT_STOCK_DISCOVERY_ENQUEUE_LOCK_SECONDS = env.int(
    "SUPPLEMENT_STOCK_DISCOVERY_ENQUEUE_LOCK_SECONDS", default=60
)
SUPPLEMENT_STOCK_DISCOVERY_NO_MATCH_TTL_SECONDS = env.int(
    "SUPPLEMENT_STOCK_DISCOVERY_NO_MATCH_TTL_SECONDS", default=60 * 60 * 6
)
SUPPLEMENT_STOCK_DISCOVERY_ERROR_TTL_SECONDS = env.int(
    "SUPPLEMENT_STOCK_DISCOVERY_ERROR_TTL_SECONDS", default=300
)

# Точечная справочная проверка цены медикамента по пользовательскому intent.
# Она не участвует в корзине и никогда не обновляет наличие/остаток лекарства.
MEDICINE_MARKET_CHECK_ENABLED = env.bool(
    "MEDICINE_MARKET_CHECK_ENABLED", default=False
)
MEDICINE_MARKET_CHECK_SOURCES = env.list(
    "MEDICINE_MARKET_CHECK_SOURCES", default=["ilacfiyati"]
)
MEDICINE_MARKET_CHECK_FRESH_SECONDS = env.int(
    "MEDICINE_MARKET_CHECK_FRESH_SECONDS", default=60 * 60 * 12
)
MEDICINE_MARKET_CHECK_ERROR_FRESH_SECONDS = env.int(
    "MEDICINE_MARKET_CHECK_ERROR_FRESH_SECONDS", default=300
)
MEDICINE_MARKET_CHECK_STALE_RUNNING_SECONDS = env.int(
    "MEDICINE_MARKET_CHECK_STALE_RUNNING_SECONDS", default=180
)
MEDICINE_MARKET_CHECK_ENQUEUE_LOCK_SECONDS = env.int(
    "MEDICINE_MARKET_CHECK_ENQUEUE_LOCK_SECONDS", default=30
)
MEDICINE_MARKET_CHECK_GLOBAL_RATE_PER_MINUTE = env.int(
    "MEDICINE_MARKET_CHECK_GLOBAL_RATE_PER_MINUTE", default=10
)
MEDICINE_MARKET_CHECK_SOURCE_CONCURRENCY = env.int(
    "MEDICINE_MARKET_CHECK_SOURCE_CONCURRENCY", default=2
)
MEDICINE_MARKET_CHECK_REQUEST_TIMEOUT_SECONDS = env.int(
    "MEDICINE_MARKET_CHECK_REQUEST_TIMEOUT_SECONDS", default=15
)
MEDICINE_MARKET_CHECK_MAX_ANALOGS = env.int(
    "MEDICINE_MARKET_CHECK_MAX_ANALOGS", default=50
)

# On-demand reference-price observation for supplements. This deliberately does not
# imply buyable stock: sales require a separate source in
# SUPPLEMENT_STOCK_ADAPTER_SOURCES and the regular source-offer checkout preflight.
SUPPLEMENT_MARKET_CHECK_ENABLED = env.bool(
    "SUPPLEMENT_MARKET_CHECK_ENABLED", default=False
)
SUPPLEMENT_MARKET_CHECK_SOURCES = env.list(
    "SUPPLEMENT_MARKET_CHECK_SOURCES", default=["ilacfiyati"]
)
SUPPLEMENT_MARKET_CHECK_FRESH_SECONDS = env.int(
    "SUPPLEMENT_MARKET_CHECK_FRESH_SECONDS", default=60 * 60 * 12
)
SUPPLEMENT_MARKET_CHECK_ERROR_FRESH_SECONDS = env.int(
    "SUPPLEMENT_MARKET_CHECK_ERROR_FRESH_SECONDS", default=300
)
SUPPLEMENT_MARKET_CHECK_STALE_RUNNING_SECONDS = env.int(
    "SUPPLEMENT_MARKET_CHECK_STALE_RUNNING_SECONDS", default=180
)
SUPPLEMENT_MARKET_CHECK_ENQUEUE_LOCK_SECONDS = env.int(
    "SUPPLEMENT_MARKET_CHECK_ENQUEUE_LOCK_SECONDS", default=30
)
SUPPLEMENT_MARKET_CHECK_GLOBAL_RATE_PER_MINUTE = env.int(
    "SUPPLEMENT_MARKET_CHECK_GLOBAL_RATE_PER_MINUTE", default=10
)
SUPPLEMENT_MARKET_CHECK_SOURCE_CONCURRENCY = env.int(
    "SUPPLEMENT_MARKET_CHECK_SOURCE_CONCURRENCY", default=2
)
SUPPLEMENT_MARKET_CHECK_REQUEST_TIMEOUT_SECONDS = env.int(
    "SUPPLEMENT_MARKET_CHECK_REQUEST_TIMEOUT_SECONDS", default=15
)


# Sentry (неактивен, если DSN пуст)
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        enable_tracing=True,
        traces_sample_rate=min(
            max(env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.05), 0.0),
            1.0,
        ),
        send_default_pii=False,
    )


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

# Media Enrichment
SERPER_API_KEY = env("SERPER_API_KEY", default="")
MEDICINE_MEDIA_MIN_WIDTH = env.int("MEDICINE_MEDIA_MIN_WIDTH", default=400)
MEDICINE_MEDIA_MIN_HEIGHT = env.int("MEDICINE_MEDIA_MIN_HEIGHT", default=400)
MEDICINE_MEDIA_MAX_PER_PRODUCT = env.int("MEDICINE_MEDIA_MAX_PER_PRODUCT", default=3)


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

# R2 Configuration (Used for AI processing and media proxy)
R2_CONFIG = {
    'endpoint_url': f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    'aws_access_key_id': R2_ACCESS_KEY_ID,
    'aws_secret_access_key': R2_SECRET_ACCESS_KEY,
    'region_name': 'auto',
    'bucket_name': R2_BUCKET_NAME,
    'prefix': R2_PREFIX,
    'public_url': (R2_PUBLIC_URL or '').rstrip('/'),
}

AI_R2_SETTINGS = {
    'original_images_path': 'products/original/',
    'processed_images_path': 'products/processed/',
    'thumbnails_path': 'products/thumbs/',
    'temp_processing_path': 'temp/ai_processing/',
    'cdn_url': R2_PUBLIC_URL,
}

OPENAI_API_KEY = env("OPENAI_API_KEY", default="")

# CoinRemitter (crypto payments)
COINREMITTER_API_KEY = env("COINREMITTER_API_KEY", default="")
COINREMITTER_API_PASSWORD = env("COINREMITTER_API_PASSWORD", default="")
COINREMITTER_COIN = env("COINREMITTER_COIN", default="USDTTRC20")
COINREMITTER_WEBHOOK_SECRET = env("COINREMITTER_WEBHOOK_SECRET", default="")
COINREMITTER_WEBHOOK_IP_WHITELIST = env.list("COINREMITTER_WEBHOOK_IP_WHITELIST", default=[])
SITE_URL = env("SITE_URL", default="http://localhost:3000").rstrip("/")
# Для success_url/fail_url: URL фронтенда (checkout-success). По умолчанию = SITE_URL.
FRONTEND_SITE_URL = env("FRONTEND_SITE_URL", default="").rstrip("/") or SITE_URL

# Telegram notifications
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_BOT_USERNAME = env("TELEGRAM_BOT_USERNAME", default="") or env("NEXT_PUBLIC_TELEGRAM_BOT_USERNAME", default="")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID", default="")
TELEGRAM_WEBHOOK_SECRET = env("TELEGRAM_WEBHOOK_SECRET", default="")
PRODUCTION_WATCHDOG_ENABLED = env.bool("PRODUCTION_WATCHDOG_ENABLED", default=False)
PRODUCTION_WATCHDOG_BASE_URL = env(
    "PRODUCTION_WATCHDOG_BASE_URL",
    default="https://mudaroba.com",
).rstrip("/")
PRODUCTION_WATCHDOG_FAILURE_THRESHOLD = env.int(
    "PRODUCTION_WATCHDOG_FAILURE_THRESHOLD",
    default=2,
)
PRODUCTION_WATCHDOG_REPEAT_SECONDS = env.int(
    "PRODUCTION_WATCHDOG_REPEAT_SECONDS",
    default=3600,
)
PRODUCTION_WATCHDOG_REQUEST_TIMEOUT_SECONDS = env.int(
    "PRODUCTION_WATCHDOG_REQUEST_TIMEOUT_SECONDS",
    default=10,
)
validate_telegram_webhook_settings(
    debug=DEBUG,
    bot_token=TELEGRAM_BOT_TOKEN,
    webhook_secret=TELEGRAM_WEBHOOK_SECRET,
)

# authenticated: любой авторизованный; purchased: только покупатель доставленного заказа.
PRODUCT_REVIEW_ACCESS_POLICY = env("PRODUCT_REVIEW_ACCESS_POLICY", default="authenticated")

# Google OAuth2 (Sign In With Google / Google One Tap)
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", default="")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET", default="")

# VK OAuth (VK ID SDK)
VK_APP_ID = env("VK_APP_ID", default="")
VK_APP_SECRET = env("VK_APP_SECRET", default="")

# VK Market API (управление товарами и фото через API сообщества)
# Токен получить: vk.com/club → Управление → Настройки → Работа с API
VK_API_TOKEN = env("VK_YML_API", default="")
VK_GROUP_ID = env.int("VK_GROUP_ID", default=0)
# Пользовательский токен (нужен для market.get):
# https://oauth.vk.com/authorize?client_id=APP_ID&display=page&redirect_uri=https://oauth.vk.com/blank.html&scope=market,photos,video,offline&response_type=token&v=5.131
VK_USER_TOKEN = env("VK_USER_TOKEN", default="")

# Increase data upload fields because admin uses filter_horizontal for thousands of categories
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000
