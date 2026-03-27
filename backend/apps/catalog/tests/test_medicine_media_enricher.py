import pytest
from unittest.mock import patch, MagicMock
from django.core.files.base import ContentFile
from apps.catalog.models import MedicineProduct, MedicineProductImage
from apps.catalog.services.medicine_media_enricher import MedicineMediaEnricher

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

    @patch('apps.catalog.services.medicine_media_enricher.httpx.Client.stream')
    def test_validate_image_too_small(self, mock_stream, enricher):
        # Create a tiny 100x100 image
        from PIL import Image
        import io
        img = Image.new('RGB', (100, 100))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_bytes = img_byte_arr.getvalue()
        
        mock_context = MagicMock()
        mock_response = MagicMock()
        mock_response.headers = {"Content-Length": str(len(img_bytes))}
        mock_response.content = img_bytes
        mock_context.__enter__.return_value = mock_response
        mock_stream.return_value = mock_context
        
        is_valid = enricher.validate_image("http://example.com/small.jpg")
        assert is_valid is False

    @patch('apps.catalog.services.medicine_media_enricher.httpx.Client.stream')
    def test_validate_image_ok(self, mock_stream, enricher):
        # Create a 500x500 image (above min width 400)
        from PIL import Image
        import io
        img = Image.new('RGB', (500, 500))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_bytes = img_byte_arr.getvalue()
        
        mock_context = MagicMock()
        mock_response = MagicMock()
        mock_response.headers = {"Content-Length": str(len(img_bytes))}
        mock_response.content = img_bytes
        mock_context.__enter__.return_value = mock_response
        mock_stream.return_value = mock_context
        
        is_valid = enricher.validate_image("http://example.com/ok.jpg")
        assert is_valid is True

    @patch('apps.catalog.services.medicine_media_enricher.httpx.Client.get')
    def test_download_and_save_creates_record(self, mock_get, enricher, medicine_product):
        mock_response = MagicMock()
        mock_response.content = b"fake_image_data"
        mock_get.return_value = mock_response
        
        image = enricher.download_and_save(medicine_product, "http://example.com/test.jpg")
        
        assert image is not None
        assert image.product == medicine_product
        assert image.image_url == "http://example.com/test.jpg"
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
