import pytest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings

from apps.orders.services import _deny_receipt_external_resource, get_receipt_storage_key
from apps.orders.tasks import MAX_RECEIPT_PDF_BYTES, _load_receipt_pdf_from_storage


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/tracker.png",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
    ],
)
def test_receipt_renderer_rejects_external_resources(url):
    with pytest.raises(ValueError, match="External resources are disabled"):
        _deny_receipt_external_resource(url)


@override_settings(R2_CONFIG={"bucket_name": "receipts"})
@patch("apps.orders.tasks.get_r2_client")
def test_receipt_is_loaded_directly_from_bounded_storage_object(get_client):
    get_client.return_value.get_object.return_value = {
        "ContentLength": 9,
        "Body": BytesIO(b"%PDF-test"),
    }

    assert _load_receipt_pdf_from_storage(SimpleNamespace(number="ORDER-1")) == b"%PDF-test"
    key = get_client.return_value.get_object.call_args.kwargs["Key"]
    assert key.startswith("receipts/")
    assert key != "receipts/ORDER-1.pdf"
    get_client.return_value.get_object.assert_called_once()


@override_settings(SECRET_KEY="one-long-receipt-key")
def test_receipt_storage_key_is_deterministic_and_not_order_number_only():
    order = SimpleNamespace(id=7, number="ORDER-1")

    first = get_receipt_storage_key(order)
    second = get_receipt_storage_key(order)

    assert first == second
    assert first.endswith("/ORDER-1.pdf")
    assert first != "receipts/ORDER-1.pdf"


@override_settings(R2_CONFIG={"bucket_name": "receipts"})
@patch("apps.orders.tasks.get_r2_client")
def test_oversized_receipt_is_rejected_before_read(get_client):
    body = BytesIO(b"%PDF-test")
    get_client.return_value.get_object.return_value = {
        "ContentLength": MAX_RECEIPT_PDF_BYTES + 1,
        "Body": body,
    }

    assert _load_receipt_pdf_from_storage(SimpleNamespace(number="ORDER-1")) is None
