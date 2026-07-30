"""Тесты внутрипроцессного мемо-кэша курсов валют.

Списочные сериализаторы конвертируют цену каждой карточки в несколько валют;
без мемо отсутствующая пара запускала каскад пивот-запросов к БД на каждую
карточку (сотни SQL на страницу списка).
"""

from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.catalog.currency_models import CurrencyRate, GlobalCurrencySettings
from apps.catalog.utils.currency_service import CurrencyRateService, clear_rate_memo


@pytest.fixture(autouse=True)
def _clean_rate_caches():
    clear_rate_memo()
    cache.clear()
    yield
    clear_rate_memo()
    cache.clear()


def _create_rate(rate: str = "2.5"):
    return CurrencyRate.objects.create(
        from_currency="TRY",
        to_currency="RUB",
        rate=Decimal(rate),
        source="centralbank_rf",
        is_active=True,
    )


@pytest.mark.django_db
def test_missing_pair_is_not_memoized(django_assert_num_queries):
    """Новый курс должен подхватываться сразу, без отрицательного memo TTL."""
    service = CurrencyRateService()
    assert service.get_rate("TRY", "RUB") is None  # первый вызов — каскад пивотов

    _create_rate("2.5")
    assert service.get_rate("TRY", "RUB") == Decimal("2.5")


@pytest.mark.django_db
def test_found_rate_memoized_without_queries(django_assert_num_queries):
    _create_rate("2.5")
    service = CurrencyRateService()
    assert service.get_rate("TRY", "RUB") == Decimal("2.5")

    with django_assert_num_queries(0):
        assert service.get_rate("TRY", "RUB") == Decimal("2.5")


@pytest.mark.django_db
def test_reverse_rate_resolves_and_memoizes(django_assert_num_queries):
    _create_rate("2.5")
    service = CurrencyRateService()
    reverse = service.get_rate("RUB", "TRY")
    assert reverse == Decimal("1") / Decimal("2.5")

    with django_assert_num_queries(0):
        assert service.get_rate("RUB", "TRY") == reverse


@pytest.mark.django_db
def test_clear_rate_memo_picks_up_new_rate():
    service = CurrencyRateService()
    assert service.get_rate("TRY", "RUB") is None

    _create_rate("2.5")
    # Отрицательные результаты не кэшируются: ручное добавление курса видно сразу.
    assert service.get_rate("TRY", "RUB") == Decimal("2.5")


@pytest.mark.django_db
def test_usdt_markup_change_invalidates_cached_rate_in_all_cache_layers(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        GlobalCurrencySettings,
        "_schedule_usdt_snapshot_refresh",
        staticmethod(lambda: scheduled.append("refresh")),
    )
    CurrencyRate.objects.create(
        from_currency="TRY",
        to_currency="USD",
        rate=Decimal("2"),
        source="centralbank_rf",
        is_active=True,
    )
    settings = GlobalCurrencySettings.load()
    settings.usdt_markup_percentage = Decimal("3")
    settings.save()

    service = CurrencyRateService()
    assert service.get_rate("TRY", "USDT") == Decimal("2.0600000")

    settings.usdt_markup_percentage = Decimal("5")
    settings.save()

    assert service.get_rate("TRY", "USDT") == Decimal("2.1000000")
    assert scheduled == ["refresh"]
