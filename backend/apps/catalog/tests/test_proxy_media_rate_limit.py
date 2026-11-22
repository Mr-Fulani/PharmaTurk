"""Лимит промахов кэша у proxy_media: до Django доходит только то, чего нет в кэше nginx."""

from unittest.mock import patch

import pytest
from django.test import RequestFactory, override_settings


@pytest.fixture
def views():
    with patch(
        'apps.catalog.models.service_portfolio_translation_fields_ready',
        return_value=False,
    ):
        from apps.catalog import views as catalog_views

    return catalog_views


def _request(**meta):
    return RequestFactory().get(
        '/api/catalog/proxy-media/', {'path': 'products/a/main-1.webp'}, **meta
    )


def test_public_visitor_is_counted_per_real_ip(views):
    # Адрес настоящий публичный: учебные диапазоны (203.0.113.0/24 и т. п.)
    # ipaddress считает частными, и лимит к ним не применяется.
    request = _request(HTTP_X_REAL_IP='8.8.8.8', HTTP_X_FORWARDED_FOR='198.51.100.1')

    with patch.object(views, '_cache_miss_within_limit', return_value=False) as within:
        assert views._proxy_media_cache_miss_allowed(request) is False

    within.assert_called_once_with(
        'proxy_media_miss', '8.8.8.8', views._PROXY_MEDIA_MISSES_PER_MINUTE
    )


@pytest.mark.parametrize('remote_addr', ['172.18.0.5', '127.0.0.1', '10.0.0.3'])
def test_internal_callers_are_not_limited(views, remote_addr):
    request = _request(REMOTE_ADDR=remote_addr)

    with patch.object(views, '_cache_miss_within_limit', return_value=False) as within:
        assert views._proxy_media_cache_miss_allowed(request) is True

    within.assert_not_called()


def test_counter_stops_after_the_limit(views):
    counters = {}

    def add(key, value, timeout=None):
        if key in counters:
            return False
        counters[key] = value
        return True

    def incr(key):
        counters[key] += 1
        return counters[key]

    with patch.object(views.cache, 'add', side_effect=add), patch.object(
        views.cache, 'incr', side_effect=incr
    ):
        results = [
            views._cache_miss_within_limit('proxy_media_miss', '203.0.113.9', 3)
            for _ in range(5)
        ]

    assert results == [True, True, True, False, False]


@override_settings(R2_PUBLIC_URL='https://cdn.example.com')
def test_view_answers_429_without_touching_storage(views):
    with patch.object(views, '_proxy_media_cache_miss_allowed', return_value=False), patch(
        'django.core.files.storage.default_storage'
    ) as storage:
        response = views.proxy_media(_request(HTTP_X_REAL_IP='203.0.113.9'))

    assert response.status_code == 429
    assert response['Retry-After'] == '60'
    storage.open.assert_not_called()
    storage.exists.assert_not_called()
