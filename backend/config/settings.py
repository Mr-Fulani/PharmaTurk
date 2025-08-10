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
    "apps.orders",
    "apps.payments",
    "apps.vapi",
]

# Кастомная модель пользователя
AUTH_USER_MODEL = 'users.User'

MIDDLEWARE = [
    # Метрики Prometheus
    "django_prometheus.middleware.PrometheusBeforeMiddleware",

    "django.middleware.security.SecurityMiddleware",
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
CELERY_BEAT_SCHEDULE = {
    # Обновление цен каждые 4-6 часов
    "refresh-prices": {
        "task": "apps.catalog.tasks.refresh_prices",
        "schedule": 60 * 60 * 4,  # 4 часа
    },
    # Обновление наличия каждые 2 часа
    "refresh-stock": {
        "task": "apps.catalog.tasks.refresh_stock",
        "schedule": 60 * 60 * 2,  # 2 часа
    },
    # Синхронизация товаров из API парсера каждые 6 часов
    "vapi-sync-products": {
        "task": "apps.vapi.tasks.pull_products",
        "schedule": 60 * 60 * 6,  # 6 часов
        "args": (1, 100),  # первая страница, 100 товаров
    },
    # Синхронизация справочников каждый день в 3:00
    "vapi-sync-categories": {
        "task": "apps.vapi.tasks.sync_categories_and_brands",
        "schedule": 60 * 60 * 24,  # 24 часа
    },
    # Полная синхронизация каталога каждые 3 дня в 2:00
    "vapi-full-sync": {
        "task": "apps.vapi.tasks.full_catalog_sync",
        "schedule": 60 * 60 * 24 * 3,  # 3 дня
        "args": (100,),  # максимум 100 страниц
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


# Статика/медиа
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# DRF + JWT
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
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


# CORS
CORS_ALLOW_ALL_ORIGINS = True if DEBUG else False


# Безопасность (базовые параметры для dev/QA)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_PROTECTION = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
X_FRAME_OPTIONS = "DENY"

# Отключаем автоматическое добавление завершающего слэша, чтобы не ломать POST-запросы
APPEND_SLASH = False


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
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',
    
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
    
    'JTI_CLAIM': 'jti',
    
    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}

