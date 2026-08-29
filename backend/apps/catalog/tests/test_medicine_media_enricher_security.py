"""DB-free security regressions for manually requested image enrichment."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image

from apps.catalog.services.medicine_media_enricher import (
    MedicineImageSearchCandidate,
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
    stage = Mock(return_value=saved_record)
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", fetch)
    monkeypatch.setattr(enricher, "stage_validated_candidate", stage)
    product = SimpleNamespace(id=7)
    url = "https://images.example.test/medicine.jpg"
    candidate = MedicineImageSearchCandidate(url=url, source="serper", query="medicine")

    requester = object()
    result = enricher.process_candidate(product, candidate, requested_by=requester)

    assert result is saved_record
    fetch.assert_called_once_with(url)
    stage.assert_called_once()
    saved_product, saved_candidate, fetched = stage.call_args.args
    assert saved_product is product
    assert saved_candidate is candidate
    assert fetched.content is image_data
    assert fetched.extension == ".jpg"
    assert (fetched.width, fetched.height) == (500, 500)
    assert stage.call_args.kwargs == {"requested_by": requester}


def test_private_or_rebinding_target_is_rejected_before_persistence(monkeypatch, caplog):
    enricher = _enricher()
    fetch = Mock(side_effect=safe_image_fetcher.UnsafeImageURLError())
    stage = Mock(side_effect=AssertionError("unsafe candidate must not be persisted"))
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", fetch)
    monkeypatch.setattr(enricher, "stage_validated_candidate", stage)
    product = SimpleNamespace(id=7)
    secret = "signed-query-value"
    url = f"http://169.254.169.254/latest/meta-data?token={secret}"

    candidate = MedicineImageSearchCandidate(url=url, source="serper")
    assert enricher.process_candidate(product, candidate, requested_by=object()) is None

    fetch.assert_called_once_with(url)
    stage.assert_not_called()
    assert secret not in caplog.text


def test_persisted_source_url_drops_query_and_fragment():
    source = "https://cdn.example.test/images/medicine.jpg?token=secret#fragment"

    assert _query_free_source_url(source) == "https://cdn.example.test/images/medicine.jpg"


def test_declared_or_streamed_oversize_is_rejected_before_persistence(monkeypatch):
    enricher = _enricher()
    fetch = Mock(side_effect=safe_image_fetcher.ImageTooLargeError())
    stage = Mock(side_effect=AssertionError("oversized candidate must not be persisted"))
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", fetch)
    monkeypatch.setattr(enricher, "stage_validated_candidate", stage)

    candidate = MedicineImageSearchCandidate(
        url="https://images.example/huge.jpg",
        source="serper",
    )
    assert (
        enricher.process_candidate(
            SimpleNamespace(id=7),
            candidate,
            requested_by=object(),
        )
        is None
    )

    fetch.assert_called_once()
    stage.assert_not_called()


def test_mime_mismatch_and_small_images_are_rejected(monkeypatch):
    enricher = _enricher()
    stage = Mock(side_effect=AssertionError("invalid candidate must not be persisted"))
    monkeypatch.setattr(enricher, "stage_validated_candidate", stage)

    mismatch_fetch = Mock(return_value=(_image_bytes("PNG"), "image/jpeg"))
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", mismatch_fetch)
    mismatch_candidate = MedicineImageSearchCandidate(
        url="https://images.example/wrong.jpg",
        source="serper",
    )
    assert (
        enricher.process_candidate(
            SimpleNamespace(id=7),
            mismatch_candidate,
            requested_by=object(),
        )
        is None
    )

    small_fetch = Mock(return_value=(_image_bytes(size=(100, 100)), "image/jpeg"))
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", small_fetch)
    small_candidate = MedicineImageSearchCandidate(
        url="https://images.example/small.jpg",
        source="serper",
    )
    assert (
        enricher.process_candidate(
            SimpleNamespace(id=7),
            small_candidate,
            requested_by=object(),
        )
        is None
    )

    mismatch_fetch.assert_called_once()
    small_fetch.assert_called_once()
    stage.assert_not_called()
