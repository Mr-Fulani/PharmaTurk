"""DB-free checks for bounded public catalog query parameters."""

from types import SimpleNamespace
from unittest.mock import patch


def _bounded_query_int():
    with patch(
        "apps.catalog.models.service_portfolio_translation_fields_ready",
        return_value=False,
    ):
        from apps.catalog.views import _bounded_query_int as helper

    return helper


def test_bounded_query_int_clamps_large_and_negative_values():
    helper = _bounded_query_int()

    assert helper(SimpleNamespace(query_params={"limit": "999999"}), "limit", 12, maximum=50) == 50
    assert helper(SimpleNamespace(query_params={"limit": "-20"}), "limit", 12, maximum=50) == 1


def test_bounded_query_int_uses_default_for_malformed_values():
    helper = _bounded_query_int()

    assert helper(SimpleNamespace(query_params={"limit": "not-a-number"}), "limit", 12, maximum=50) == 12
