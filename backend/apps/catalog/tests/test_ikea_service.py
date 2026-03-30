import pytest
from unittest.mock import patch, MagicMock
from apps.catalog.services import IkeaService
from apps.catalog.services.ikea_service import extract_ikea_color_from_variant_info
from apps.catalog.models import FurnitureProduct, FurnitureVariant, Brand

@pytest.fixture
def ikea_service(db):
    return IkeaService()

class TestIkeaExtractItemCode:
    """Разбор URL карточки товара ikea.com.tr (без БД)."""

    def test_slug_with_suffix_digits(self):
        url = (
            "https://www.ikea.com.tr/urun/kallax-beyaz-77x147-cm-calisma-masali-unite-80275887"
        )
        assert IkeaService._extract_item_code(url) == "80275887"

    def test_en_product_path(self):
        url = (
            "https://www.ikea.com.tr/en/product/"
            "kivik-tibbleby-beige-grey-5-seat-corner-sofa-39440475"
        )
        assert IkeaService._extract_item_code(url) == "39440475"

    def test_rejects_urun_gruplari(self):
        url = "https://www.ikea.com.tr/urun-gruplari/kallax-serisi"
        assert IkeaService._extract_item_code(url) is None

    def test_rejects_kategori_path(self):
        assert IkeaService._extract_item_code(
            "https://www.ikea.com.tr/kategori/acik-kitapliklar"
        ) is None

    def test_parse_category_list_url_en(self):
        slug, lang = IkeaService.parse_category_list_url(
            "https://www.ikea.com.tr/en/category/four-seats?page=2"
        )
        assert slug == "four-seats"
        assert lang == "en"

    def test_parse_category_list_url_kategori_tr(self):
        slug, lang = IkeaService.parse_category_list_url(
            "https://www.ikea.com.tr/kategori/acik-kitapliklar"
        )
        assert slug == "acik-kitapliklar"
        assert lang == "tr"

    def test_parse_category_list_url_tr_category(self):
        slug, lang = IkeaService.parse_category_list_url(
            "https://www.ikea.com.tr/tr/category/foo-bar"
        )
        assert slug == "foo-bar"
        assert lang == "tr"


@pytest.mark.django_db
class TestIkeaService:
    """variantInfo у IKEA TR бывает list или nested dict — цвет для вариантов и фронта."""

    def test_extract_color_dict_variant_info(self):
        vi = {
            "color": {"name": "Renk", "value": "bej-beyaz"},
            "variant1": {"name": "Ölçü", "value": "120x70 cm"},
        }
        assert extract_ikea_color_from_variant_info(vi) == "bej-beyaz"

    def test_extract_color_list_renk(self):
        assert extract_ikea_color_from_variant_info([{"name": "Renk", "value": "beyaz"}]) == "beyaz"

    @patch('httpx.Client.get')
    def test_fetch_items_calls_api(self, mock_get, ikea_service):
        # Имитируем ответ от httpx
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sprCode": "123", "title": "BILLY"}
        mock_get.return_value = mock_response
        
        result = ikea_service.fetch_items(["123"])
        
        assert len(result) == 1
        assert result[0]["sprCode"] == "123"
        assert mock_get.called

    def test_upsert_creates_objects(self, ikea_service):
        # Структура ответа IKEA Turkey API
        item_data = {
            "sprCode": "90271485",
            "title": "KALLAX",
            "subTitle": "Shelf unit",
            "price": {"sellPrice": 1000},
            "images": [{"code": "IMG1", "rank": 1}],
            "variantInfo": [{"name": "Renk", "value": "White"}],
            "dimensionsDetail": "77x147 cm"
        }
        
        product = ikea_service.upsert_furniture_product(item_data)
        
        assert product is not None
        assert product.external_id == "90271485"
        assert product.name == "KALLAX"
        assert product.brand.name == "IKEA"
        assert product.currency == "TRY"
        
        assert FurnitureProduct.objects.count() == 1
        variant = product.variants.first()
        assert variant.color == "White"
        assert "IMG1" in variant.main_image

    def test_upsert_updates_existing(self, ikea_service):
        # Создаем товар заранее
        Brand.objects.get_or_create(name="IKEA", defaults={"slug": "ikea"})
        initial_product = FurnitureProduct.objects.create(
            external_id="123",
            name="Old Name",
            price=500,
            currency="TRY",
            brand=Brand.objects.get(slug="ikea"),
            slug="ikea-old-123"
        )
        
        item_data = {
            "sprCode": "123",
            "title": "New Name",
            "price": {"sellPrice": 600}
        }
        
        product = ikea_service.upsert_furniture_product(item_data)
        
        assert product.id == initial_product.id
        assert product.price == 600
        assert product.old_price == 500
        assert FurnitureProduct.objects.count() == 1
