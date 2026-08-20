from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from apps.ai.models import AIProcessingStatus
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.media_processor import R2MediaProcessor
from apps.recommendations.services import safe_image_fetcher


def _image_bytes(image_format: str = "PNG", size: tuple[int, int] = (32, 24)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size=size, color=(20, 40, 60)).save(output, image_format)
    return output.getvalue()


def _processor(*, cdn_url: str = "https://cdn.example.test") -> R2MediaProcessor:
    processor = R2MediaProcessor.__new__(R2MediaProcessor)
    processor.s3 = Mock()
    processor.bucket = "media"
    processor.cdn_url = cdn_url
    return processor


def test_external_image_uses_hardened_fetcher(monkeypatch):
    processor = _processor()
    image_data = _image_bytes()
    fetch = Mock(return_value=(image_data, "image/png"))
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", fetch)

    result = processor.get_image_for_analysis("https://images.example.test/photo.png")

    fetch.assert_called_once_with("https://images.example.test/photo.png")
    processor.s3.get_object.assert_not_called()
    assert result["base64"].startswith("data:image/jpeg;base64,")
    assert result["original_format"] == "PNG"
    assert result["dimensions"] == (32, 24)


def test_private_external_url_returns_safe_error(monkeypatch):
    processor = _processor()
    fetch = Mock(side_effect=safe_image_fetcher.UnsafeImageURLError())
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", fetch)

    result = processor.get_image_for_analysis("http://169.254.169.254/latest/meta-data")

    assert result == {
        "url": "http://169.254.169.254/latest/meta-data",
        "base64": None,
        "error": "unsafe_image_url",
    }


def test_cdn_hostname_prefix_spoof_is_not_treated_as_r2(monkeypatch):
    processor = _processor(cdn_url="https://cdn.example.test")
    image_data = _image_bytes("JPEG")
    fetch = Mock(return_value=(image_data, "image/jpeg"))
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", fetch)
    spoofed_url = "https://cdn.example.test.evil.invalid/products/a.jpg"

    result = processor.get_image_for_analysis(spoofed_url)

    fetch.assert_called_once_with(spoofed_url)
    processor.s3.get_object.assert_not_called()
    assert result.get("error") is None


def test_empty_cdn_url_does_not_capture_external_urls(monkeypatch):
    processor = _processor(cdn_url="")
    image_data = _image_bytes("JPEG")
    fetch = Mock(return_value=(image_data, "image/jpeg"))
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", fetch)

    result = processor.get_image_for_analysis("https://images.example.test/a.jpg")

    fetch.assert_called_once_with("https://images.example.test/a.jpg")
    processor.s3.get_object.assert_not_called()
    assert result.get("error") is None


def test_r2_image_keeps_direct_object_access_and_bounded_read(monkeypatch):
    processor = _processor()
    image_data = _image_bytes("WEBP")
    body = Mock()
    body.read.return_value = image_data
    processor.s3.get_object.return_value = {
        "Body": body,
        "ContentLength": len(image_data),
        "ContentType": "image/webp",
    }
    fetch = Mock(side_effect=AssertionError("R2 images must not use public fetch"))
    monkeypatch.setattr(safe_image_fetcher, "fetch_public_image_bytes", fetch)

    result = processor.get_image_for_analysis(
        "https://cdn.example.test/products/original/a.webp"
    )

    processor.s3.get_object.assert_called_once_with(
        Bucket="media", Key="products/original/a.webp"
    )
    body.read.assert_called_once_with(safe_image_fetcher.MAX_IMAGE_BYTES + 1)
    fetch.assert_not_called()
    assert result["original_format"] == "WEBP"


def test_r2_declared_oversize_is_rejected_before_body_read():
    processor = _processor()
    body = Mock()
    processor.s3.get_object.return_value = {
        "Body": body,
        "ContentLength": safe_image_fetcher.MAX_IMAGE_BYTES + 1,
        "ContentType": "image/jpeg",
    }

    result = processor.get_image_for_analysis(
        "https://cdn.example.test/products/original/huge.jpg"
    )

    body.read.assert_not_called()
    assert result["error"] == "image_too_large"


def test_unexpected_storage_error_is_not_exposed():
    processor = _processor()
    processor.s3.get_object.side_effect = RuntimeError("secret upstream details")

    result = processor.get_image_for_analysis(
        "https://cdn.example.test/products/original/a.jpg"
    )

    assert result["error"] == "image_processing_failed"
    assert "secret" not in result["error"]


def test_external_decoded_dimensions_are_bounded(monkeypatch):
    processor = _processor()
    image_data = _image_bytes(size=(safe_image_fetcher.MAX_IMAGE_SIDE + 1, 1))
    monkeypatch.setattr(
        safe_image_fetcher,
        "fetch_public_image_bytes",
        Mock(return_value=(image_data, "image/png")),
    )

    result = processor.get_image_for_analysis("https://images.example.test/wide.png")

    assert result["error"] == "image_too_large"


def _generator_for_orchestration(monkeypatch):
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.llm = SimpleNamespace(
        model="test-model",
        analyze_images=Mock(
            return_value={"content": {"summary": "should not be called"}}
        ),
        generate_content=Mock(
            return_value={
                "content": {"ru": {}, "en": {}},
                "tokens": 0,
                "cost_usd": 0,
                "processing_time_ms": 0,
            }
        ),
    )
    generator.media_processor = SimpleNamespace(
        get_product_images_batch=Mock(
            return_value=[{"url": "https://images.example.test/book.jpg"}]
        )
    )
    generator._collect_input_data = Mock(return_value={})
    generator._get_product_image_urls = Mock(
        return_value=["https://images.example.test/book.jpg"]
    )
    generator._get_system_prompt = Mock(return_value="system")
    generator._construct_user_prompt = Mock(return_value="user")
    generator._validate_generated_content = Mock()
    generator._parse_and_save_results = Mock()
    generator._check_needs_moderation = Mock(return_value=False)

    product = SimpleNamespace(id=7, product_type="books", category=None)
    log_entry = SimpleNamespace(
        input_data={},
        input_images_urls=[],
        image_analysis={},
        raw_llm_response={},
        tokens_used=0,
        cost_usd=0,
        processing_time_ms=0,
        completed_at=None,
        status=AIProcessingStatus.PROCESSING,
        save=Mock(),
    )
    monkeypatch.setattr(
        "apps.ai.services.content_generator.Product.objects.get",
        Mock(return_value=product),
    )
    monkeypatch.setattr(
        "apps.ai.services.content_generator.AIProcessingLog.objects.create",
        Mock(return_value=log_entry),
    )
    return generator


@pytest.mark.parametrize(
    "options",
    [
        {
            "generate_description": True,
            "categorize": True,
            "analyze_images": False,
            "use_images": True,
            "force": True,
        },
        {
            "generate_description": True,
            "categorize": True,
            "analyze_images": True,
            "use_images": False,
            "force": True,
        },
    ],
)
def test_explicit_false_image_option_prevents_vision(monkeypatch, options):
    generator = _generator_for_orchestration(monkeypatch)

    generator.process_product(product_id=7, options=options)

    generator._get_product_image_urls.assert_not_called()
    generator.media_processor.get_product_images_batch.assert_not_called()
    generator.llm.analyze_images.assert_not_called()
