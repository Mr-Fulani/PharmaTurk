"""Новое лекарство IlacFiyati, похожее на больничное, отмечается само; ручная отметка главнее (TD-047)."""

import pytest

from apps.catalog.models import Category, CategoryType, MedicineProduct, Product
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScraperConfig, ScrapingSession
from apps.scrapers.services import ScraperIntegrationService

INFUSION = "POLIFLEKS %5 DEKSTROZ 500 ML SOL. SETLI"


@pytest.fixture
def run(db, monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    kind, _ = CategoryType.objects.get_or_create(slug="medicines", defaults={"name": "Medicine"})
    root, _ = Category.objects.update_or_create(
        slug="medicines", defaults={"name": "Медицина", "category_type": kind, "parent": None},
    )
    config = ScraperConfig.objects.create(
        name="hospital-flag-ilacfiyati", parser_class="ilacfiyati",
        base_url="https://ilacfiyati.com", default_category=root,
    )
    return ScrapingSession.objects.create(
        scraper_config=config, start_url="https://ilacfiyati.com/ilaclar", max_pages=1, max_products=10,
    )


def scraped(name, slug, atc, barcode, **attributes):
    return ScrapedProduct(
        name=name, source="ilacfiyati", category="medicines", external_id=slug,
        url=f"https://ilacfiyati.com/ilaclar/{slug}", price=100, currency="TRY",
        is_available=True, stock_quantity=None, barcode=barcode,
        attributes={"atc_code": atc, "barcode": barcode, **attributes},
    )


def medicine(slug):
    return MedicineProduct.objects.get(base_product__external_id=slug)


def test_new_hospital_medicine_is_flagged_and_ordinary_is_not(run):
    service = ScraperIntegrationService()
    result = service._process_scraped_products(run, [
        scraped(INFUSION, "polifleks-5-dekstroz", "B05BA03", "8699000000011"),
        scraped("PAROL 500 MG 20 TABLET", "parol-500-mg", "N02BE01", "8699000000028"),
        scraped("DODEX 1000 MCG/ML 5 AMPUL", "dodex-ampul", "B03BA01", "8699000000035"),
    ])

    assert result["created"] == 3 and result["errors"] == 0
    assert medicine("polifleks-5-dekstroz").is_hospital is True
    assert medicine("parol-500-mg").is_hospital is False
    assert medicine("dodex-ampul").is_hospital is False
    # Цена и показ не меняются: отметка только прячет цену на сайте.
    base = Product.objects.get(external_id="polifleks-5-dekstroz")
    assert base.price == 100 and base.is_active


def test_rescrape_keeps_manual_flag_both_ways(run):
    service = ScraperIntegrationService()
    items = [
        scraped(INFUSION, "polifleks-5-dekstroz", "B05BA03", "8699000000011"),
        scraped("PAROL 500 MG 20 TABLET", "parol-500-mg", "N02BE01", "8699000000028"),
    ]
    service._process_scraped_products(run, items)
    # Владелец снял отметку у раствора и поставил у таблеток.
    MedicineProduct.objects.filter(pk=medicine("polifleks-5-dekstroz").pk).update(is_hospital=False)
    MedicineProduct.objects.filter(pk=medicine("parol-500-mg").pk).update(is_hospital=True)

    for item in items:
        item.price = 150
    result = service._process_scraped_products(run, items)

    assert result["created"] == 0 and result["errors"] == 0
    assert Product.objects.get(external_id="polifleks-5-dekstroz").price == 150
    assert medicine("polifleks-5-dekstroz").is_hospital is False
    assert medicine("parol-500-mg").is_hospital is True


def test_analog_stub_is_judged_by_name_until_it_gets_its_own_card(run):
    service = ScraperIntegrationService()
    # ATC заглушки унаследован от родителя-раствора; по названию это не раствор.
    service._process_scraped_products(run, [
        scraped("ISOTEN 20 ML 5 FLAKON", "isoten-flakon", "B05BA03", "8699000000042", is_stub=True),
        scraped("NEOFLEKS %5 DEKSTROZ 250 ML SETSIZ", "neofleks-5-dekstroz", "B05BA03", "8699000000059", is_stub=True),
    ])
    assert medicine("isoten-flakon").is_hospital is False
    assert medicine("neofleks-5-dekstroz").is_hospital is True

    # Заглушка получила свою карточку с кодом ATC диализа — для правила это новое лекарство.
    result = service._process_scraped_products(run, [
        scraped("ISOTEN 20 ML 5 FLAKON", "isoten-flakon", "B05ZB", "8699000000042"),
    ])
    assert result["updated"] == 1 and result["errors"] == 0
    assert medicine("isoten-flakon").is_hospital is True
