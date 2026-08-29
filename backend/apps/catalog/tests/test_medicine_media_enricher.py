import pytest
from unittest.mock import patch, MagicMock
from django.core.cache import cache
from apps.catalog.models import (
    MediaEnrichmentStatus,
    MedicineProduct,
    MedicineProductImage,
)
from apps.catalog.services.medicine_media_enricher import (
    FetchedMedicineImage,
    MEDIA_ENRICHMENT_MAX_IMAGES,
    MEDIA_ENRICHMENT_RECENT_NO_RESULT,
    MedicineMediaEnricher,
)
from apps.catalog.tasks import enrich_medicine_media

@pytest.fixture
def medicine_product(db):
    product = MedicineProduct.objects.create(
        name="ARYOSEVEN",
        slug="aryoseven",
        active_ingredient="Eptacog alfa (aktive edilmiş) - Faktör VIIa",
        barcode="8699586773133",
        price=100.0,
        is_active=True
    )
    return product

@pytest.fixture
def enricher():
    return MedicineMediaEnricher()

@pytest.mark.django_db
class TestMedicineMediaEnricher:
    
    def test_build_queries_uses_name_and_ingredient(self, enricher, medicine_product):
        queries = enricher.build_search_queries(medicine_product)
        assert len(queries) >= 2
        assert "ARYOSEVEN Eptacog alfa (aktive edilmiş) - Faktör VIIa" in queries
        assert "ARYOSEVEN" in queries
        
    @patch('apps.catalog.services.medicine_media_enricher.httpx.Client.get')
    def test_open_food_facts_returns_urls(self, mock_get, enricher, medicine_product):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": 1,
            "product": {
                "image_url": "https://example.com/front.jpg",
                "image_front_url": "https://example.com/front.jpg"
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        urls = enricher.open_food_facts_client.fetch_images(medicine_product.barcode)
        assert len(urls) == 1
        assert urls[0] == "https://example.com/front.jpg"
        
    def test_serper_skipped_when_no_api_key(self, enricher, settings, medicine_product):
        settings.SERPER_API_KEY = ""
        enricher.serper_client.api_key = ""
        
        with patch('apps.catalog.services.medicine_media_enricher.SerperImageSearchClient.fetch_images') as mock_fetch:
            urls = enricher.fetch_candidates(medicine_product)
            mock_fetch.assert_not_called()

    @patch('apps.catalog.services.medicine_media_enricher.safe_image_fetcher.fetch_public_image_bytes')
    def test_validate_image_too_small(self, mock_fetch, enricher):
        # Create a tiny 100x100 image
        from PIL import Image
        import io
        img = Image.new('RGB', (100, 100))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_bytes = img_byte_arr.getvalue()
        
        mock_fetch.return_value = (img_bytes, "image/jpeg")

        fetched = enricher.fetch_validated_image("https://example.com/small.jpg")
        assert fetched is None

    @patch('apps.catalog.services.medicine_media_enricher.safe_image_fetcher.fetch_public_image_bytes')
    def test_validate_image_ok(self, mock_fetch, enricher):
        # Create a 500x500 image (above min width 400)
        from PIL import Image
        import io
        img = Image.new('RGB', (500, 500))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_bytes = img_byte_arr.getvalue()
        
        mock_fetch.return_value = (img_bytes, "image/jpeg")

        fetched = enricher.fetch_validated_image("https://example.com/ok.jpg")
        assert fetched is not None
        assert fetched.content == img_bytes
        assert fetched.extension == ".jpg"
        assert (fetched.width, fetched.height) == (500, 500)

    def test_download_and_save_creates_record(self, enricher, medicine_product):
        from PIL import Image
        import io

        output = io.BytesIO()
        Image.new('RGB', (500, 500)).save(output, format='JPEG')
        image_data = output.getvalue()

        image = enricher.save_validated_image(
            medicine_product,
            "https://example.com/test.jpg",
            FetchedMedicineImage(
                content=image_data,
                extension=".jpg",
                width=500,
                height=500,
            ),
        )
        
        assert image is not None
        assert image.product == medicine_product
        assert image.image_url == "https://example.com/test.jpg"
        assert image.is_main is True
        assert MedicineProductImage.objects.count() == 1

    def test_enrich_skips_product_with_enough_photos(self, enricher, medicine_product):
        # Add 3 fake photos
        for i in range(3):
            MedicineProductImage.objects.create(
                product=medicine_product,
                image_url=f"http://example.com/{i}.jpg"
            )
            
        with patch.object(enricher, 'fetch_candidates') as mock_fetch:
            added = enricher.enrich(medicine_product, max_images=3)
            assert added == 0
            mock_fetch.assert_not_called()

        medicine_product.refresh_from_db()
        assert medicine_product.media_enrichment_status == MediaEnrichmentStatus.COMPLETED
        assert medicine_product.media_enrichment_last_at is not None
        assert medicine_product.media_enrichment_error == MEDIA_ENRICHMENT_MAX_IMAGES

    def test_enrich_cached_no_result_finishes_processing_state(
        self,
        enricher,
        medicine_product,
    ):
        cache.set(f"medicine_media_enrich_failed_{medicine_product.pk}", True, 60)
        medicine_product.media_enrichment_status = MediaEnrichmentStatus.PROCESSING
        medicine_product.save(update_fields=["media_enrichment_status"])

        with patch.object(enricher, "fetch_candidates") as mock_fetch:
            added = enricher.enrich(medicine_product, max_images=3)

        assert added == 0
        mock_fetch.assert_not_called()
        medicine_product.refresh_from_db()
        assert medicine_product.media_enrichment_status == MediaEnrichmentStatus.COMPLETED
        assert medicine_product.media_enrichment_last_at is not None
        assert medicine_product.media_enrichment_error == MEDIA_ENRICHMENT_RECENT_NO_RESULT

    def test_task_reports_error_when_every_product_fails(
        self,
        medicine_product,
        monkeypatch,
    ):
        def fail_enrichment(_enricher, product, *_args, **_kwargs):
            product.media_enrichment_status = MediaEnrichmentStatus.FAILED
            product.media_enrichment_error = "source timeout"
            product.save(
                update_fields=["media_enrichment_status", "media_enrichment_error"]
            )
            return 0

        monkeypatch.setattr(MedicineMediaEnricher, "enrich", fail_enrichment)

        result = enrich_medicine_media.run(product_ids=[medicine_product.pk])

        assert result == {
            "status": "error",
            "products_processed": 1,
            "images_added": 0,
            "errors": 1,
            "skipped": 0,
            "no_results": 0,
        }
