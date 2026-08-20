"""DB-free security regressions for nightly medicine image enrichment."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image

from apps.catalog.services.medicine_media_enricher import (
    MedicineMediaEnricher,
    _query_free_source_url,
)
from apps.recommendations.services import safe_image_fetcher


def _image_bytes(image_format: str = "JPEG", size: tuple[int, int] = (500, 500)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size=size, color=(20, 40, 60)).save(output, image_format)
    return output.getvalue()


def _enricher() -> MedicineMediaEnricher:
    enricher = MedicineMediaEnricher.__new__(MedicineMediaEnricher)
    enricher.min_width = 400
    enricher.min_height = 400
    return enricher


def test_candidate_uses_one_hardened_fetch_and_reuses_exact_bytes(monkeypatch):
    enricher = _enricher()
    image_data = _image_bytes()
    fetch = Mock(return_value=(image_data, "image/jpeg"))
    saved_record = object()
    save = Mock(return_value=saved_record)
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", fetch)
    monkeypatch.setattr(enricher, "save_validated_image", save)
    product = SimpleNamespace(id=7)
    url = "https://images.example.test/medicine.jpg"

    result = enricher.process_candidate(product, url)

    assert result is saved_record
    fetch.assert_called_once_with(url)
    save.assert_called_once()
    saved_product, saved_url, fetched = save.call_args.args
    assert saved_product is product
    assert saved_url == url
    assert fetched.content is image_data
    assert fetched.extension == ".jpg"
    assert (fetched.width, fetched.height) == (500, 500)


def test_private_or_rebinding_target_is_rejected_before_persistence(monkeypatch, caplog):
    enricher = _enricher()
    fetch = Mock(side_effect=safe_image_fetcher.UnsafeImageURLError())
    save = Mock(side_effect=AssertionError("unsafe candidate must not be persisted"))
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", fetch)
    monkeypatch.setattr(enricher, "save_validated_image", save)
    product = SimpleNamespace(id=7)
    secret = "signed-query-value"
    url = f"http://169.254.169.254/latest/meta-data?token={secret}"

    assert enricher.process_candidate(product, url) is None

    fetch.assert_called_once_with(url)
    save.assert_not_called()
    assert secret not in caplog.text


def test_persisted_source_url_drops_query_and_fragment():
    source = "https://cdn.example.test/images/medicine.jpg?token=secret#fragment"

    assert _query_free_source_url(source) == "https://cdn.example.test/images/medicine.jpg"


def test_declared_or_streamed_oversize_is_rejected_before_persistence(monkeypatch):
    enricher = _enricher()
    fetch = Mock(side_effect=safe_image_fetcher.ImageTooLargeError())
    save = Mock(side_effect=AssertionError("oversized candidate must not be persisted"))
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", fetch)
    monkeypatch.setattr(enricher, "save_validated_image", save)

    assert enricher.process_candidate(SimpleNamespace(id=7), "https://images.example/huge.jpg") is None

    fetch.assert_called_once()
    save.assert_not_called()


def test_mime_mismatch_and_small_images_are_rejected(monkeypatch):
    enricher = _enricher()
    save = Mock(side_effect=AssertionError("invalid candidate must not be persisted"))
    monkeypatch.setattr(enricher, "save_validated_image", save)

    mismatch_fetch = Mock(return_value=(_image_bytes("PNG"), "image/jpeg"))
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", mismatch_fetch)
    assert enricher.process_candidate(SimpleNamespace(id=7), "https://images.example/wrong.jpg") is None

    small_fetch = Mock(return_value=(_image_bytes(size=(100, 100)), "image/jpeg"))
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", small_fetch)
    assert enricher.process_candidate(SimpleNamespace(id=7), "https://images.example/small.jpg") is None

    mismatch_fetch.assert_called_once()
    small_fetch.assert_called_once()
    save.assert_not_called()
