from types import SimpleNamespace

from apps.catalog.medicine_reference import build_medicine_reference_payload
from apps.catalog.views import _build_medicine_reference_payload


def test_medicine_reference_view_uses_extracted_contract():
    assert _build_medicine_reference_payload is build_medicine_reference_payload


def test_empty_medicine_reference_payload_keeps_legacy_shape():
    product = SimpleNamespace(
        active_ingredient="",
        atc_code="",
        sgk_equivalent_code="",
        analogs=SimpleNamespace(all=lambda: []),
    )
    request = SimpleNamespace(headers={}, query_params={})

    payload = build_medicine_reference_payload(product, request, limit=10)

    assert payload == {
        "count": 0,
        "active_ingredient": None,
        "atc_code": None,
        "results": [],
    }
