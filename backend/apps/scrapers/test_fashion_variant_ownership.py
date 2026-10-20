"""Цвет принадлежит одной карточке: «плывущий» id группы LCW/FLO не плодит дубли."""

import pytest

from apps.catalog.models import Category, ClothingVariant, Product
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScraperConfig, ScrapingSession
from apps.scrapers.services import ScraperIntegrationService

pytestmark = pytest.mark.django_db


def _session():
    category, _ = Category.objects.get_or_create(slug="ownership-clothing", defaults={"name": "Одежда"})
    config = ScraperConfig.objects.create(
        name="ownership-lcw", parser_class="lcw", base_url="https://www.lcw.com", default_category=category,
    )
    return ScrapingSession.objects.create(
        scraper_config=config, start_url="https://www.lcw.com", max_pages=1, max_products=10, status="running",
    ), category


def _product(category, external_id, color_ids):
    product = Product.objects.create(
        name=f"Tişört {external_id}", slug=f"tisort-{external_id}", category=category,
        product_type="clothing", price=100, currency="TRY", external_id=external_id,
        external_url=f"https://www.lcw.com/tisort-o-{color_ids[0]}", external_data={"source": "lcw"},
    )
    for index, color_id in enumerate(color_ids):
        ClothingVariant.objects.create(
            product=product.domain_item, name=f"Цвет {color_id}", color=f"c{color_id}",
            external_id=f"lcw-var-{color_id}", external_url=f"https://www.lcw.com/tisort-o-{color_id}",
            price=100, currency="TRY", sort_order=index, is_active=True, is_available=True,
        )
    return product


def _group(external_id, color_ids):
    return ScrapedProduct(
        name="Tişört", price=100, currency="TRY", source="lcw", external_id=external_id,
        url=f"https://www.lcw.com/tisort-o-{color_ids[0]}",
        attributes={
            "variant_group_id": external_id,
            "fashion_variants": [
                {
                    "external_id": f"lcw-var-{color_id}", "color": f"c{color_id}", "price": 100,
                    "currency": "TRY", "external_url": f"https://www.lcw.com/tisort-o-{color_id}",
                    "sort_order": index, "is_available": True, "stock_quantity": 3,
                }
                for index, color_id in enumerate(color_ids)
            ],
        },
    )


def test_drifted_group_id_updates_the_card_that_owns_its_colors():
    session, category = _session()
    saved = _product(category, "lcw-100", [100, 101])

    # Цвет 100 пропал из ссылок — id группы «уплыл» на 101.
    action, product = ScraperIntegrationService()._process_single_product(
        session, _group("lcw-101", [101, 102]),
    )

    assert action == "updated" and product.pk == saved.pk
    assert Product.objects.filter(product_type="clothing").count() == 1
    variants = dict(saved.domain_item.variants.values_list("external_id", "is_active"))
    # Объединение, а не замена: цвет 100 этой выдачей не снимается.
    assert variants == {"lcw-var-100": True, "lcw-var-101": True, "lcw-var-102": True}


def test_color_owned_by_another_card_is_not_copied():
    session, category = _session()
    owner = _product(category, "lcw-200", [200])
    other = _product(category, "lcw-300", [300])

    ScraperIntegrationService()._process_single_product(session, _group("lcw-300", [300, 200]))

    assert list(other.domain_item.variants.values_list("external_id", flat=True)) == ["lcw-var-300"]
    assert list(owner.domain_item.variants.values_list("external_id", flat=True)) == ["lcw-var-200"]


def test_own_group_still_retires_colors_that_disappeared():
    session, category = _session()
    saved = _product(category, "lcw-400", [400, 401])

    ScraperIntegrationService()._process_single_product(session, _group("lcw-400", [400]))

    variants = dict(saved.domain_item.variants.values_list("external_id", "is_active"))
    assert variants == {"lcw-var-400": True, "lcw-var-401": False}
