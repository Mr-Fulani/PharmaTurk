import pytest


@pytest.fixture(autouse=True)
def _isolate_test_cache(settings):
    """Тестовые данные не должны попадать в Redis работающего приложения."""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "backend-tests",
        }
    }
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
