import os

import pytest


@pytest.fixture(scope="session")
def django_db_modify_db_settings(django_db_modify_db_settings_parallel_suffix):
    """Тестовая база — копия уже промигрированной, если она указана в TEST_DB_TEMPLATE.

    В CI отдельный шаг прогоняет все миграции с нуля на пустой базе, а каждый воркер
    pytest-xdist копирует её (CREATE DATABASE … TEMPLATE) вместо повторного прогона
    миграций. Схема та же, что после настоящего migrate: расширения, RunSQL-индексы и
    данные RunPython на месте. Без переменной всё как раньше — база создаётся миграциями.
    """
    template = os.environ.get("TEST_DB_TEMPLATE")
    if template:
        from django.conf import settings

        settings.DATABASES["default"].setdefault("TEST", {})["TEMPLATE"] = template


def pytest_collection_modifyitems(items):
    """Тесты миграций — первыми: они самые долгие (до 1,5 мин каждый).

    При параллельном запуске долгие тесты в начале расходятся по воркерам, а в хвосте
    очереди они доставались одному воркеру, и остальные простаивали (4 мин из 11).
    """
    items.sort(key=lambda item: not item.path.name.endswith("_migration.py"))


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


# Ответ ЦБ РФ в том виде, в каком его разбирает CurrencyRateService._parse_cbr_response.
_OFFLINE_CBR_RESPONSE = {
    "Valute": {
        "USD": {"CharCode": "USD", "Nominal": 1, "Value": 80.0},
        "EUR": {"CharCode": "EUR", "Nominal": 1, "Value": 90.0},
        "TRY": {"CharCode": "TRY", "Nominal": 10, "Value": 20.0},
        "KZT": {"CharCode": "KZT", "Nominal": 100, "Value": 16.0},
    }
}


@pytest.fixture(autouse=True)
def _offline_currency_rates(monkeypatch):
    """Курсы валют в тестах — без сети.

    Сохранение товара без курса в базе шло за курсом на cbr-xml-daily.ru. 18.11.2026 сайт
    перестал отвечать раннерам GitHub, запрос без таймаута висел, и весь набор снимался по
    30-минутному ограничителю. Как и в жизни: ЦБ отдаёт курсы, второй источник недоступен.
    """
    from apps.catalog.services import currency_service as services_module
    from apps.catalog.utils import currency_service as utils_module

    def offline_rates(self, source):
        if source == "centralbank_rf":
            return self._parse_cbr_response(_OFFLINE_CBR_RESPONSE)
        raise ConnectionError(f"network is disabled in tests: {source}")

    for module in (services_module, utils_module):
        monkeypatch.setattr(module.CurrencyRateService, "get_rates_from_source", offline_rates)
