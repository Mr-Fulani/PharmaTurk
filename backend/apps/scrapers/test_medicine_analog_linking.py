import pytest
from decimal import Decimal
from types import SimpleNamespace
from rest_framework.test import APIRequestFactory

from apps.catalog.currency_models import GlobalCurrencySettings
from apps.catalog.models import MedicineAnalog, Product
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.services import ScraperIntegrationService


def _analog_stats_session():
    return SimpleNamespace(
        analogs_found=0,
        analog_links_saved=0,
        analog_stubs_created=0,
        analog_stubs_upgraded=0,
        analog_errors=0,
    )


def test_explicit_analog_without_codes_creates_stub_and_updates_stats(monkeypatch):
    service = ScraperIntegrationService.__new__(ScraperIntegrationService)
    service.logger = SimpleNamespace(exception=lambda *args, **kwargs: None)
    source_product = SimpleNamespace(name="SOURCE", product_type="medicines")
    medicine = SimpleNamespace(active_ingredient="", atc_code="")
    analog_ref = SimpleNamespace()
    created_product = SimpleNamespace(product_type="medicines")
    session = _analog_stats_session()
    captured = {}

    monkeypatch.setattr(service, "_get_medicine_product", lambda _product: medicine)
    monkeypatch.setattr(
        service,
        "_upsert_medicine_analog_reference",
        lambda *args, **kwargs: analog_ref,
    )
    monkeypatch.setattr(
        service,
        "_find_existing_medicine_analog_product",
        lambda **kwargs: None,
    )

    def fake_create(create_session, stub):
        captured["session"] = create_session
        captured["stub"] = stub
        return "created", created_product

    monkeypatch.setattr(service, "_create_new_product", fake_create)
    monkeypatch.setattr(
        service,
        "_link_medicine_analog_reference",
        lambda *args, **kwargs: captured.setdefault("linked", True),
    )
    scraped = ScrapedProduct(
        name="SOURCE",
        source="ilacfiyati",
        category="Medicines",
        analogs=[
            {
                "name": "ANALOG WITHOUT CODES",
                "url": "https://ilacfiyati.com/ilaclar/analog-without-codes",
                "external_id": "analog-without-codes",
                "source_tab": "Eşdeğeri",
            }
        ],
    )

    service._process_medicine_analogs(source_product, scraped, session)

    assert captured["session"] is session
    assert captured["stub"].attributes["is_stub"] is True
    assert captured["stub"].attributes["active_ingredient"] == ""
    assert captured["stub"].attributes["atc_code"] == ""
    assert captured["linked"] is True
    assert session.analogs_found == 1
    assert session.analog_links_saved == 1
    assert session.analog_stubs_created == 1
    assert session.analog_errors == 0


def test_analog_tab_fetch_errors_are_counted_without_dropping_main_product():
    service = ScraperIntegrationService.__new__(ScraperIntegrationService)
    session = _analog_stats_session()
    scraped = ScrapedProduct(name="SOURCE", source="ilacfiyati")
    scraped.analog_fetch_errors = 2

    service._process_medicine_analogs(SimpleNamespace(), scraped, session)

    assert session.analog_errors == 2
    assert session.analogs_found == 0


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
def test_explicit_analog_is_linked_without_active_ingredient_or_atc():
    service = ScraperIntegrationService()
    source_product = Product.objects.create(
        name="SOURCE WITHOUT CODES",
        slug="source-without-codes",
        product_type="medicines",
        external_id="source-without-codes",
        external_data={},
    )
    source_medicine = service._get_medicine_product(source_product)
    analog_product = Product.objects.create(
        name="EXPLICIT ANALOG WITHOUT CODES",
        slug="explicit-analog-without-codes",
        product_type="medicines",
        external_id="explicit-analog-without-codes",
        external_data={},
    )
    analog_medicine = service._get_medicine_product(analog_product)
    session = _analog_stats_session()
    scraped = ScrapedProduct(
        name=source_product.name,
        source="ilacfiyati",
        analogs=[
            {
                "name": analog_product.name,
                "url": "https://ilacfiyati.com/ilaclar/explicit-analog-without-codes",
                "external_id": analog_product.external_id,
                "source_tab": "Eşdeğeri",
            }
        ],
    )

    service._process_medicine_analogs(source_product, scraped, session=session)

    assert MedicineAnalog.objects.filter(
        product=source_medicine,
        analog_product=analog_medicine,
        external_id=analog_product.external_id,
    ).exists()
    assert session.analogs_found == 1
    assert session.analog_links_saved == 1
    assert session.analog_stubs_created == 0
    assert session.analog_errors == 0


@pytest.mark.django_db
def test_api_product_conflict_still_saves_explicit_analogs():
    service = ScraperIntegrationService()
    api_product = Product.objects.create(
        name="API SOURCE",
        slug="api-source",
        product_type="medicines",
        external_id="api-source",
        external_data={"source": "api"},
    )
    source_medicine = service._get_medicine_product(api_product)
    analog_product = Product.objects.create(
        name="API EXPLICIT ANALOG",
        slug="api-explicit-analog",
        product_type="medicines",
        external_id="api-explicit-analog",
        external_data={},
    )
    analog_medicine = service._get_medicine_product(analog_product)
    session = _analog_stats_session()
    scraped = ScrapedProduct(
        name=api_product.name,
        external_id=api_product.external_id,
        source="ilacfiyati",
        analogs=[
            {
                "name": analog_product.name,
                "url": "https://ilacfiyati.com/ilaclar/api-explicit-analog",
                "external_id": analog_product.external_id,
                "source_tab": "SGK Eşdeğeri",
            }
        ],
    )

    action, product = service._process_single_product(session, scraped)

    assert action == "updated"
    assert product.pk == api_product.pk
    assert MedicineAnalog.objects.filter(
        product=source_medicine,
        analog_product=analog_medicine,
    ).exists()
    assert session.analogs_found == 1
    assert session.analog_links_saved == 1


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
def test_medicine_analogs_api_applies_product_markup_to_public_prices():
    from apps.catalog.views import MedicineProductViewSet

    settings = GlobalCurrencySettings.load()
    settings.default_margin_percentage = Decimal("20")
    settings.save()

    service = ScraperIntegrationService()
    source_base = Product.objects.create(
        name="SOURCE WITH MARKUP",
        slug="source-with-markup",
        product_type="medicines",
        price=Decimal("100"),
        currency="TRY",
        external_data={},
    )
    source = service._get_medicine_product(source_base)
    analog_base = Product.objects.create(
        name="ANALOG WITH MARKUP",
        slug="analog-with-markup",
        product_type="medicines",
        price=Decimal("80"),
        old_price=Decimal("90"),
        currency="TRY",
        external_id="analog-with-markup",
        external_data={},
        is_available=True,
    )
    analog = service._get_medicine_product(analog_base)
    MedicineAnalog.objects.create(
        product=source,
        analog_product=analog,
        name=analog.name,
        external_id=analog.external_id,
        source="ilacfiyati",
    )

    request = APIRequestFactory().get("/", HTTP_X_CURRENCY="TRY")
    response = MedicineProductViewSet.as_view({"get": "analogs"})(
        request, slug=source.slug
    )

    assert response.status_code == 200
    result = response.data["results"][0]
    assert result["price"] == 96.0
    assert result["old_price"] == 108.0
    assert result["saving_amount"] == 24.0
    assert result["saving_percent"] == 20


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
