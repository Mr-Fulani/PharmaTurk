import pytest
from rest_framework.test import APIRequestFactory

from apps.catalog.models import MedicineAnalog, Product
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.services import ScraperIntegrationService


@pytest.mark.django_db
def test_medicine_analogs_are_saved_and_matched_by_barcode():
    service = ScraperIntegrationService()
    product = Product.objects.create(
        name="ZOVIRAX 5% KREM",
        slug="zovirax-5-krem",
        product_type="medicines",
        external_id="zovirax-5-krem",
        external_data={},
    )
    medicine = service._get_medicine_product(product)
    medicine.active_ingredient = "Asiklovir"
    medicine.atc_code = "D06BB03"
    medicine.save()

    analog_product = Product.objects.create(
        name="ASIVIRAL 400 MG 25 TABLET",
        slug="asiviral-400-mg-25-tablet",
        product_type="medicines",
        external_id="asiviral-400-mg-25-tablet",
        external_data={},
    )
    analog_medicine = service._get_medicine_product(analog_product)
    analog_medicine.barcode = "8699546090114"
    analog_medicine.save()

    scraped = ScrapedProduct(
        name=product.name,
        source="ilacfiyati",
        analogs=[
            {
                "name": "ASIVIRAL 400 MG 25 TABLET",
                "url": "https://ilacfiyati.com/ilaclar/asiviral-400-mg-25-tablet",
                "external_id": "asiviral-400-mg-25-tablet",
                "barcode": "8699546090114",
                "atc_code": "D06BB03",
                "sgk_equivalent_code": "E007D",
            }
        ],
    )

    service._process_medicine_analogs(product, scraped, session=None)

    assert MedicineAnalog.objects.filter(
        product=medicine,
        analog_product=analog_medicine,
        name="ASIVIRAL 400 MG 25 TABLET",
        barcode="8699546090114",
        atc_code="D06BB03",
        sgk_equivalent_code="E007D",
        external_id="asiviral-400-mg-25-tablet",
        source="ilacfiyati",
    ).exists()

    analog_medicine.refresh_from_db()
    assert analog_medicine.active_ingredient == "Asiklovir"
    assert analog_medicine.atc_code == "D06BB03"
    assert analog_medicine.sgk_equivalent_code == "E007D"


@pytest.mark.django_db
def test_medicine_analogs_api_uses_explicit_analog_rows_without_active_ingredient():
    from apps.catalog.views import MedicineProductViewSet

    service = ScraperIntegrationService()
    product = Product.objects.create(
        name="SOURCE DRUG",
        slug="source-drug",
        product_type="medicines",
        external_data={},
    )
    medicine = service._get_medicine_product(product)

    analog_product = Product.objects.create(
        name="EXPLICIT ANALOG",
        slug="explicit-analog",
        product_type="medicines",
        external_id="explicit-analog",
        external_data={},
        is_available=True,
    )
    analog_medicine = service._get_medicine_product(analog_product)
    analog_medicine.barcode = "8699546090114"
    analog_medicine.save()

    MedicineAnalog.objects.create(
        product=medicine,
        analog_product=analog_medicine,
        name="EXPLICIT ANALOG",
        barcode="8699546090114",
        external_id="explicit-analog",
        source="ilacfiyati",
        source_tab="Eşdeğeri",
    )

    request = APIRequestFactory().get("/")
    response = MedicineProductViewSet.as_view({"get": "analogs"})(request, slug=medicine.slug)

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["slug"] == analog_medicine.slug


