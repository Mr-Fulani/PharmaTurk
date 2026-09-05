from types import SimpleNamespace

from apps.catalog import supplement_market_check_api
from apps.catalog.supplement_market_check_api import (
    build_supplement_market_check_response,
)
from apps.catalog.views import _build_supplement_market_check_response


def test_supplement_market_check_view_uses_extracted_contract():
    assert (
        _build_supplement_market_check_response
        is build_supplement_market_check_response
    )


def test_supplement_market_check_get_keeps_serialized_payload(monkeypatch):
    supplement = SimpleNamespace(pk=7)
    request = SimpleNamespace(method="GET")
    check = SimpleNamespace(status="pending")

    class StubService:
        def latest_for(self, item):
            assert item is supplement
            return check

        def serialize(self, item, latest):
            assert item is supplement
            assert latest is check
            return {"status": latest.status}

    monkeypatch.setattr(
        supplement_market_check_api,
        "SupplementMarketCheckService",
        StubService,
    )
    monkeypatch.setattr(
        supplement_market_check_api,
        "attach_public_market_price",
        lambda payload, *, product, request: payload,
    )

    response = build_supplement_market_check_response(
        supplement=supplement,
        request=request,
    )

    assert response.status_code == 200
    assert response.data == {"status": "pending"}