@pytest.mark.django_db
def test_medicine_analogs_api_sorts_by_price_and_returns_savings():
    from apps.catalog.views import MedicineProductViewSet

    service = ScraperIntegrationService()
    product = Product.objects.create(
        name="SOURCE DRUG",
        slug="source-drug-priced",
        product_type="medicines",
        price=100,
        currency="TRY",
        external_data={},
    )
    medicine = service._get_medicine_product(product)

    expensive_product = Product.objects.create(
        name="EXPENSIVE ANALOG",
        slug="expensive-analog",
        product_type="medicines",
        price=80,
        currency="TRY",
        external_id="expensive-analog",
        external_data={},
        is_available=True,
    )
    expensive = service._get_medicine_product(expensive_product)

    cheap_product = Product.objects.create(
        name="CHEAP ANALOG",
        slug="cheap-analog",
        product_type="medicines",
        price=60,
        currency="TRY",
        external_id="cheap-analog",
        external_data={},
        is_available=True,
    )
    cheap = service._get_medicine_product(cheap_product)

    MedicineAnalog.objects.create(
        product=medicine,
        analog_product=expensive,
        name=expensive.name,
        external_id=expensive.external_id,
        source="ilacfiyati",
    )
    MedicineAnalog.objects.create(
        product=medicine,
        analog_product=cheap,
        name=cheap.name,
        external_id=cheap.external_id,
        source="ilacfiyati",
    )

    request = APIRequestFactory().get("/", HTTP_X_CURRENCY="TRY")
    response = MedicineProductViewSet.as_view({"get": "analogs"})(request, slug=medicine.slug)

    assert response.status_code == 200
    assert [item["slug"] for item in response.data["results"]] == [cheap.slug, expensive.slug]
    assert response.data["results"][0]["saving_percent"] > response.data["results"][1]["saving_percent"] > 0


@pytest.mark.django_db
def test_medicine_analogs_api_excludes_stub_products():
    from apps.catalog.views import MedicineProductViewSet

    service = ScraperIntegrationService()
    product = Product.objects.create(
        name="SOURCE DRUG",
        slug="source-drug-with-stub",
        product_type="medicines",
        price=100,
        currency="TRY",
        external_data={},
    )
    medicine = service._get_medicine_product(product)
    medicine.active_ingredient = "Bilastin"
    medicine.atc_code = "R06AX29"
    medicine.save()

    stub_product = Product.objects.create(
        name="STUB ANALOG",
        slug="stub-analog",
        product_type="medicines",
        external_url="https://ilacfiyati.com/ilaclar/stub-analog",
        external_data={"source": "ilacfiyati", "is_stub": True},
    )
    stub = service._get_medicine_product(stub_product)
    stub.active_ingredient = "Bilastin"
    stub.atc_code = "R06AX29"
    stub.save()

    MedicineAnalog.objects.create(
        product=medicine,
        analog_product=stub,
        name=stub.name,
        external_id="stub-analog",
        source="ilacfiyati",
    )

    request = APIRequestFactory().get("/", HTTP_X_CURRENCY="TRY")
    response = MedicineProductViewSet.as_view({"get": "analogs"})(request, slug=medicine.slug)

    assert response.status_code == 200
    assert response.data["results"] == []


@pytest.mark.django_db
def test_generic_products_api_excludes_medicine_stubs_only():
    from apps.catalog.views import ProductViewSet

    Product.objects.create(
        name="VISIBLE MEDICINE",
        slug="visible-medicine",
        product_type="medicines",
        external_data={"source": "ilacfiyati"},
        is_active=True,
    )
    Product.objects.create(
        name="STUB MEDICINE",
        slug="stub-medicine",
        product_type="medicines",
        external_data={"source": "ilacfiyati", "is_stub": True},
        is_active=True,
    )
    Product.objects.create(
        name="NON MEDICINE WITH SAME FLAG",
        slug="non-medicine-with-same-flag",
        product_type="clothing",
        external_data={"is_stub": True},
        is_active=True,
    )

    request = APIRequestFactory().get("/")
    response = ProductViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200
    names = [item["name"] for item in response.data["results"]]
    assert "VISIBLE MEDICINE" in names
    assert "NON MEDICINE WITH SAME FLAG" in names
    assert "STUB MEDICINE" not in names
