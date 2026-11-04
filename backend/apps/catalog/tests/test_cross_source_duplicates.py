"""Одинаковые товары FLO и SuperStep: на сайте одно, более дорогое предложение.

Четыре решения владельца 04.11.2026 (docs/CROSS_SOURCE_DUPLICATES.md):
1. тот же товар — по штрихкодам размеров, запасной признак — бренд + артикул, не по названию;
2. показываем более дорогое, второе скрываем (не удаляем);
3. цены поменялись местами — предложения тоже;
4. у дорогого нет размеров в наличии, а у дешёвого есть — показываем дешёвое.
"""
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import (
    Brand,
    Category,
    ClothingProduct,
    ClothingVariant,
    ClothingVariantSize,
    CrossSourceDuplicate,
    Product,
    ProductSourceOffer,
    ShoeProduct,
    ShoeVariant,
    ShoeVariantSize,
)
from apps.catalog.services.product_card_source_refresh import ProductCardSourceRefreshService, RefreshTarget
from apps.scrapers.base.offers import (
    OfferAvailability,
    OfferCheckError,
    OfferCheckErrorCode,
    OfferCheckResult,
    OfferStockPrecision,
)
from apps.scrapers.parsers.flo import FloParser
from apps.catalog.services import cross_source_duplicates
from apps.catalog.services.cross_source_duplicates import (
    CrossSourceDuplicateService,
    _check_at_seller,
    article_key,
    color_key,
    normalize_gtin,
    resolve_for_products,
    verify_hidden_duplicate,
)
from apps.catalog.services.stale_products import _set_active
from apps.scrapers.parsers.superstep import SuperstepParser
from apps.scrapers.services import ScraperIntegrationService

pytestmark = pytest.mark.django_db

# Один и тот же Nike у двух продавцов: у FLO штрихкоды UPC (12 цифр), у SuperStep — EAN-13.
UPC = ["196968173624", "196968173631", "196968173648"]
EAN = ["0196968173624", "0196968173631", "0196968173648"]


@pytest.fixture
def nike():
    brand, _ = Brand.objects.get_or_create(slug="nike-dups-test", defaults={"name": "Nike"})
    return brand


def _shoe(source, price, *, brand=None, name="Court Borough Low Recraft"):
    domain = ShoeProduct.objects.create(
        name=name,
        slug=f"{source}-shoe-{uuid4().hex[:10]}",
        price=Decimal(price),
        currency="TRY",
        is_available=True,
    )
    domain.refresh_from_db()
    if brand is not None:
        Product.objects.filter(pk=domain.base_product_id).update(brand=brand)
    return domain


def _color(domain, source, price, *, gtins=(), available=True, mpn="", sort_order=0, color="Beyaz"):
    variant = ShoeVariant.objects.create(
        product=domain,
        name="Цвет",
        slug=f"{source}-color-{uuid4().hex[:10]}",
        color=color,
        price=Decimal(price),
        currency="TRY",
        is_available=available,
        external_id=f"{source}-variant-{uuid4().hex[:8]}",
        mpn=mpn,
        sort_order=sort_order,
    )
    for index, code in enumerate(gtins):
        ShoeVariantSize.objects.create(
            variant=variant, size=str(40 + index), is_available=available, gtin=normalize_gtin(code)
        )
    return variant


def _pair(flo_price, superstep_price, *, flo_available=True, superstep_available=True, brand=None):
    flo = _shoe("flo", flo_price, brand=brand)
    flo_color = _color(flo, "flo", flo_price, gtins=UPC, available=flo_available)
    superstep = _shoe("superstep", superstep_price, brand=brand)
    superstep_color = _color(superstep, "superstep", superstep_price, gtins=EAN, available=superstep_available)
    return flo, flo_color, superstep, superstep_color


def _active(obj) -> bool:
    obj.refresh_from_db()
    return obj.is_active


def test_gtin_and_article_normalization():
    assert normalize_gtin("196968173624") == normalize_gtin("0196968173624") == "00196968173624"
    assert normalize_gtin("1K35052T0HFXS") == ""  # внутренний код SuperStep — не штрихкод
    assert normalize_gtin("0000000000") == ""
    assert article_key("Nike", "DV5456-106") == article_key("NIKE", "DV5456.106") == "nike|DV5456106"
    assert SuperstepParser._manufacturer_article("34-IH9166.-") == "IH9166"
    assert SuperstepParser._manufacturer_article("396464.01") == "396464.01"
    assert color_key("BEYAZ") == color_key("Beyaz") == "beyaz"
    assert color_key("Açık Gri") == "acik gri" != color_key("Açık Mavi")
    assert color_key("Beyaz-Siyah") != color_key("Beyaz")


def test_rule2_cheaper_offer_is_hidden_not_deleted():
    flo, flo_color, superstep, superstep_color = _pair("3000", "3500")

    report = CrossSourceDuplicateService().resolve()

    assert report["groups"] == 1 and report["hidden"] == 1
    assert not _active(flo_color) and _active(superstep_color)
    row = CrossSourceDuplicate.objects.get(hidden_variant_id=flo_color.pk)
    assert row.shown_variant_id == superstep_color.pk
    assert row.match == CrossSourceDuplicate.Match.EAN
    assert row.reason == CrossSourceDuplicate.Reason.PRICE
    # Единственный цвет скрыт — карточка снята целиком, но не удалена.
    assert row.product_hidden
    assert not _active(flo) and not Product.objects.get(pk=flo.base_product_id).is_active
    assert ShoeVariant.objects.filter(pk=flo_color.pk).exists()
    assert Product.objects.get(pk=superstep.base_product_id).is_active


def test_rule1_same_name_without_common_barcode_is_not_a_duplicate():
    flo = _shoe("flo", "3000")
    _color(flo, "flo", "3000", gtins=UPC)
    superstep = _shoe("superstep", "3500")
    _color(superstep, "superstep", "3500", gtins=["4068805874772", "4068805874789"])

    assert CrossSourceDuplicateService().resolve()["groups"] == 0
    assert not CrossSourceDuplicate.objects.exists()


def test_rule1_one_common_barcode_is_not_enough():
    flo = _shoe("flo", "3000")
    _color(flo, "flo", "3000", gtins=UPC)
    superstep = _shoe("superstep", "3500")
    _color(superstep, "superstep", "3500", gtins=[EAN[0], "4068805874789"])

    assert CrossSourceDuplicateService().resolve()["groups"] == 0


def test_rule1_article_fallback_only_without_barcodes(nike):
    flo = _shoe("flo", "3000", brand=nike)
    flo_color = _color(flo, "flo", "3000", gtins=UPC, mpn="DV5456-106")
    superstep = _shoe("superstep", "3500", brand=nike)
    superstep_color = _color(superstep, "superstep", "3500", mpn="DV5456.106")  # штрихкодов нет

    CrossSourceDuplicateService().resolve()

    row = CrossSourceDuplicate.objects.get(hidden_variant_id=flo_color.pk)
    assert row.match == CrossSourceDuplicate.Match.ARTICLE
    assert row.shown_variant_id == superstep_color.pk


def test_rule1_article_needs_same_brand_and_missing_barcodes(nike):
    adidas, _ = Brand.objects.get_or_create(slug="adidas-dups-test", defaults={"name": "adidas"})
    flo = _shoe("flo", "3000", brand=nike)
    _color(flo, "flo", "3000", gtins=UPC, mpn="DV5456-106")
    other_brand = _shoe("superstep", "3500", brand=adidas)
    _color(other_brand, "superstep", "3500", mpn="DV5456.106")
    # Штрихкоды есть у обоих и разные — один артикул ничего не решает.
    with_codes = _shoe("superstep", "3600", brand=nike)
    _color(with_codes, "superstep", "3600", gtins=["4068805874772", "4068805874789"], mpn="DV5456.106")

    assert CrossSourceDuplicateService().resolve()["groups"] == 0


def test_rule3_prices_swap_offers_swap(settings):
    settings.CROSS_SOURCE_DUPLICATES_ENABLED = True
    flo, flo_color, superstep, superstep_color = _pair("3000", "3500")
    CrossSourceDuplicateService().resolve()
    assert not _active(flo_color)

    # FLO подорожал — пересчёт по одному товару (как после импорта или проверки карточки).
    ShoeVariant.objects.filter(pk=flo_color.pk).update(price=Decimal("4000"))
    report = CrossSourceDuplicateService().resolve([flo.base_product_id])
    # Скрытый цвет возвращается только после проверки у продавца — до неё показан текущий.
    assert report["verify"] == {("shoes", flo_color.pk)}
    assert not _active(flo_color) and _active(superstep_color)
    with patch("apps.catalog.services.cross_source_duplicates._check_at_seller", return_value="found"):
        assert verify_hidden_duplicate("shoes", flo_color.pk) == "found"

    assert _active(flo_color) and not _active(superstep_color)
    assert _active(flo) and Product.objects.get(pk=flo.base_product_id).is_active
    assert not Product.objects.get(pk=superstep.base_product_id).is_active
    row = CrossSourceDuplicate.objects.get()
    assert row.hidden_variant_id == superstep_color.pk and row.shown_variant_id == flo_color.pk


def test_rule4_cheaper_shown_when_expensive_has_no_sizes():
    _, flo_color, _, superstep_color = _pair("3000", "3500", superstep_available=False)

    CrossSourceDuplicateService().resolve()

    assert _active(flo_color) and not _active(superstep_color)
    row = CrossSourceDuplicate.objects.get()
    assert row.hidden_variant_id == superstep_color.pk
    assert row.reason == CrossSourceDuplicate.Reason.STOCK


def test_rule4_nobody_in_stock_shows_expensive():
    _, flo_color, _, superstep_color = _pair(
        "3000", "3500", flo_available=False, superstep_available=False
    )

    CrossSourceDuplicateService().resolve()

    assert not _active(flo_color) and _active(superstep_color)


def test_partial_card_keeps_other_colors_and_their_price():
    flo = _shoe("flo", "3000")
    matched = _color(flo, "flo", "3000", gtins=UPC, sort_order=0)
    unique = _color(flo, "flo", "2500", gtins=["196968999999", "196968999998"], sort_order=1)
    superstep = _shoe("superstep", "3500")
    _color(superstep, "superstep", "3500", gtins=EAN)

    CrossSourceDuplicateService().resolve()

    assert not _active(matched) and _active(unique)
    assert _active(flo)
    assert not CrossSourceDuplicate.objects.get().product_hidden
    assert Product.objects.get(pk=flo.base_product_id).price == Decimal("2500")


def test_rescrape_does_not_return_hidden_color_and_stores_gtin():
    flo, flo_color, _, _ = _pair("3000", "3500")
    CrossSourceDuplicateService().resolve()
    product = Product.objects.get(pk=flo.base_product_id)
    spec = {
        "external_id": flo_color.external_id,
        "color": "Beyaz",
        "price": 3000,
        "currency": "TRY",
        "is_available": True,
        "stock_quantity": 3,
        "sizes": [{"size": "40", "is_available": True, "barcode": UPC[0]}],
    }

    ScraperIntegrationService()._sync_fashion_variants(product, variants=[spec])

    assert not _active(flo_color)
    assert list(flo_color.sizes.values_list("gtin", flat=True)) == ["00196968173624"]


def test_resolve_takes_price_and_strikethrough_of_one_colour_in_stock(settings):
    """Пересчёт дублей — то же правило цены, что импорт и витрина
    (default_fashion_variant): первый цвет карточки распродан — пара одного цвета в
    наличии, а не 749,70 при зачёркнутой 1 249,50; и при уже записанном дубле."""
    settings.CROSS_SOURCE_DUPLICATES_ENABLED = True
    flo, flo_color, _superstep, _superstep_color = _pair("3000", "3500")
    ShoeVariant.objects.filter(pk=flo_color.pk).update(sort_order=2)
    gray = _color(flo, "flo", "749.70", available=False, sort_order=0, color="Gri")
    blue = _color(flo, "flo", "999.60", sort_order=1, color="Mavi")
    ShoeVariant.objects.filter(pk=gray.pk).update(old_price=Decimal("899.00"))
    ShoeVariant.objects.filter(pk=blue.pk).update(old_price=Decimal("1249.50"))
    product_id = flo.base_product_id

    for _ in range(2):
        resolve_for_products([product_id])

        assert not _active(flo_color)
        product = Product.objects.get(pk=product_id)
        assert (product.price, product.old_price, product.is_available) == (
            Decimal("999.60"),
            Decimal("1249.50"),
            True,
        )
        Product.objects.filter(pk=product_id).update(price=Decimal("749.70"))
    assert CrossSourceDuplicate.objects.filter(hidden_variant_id=flo_color.pk).exists()


def test_automatic_resolve_only_when_enabled(settings):
    flo, flo_color, _, _ = _pair("3000", "3500")

    settings.CROSS_SOURCE_DUPLICATES_ENABLED = False
    resolve_for_products([flo.base_product_id])
    assert _active(flo_color)

    settings.CROSS_SOURCE_DUPLICATES_ENABLED = True
    resolve_for_products([flo.base_product_id])
    assert not _active(flo_color)


def test_hidden_card_redirects_temporarily_and_leaves_sitemap():
    flo, flo_color, superstep, superstep_color = _pair("3000", "3500")
    CrossSourceDuplicateService().resolve()

    flo_slug = Product.objects.get(pk=flo.base_product_id).slug
    response = APIClient().get(f"/api/catalog/products/resolve/{flo_slug}")

    assert response.status_code == 200
    assert response.data["canonical_path"].endswith(f"/{superstep.slug}")
    assert response.data["redirect_permanent"] is False
    assert response.data["redirect_active_variant_slug"] == superstep_color.slug

    shown = APIClient().get(f"/api/catalog/products/resolve/{Product.objects.get(pk=superstep.base_product_id).slug}")
    assert shown.data["redirect_permanent"] is True

    sitemap = APIClient().get("/api/catalog/sitemap-products", {"domain": "shoes", "page_size": 500})
    slugs = {row["slug"] for row in sitemap.data["results"]}
    assert superstep.slug in slugs and flo.slug not in slugs


def test_command_shows_by_default_and_unhide_all_rolls_back(tmp_path):
    flo, flo_color, _, _ = _pair("3000", "3500")

    out = StringIO()
    call_command("resolve_cross_source_duplicates", stdout=out)
    assert "Групп одинаковых цветов: 1" in out.getvalue()
    assert _active(flo_color) and not CrossSourceDuplicate.objects.exists()

    backup = tmp_path / "dups.json"
    call_command("resolve_cross_source_duplicates", "--apply", "--backup", str(backup), stdout=StringIO())
    assert backup.exists() and not _active(flo_color)

    call_command(
        "resolve_cross_source_duplicates", "--unhide-all", "--apply", "--backup", str(tmp_path / "undo.json"),
        stdout=StringIO(),
    )
    assert _active(flo_color) and _active(flo)
    assert not CrossSourceDuplicate.objects.exists()


# --- ревью #305: снятое продавцом не возвращается, нет склейки через третий, гонка ---


def test_color_gone_at_seller_is_never_returned():
    flo = _shoe("flo", "3000")
    matched = _color(flo, "flo", "3000", gtins=UPC, sort_order=0)
    other = _color(flo, "flo", "2500", gtins=["196968999999", "196968999998"], sort_order=1)
    superstep = _shoe("superstep", "3500")
    superstep_color = _color(superstep, "superstep", "3500", gtins=EAN)
    CrossSourceDuplicateService().resolve()
    assert not _active(matched)

    # Продавец убрал цвет из карточки: импорт снимает и скрытый нами цвет.
    spec = {
        "external_id": other.external_id, "color": "Siyah", "price": 2500, "currency": "TRY",
        "is_available": True, "stock_quantity": 3, "sizes": [{"size": "40", "is_available": True}],
    }
    ScraperIntegrationService()._sync_fashion_variants(Product.objects.get(pk=flo.base_product_id), variants=[spec])
    matched.refresh_from_db()
    assert not matched.is_active and not matched.is_available
    assert not CrossSourceDuplicate.objects.exists()

    # Даже если теперь он «дороже» — на сайт не возвращается, пара остаётся показанной.
    ShoeVariant.objects.filter(pk=matched.pk).update(price=Decimal("4000"))
    CrossSourceDuplicateService().resolve()
    assert not _active(matched) and _active(superstep_color)


def test_card_retired_by_stale_products_is_never_returned():
    flo, flo_color, superstep, superstep_color = _pair("3000", "3500")
    CrossSourceDuplicateService().resolve()
    _set_active(Product.objects.get(pk=flo.base_product_id), False)

    ShoeVariant.objects.filter(pk=flo_color.pk).update(price=Decimal("4000"))
    CrossSourceDuplicateService().resolve()

    assert not Product.objects.get(pk=flo.base_product_id).is_active and not _active(flo)
    assert _active(superstep_color) and Product.objects.get(pk=superstep.base_product_id).is_active
    assert not CrossSourceDuplicate.objects.exists()


def test_rule4_nobody_in_stock_keeps_current_offer():
    _, flo_color, _, superstep_color = _pair("3000", "3500", flo_available=False, superstep_available=False)
    CrossSourceDuplicateService().resolve()
    assert _active(superstep_color)

    ShoeVariant.objects.filter(pk=flo_color.pk).update(price=Decimal("4000"))
    CrossSourceDuplicateService().resolve()

    assert not _active(flo_color) and _active(superstep_color)


def test_chain_through_third_color_is_not_merged():
    other_upc = ["196968555551", "196968555552", "196968555553"]
    flo_a = _shoe("flo", "3000")
    _color(flo_a, "flo", "3000", gtins=UPC)
    flo_c = _shoe("flo", "3100")
    _color(flo_c, "flo", "3100", gtins=other_upc)
    superstep = _shoe("superstep", "3500")
    _color(superstep, "superstep", "3500", gtins=EAN[:2] + other_upc[:2])

    assert CrossSourceDuplicateService().resolve()["groups"] == 0
    assert not CrossSourceDuplicate.objects.exists()


def test_barcode_shared_by_two_colors_of_one_seller_is_ignored():
    flo = _shoe("flo", "3000")
    _color(flo, "flo", "3000", gtins=[UPC[0]])
    for price in ("3500", "3600"):
        superstep = _shoe("superstep", price)
        _color(superstep, "superstep", price, gtins=[EAN[0]])

    assert CrossSourceDuplicateService().resolve()["groups"] == 0


def test_one_common_barcode_only_when_both_have_one():
    flo = _shoe("flo", "3000")
    _color(flo, "flo", "3000", gtins=UPC)
    superstep = _shoe("superstep", "3500")
    _color(superstep, "superstep", "3500", gtins=[EAN[0]])
    assert CrossSourceDuplicateService().resolve()["groups"] == 0

    cap_flo = _shoe("flo", "900")
    _color(cap_flo, "flo", "900", gtins=["196968777771"])
    cap_superstep = _shoe("superstep", "950")
    _color(cap_superstep, "superstep", "950", gtins=["0196968777771"])
    assert CrossSourceDuplicateService().resolve()["groups"] == 1


def test_rule1_article_without_color_needs_same_color(nike):
    flo = _shoe("flo", "3000", brand=nike)
    _color(flo, "flo", "3000", gtins=UPC, mpn="B75806", color="Beyaz")
    black = _shoe("superstep", "3500", brand=nike)
    _color(black, "superstep", "3500", mpn="B75806.-", color="Siyah")
    assert CrossSourceDuplicateService().resolve()["groups"] == 0

    white = _shoe("superstep", "3600", brand=nike)
    _color(white, "superstep", "3600", mpn="B75806.-", color="BEYAZ")
    assert CrossSourceDuplicateService().resolve()["groups"] == 1


def test_stale_plan_never_hides_both_offers():
    _, flo_color, _, superstep_color = _pair("3000", "3500")
    service = CrossSourceDuplicateService(["shoes"])
    members = service.load_members("shoes")
    decisions = service.plan("shoes", members)
    # Пока план считался, параллельный импорт снял показываемый цвет.
    ShoeVariant.objects.filter(pk=superstep_color.pk).update(is_active=False)

    service.apply("shoes", members, decisions)

    assert _active(flo_color)
    assert not CrossSourceDuplicate.objects.exists()


def test_flag_off_still_fixes_card_price_from_shown_colors(settings):
    flo = _shoe("flo", "3000")
    _color(flo, "flo", "3000", gtins=UPC, sort_order=0)
    _color(flo, "flo", "2500", gtins=["196968999999", "196968999998"], sort_order=1)
    superstep = _shoe("superstep", "3500")
    _color(superstep, "superstep", "3500", gtins=EAN)
    CrossSourceDuplicateService().resolve()
    # Проверка карточки записала цену первого (скрытого) цвета.
    Product.objects.filter(pk=flo.base_product_id).update(price=Decimal("3000"))

    settings.CROSS_SOURCE_DUPLICATES_ENABLED = False
    resolve_for_products([flo.base_product_id])

    assert Product.objects.get(pk=flo.base_product_id).price == Decimal("2500")


def test_rule2_compares_site_price_with_markup():
    """«Дороже» — для покупателя: цена продавца с нашей наценкой (раздел, бренд)."""
    flo, flo_color, superstep, superstep_color = _pair("3000", "3500")
    # У раздела FLO своя наценка 50 %: 4 500 на сайте против 3 500 (+ общая) у SuperStep.
    section = Category.objects.create(name="Кроссовки FLO", slug=f"flo-sneakers-{uuid4().hex[:8]}", margin_percent=50)
    Product.objects.filter(pk=flo.base_product_id).update(category=section)

    CrossSourceDuplicateService().resolve()

    assert _active(flo_color) and not _active(superstep_color)
    row = CrossSourceDuplicate.objects.get()
    assert row.shown_price == Decimal("4500.00")


# --- повторное ревью #305 ---------------------------------------------------------


def _clothing_pair():
    colors = []
    for source, price, codes in (("flo", "1000", UPC), ("superstep", "1200", EAN)):
        domain = ClothingProduct.objects.create(
            name="Polo", slug=f"{source}-polo-{uuid4().hex[:10]}", price=Decimal(price), currency="TRY",
            is_available=True,
        )
        variant = ClothingVariant.objects.create(
            product=domain, name="Цвет", slug=f"{source}-polo-color-{uuid4().hex[:10]}", color="Beyaz",
            price=Decimal(price), currency="TRY", is_available=True,
            external_id=f"{source}-variant-{uuid4().hex[:8]}",
        )
        for index, code in enumerate(codes):
            ClothingVariantSize.objects.create(variant=variant, size=f"S{index}", gtin=normalize_gtin(code))
        colors.append(variant)
    return colors


def test_unhide_all_with_type_keeps_other_types(tmp_path):
    _, flo_shoe, _, _ = _pair("3000", "3500")
    flo_polo, _ = _clothing_pair()
    CrossSourceDuplicateService().resolve()
    assert CrossSourceDuplicate.objects.count() == 2

    call_command(
        "resolve_cross_source_duplicates", "--unhide-all", "--type", "shoes", "--apply",
        "--backup", str(tmp_path / "undo.json"), stdout=StringIO(),
    )

    assert _active(flo_shoe)
    assert list(CrossSourceDuplicate.objects.values_list("product_type", flat=True)) == ["clothing"]
    assert not _active(flo_polo)


def test_hidden_color_returns_only_after_seller_confirms(settings):
    settings.CROSS_SOURCE_DUPLICATES_ENABLED = True
    _, flo_color, _, superstep_color = _pair("3000", "3500")
    CrossSourceDuplicateService().resolve()
    ShoeVariant.objects.filter(pk=flo_color.pk).update(price=Decimal("4000"))

    # Проверка не удалась — ничего не меняется, показан текущий.
    with patch("apps.catalog.services.cross_source_duplicates._check_at_seller", return_value="unknown"):
        assert verify_hidden_duplicate("shoes", flo_color.pk) == "unknown"
    CrossSourceDuplicateService().resolve()
    assert not _active(flo_color) and _active(superstep_color)

    # Продавец убрал цвет — строка удаляется, цвет не вернётся никогда.
    with patch("apps.catalog.services.cross_source_duplicates._check_at_seller", return_value="gone"):
        assert verify_hidden_duplicate("shoes", flo_color.pk) == "gone"
    flo_color.refresh_from_db()
    assert not flo_color.is_active and not flo_color.is_available
    assert not CrossSourceDuplicate.objects.exists() and _active(superstep_color)


def test_confirmation_expires():
    _, flo_color, _, superstep_color = _pair("3000", "3500")
    CrossSourceDuplicateService().resolve()
    ShoeVariant.objects.filter(pk=flo_color.pk).update(price=Decimal("4000"))
    stale = timezone.now() - cross_source_duplicates.CONFIRM_TTL - timedelta(minutes=1)
    CrossSourceDuplicate.objects.update(confirmed_at=stale)

    CrossSourceDuplicateService().resolve()
    assert not _active(flo_color) and _active(superstep_color)

    CrossSourceDuplicate.objects.update(confirmed_at=timezone.now())
    CrossSourceDuplicateService().resolve()
    assert _active(flo_color) and not _active(superstep_color)


def _flo_offer(product, variant):
    url = f"https://www.flo.com.tr/urun/nike-{uuid4().hex[:6]}"
    return ProductSourceOffer.objects.create(
        product=product, parser_key="flo", canonical_url=url, source_domain="www.flo.com.tr",
        variant_key=variant.external_id, size_key="40", source_price=Decimal("3000"), source_currency="TRY",
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
    )


def _result(offer, *, availability=OfferAvailability.IN_STOCK, error=None):
    return OfferCheckResult(
        availability_status=availability, stock_precision=OfferStockPrecision.BOOLEAN,
        canonical_url=offer.canonical_url, error=error,
    )


def test_check_at_seller_uses_live_offer_check_or_fresh_import():
    flo, flo_color, _, _ = _pair("3000", "3500")
    CrossSourceDuplicateService().resolve()
    row = CrossSourceDuplicate.objects.get()
    product = Product.objects.get(pk=flo.base_product_id)

    # Источник без живой проверки: свежий импорт — подтверждение, старый — нет.
    Product.objects.filter(pk=product.pk).update(last_synced_at=timezone.now())
    assert _check_at_seller(row, flo_color) == "found"
    Product.objects.filter(pk=product.pk).update(last_synced_at=timezone.now() - timedelta(days=3))
    assert _check_at_seller(row, flo_color) == "unknown"

    offer = _flo_offer(product, flo_color)
    service = "apps.catalog.services.source_offer_verification.SourceOfferVerificationService"
    with patch(f"{service}.is_enabled_for", return_value=True):
        with patch(f"{service}.verify", return_value=_result(offer)):
            assert _check_at_seller(row, flo_color) == "found"
        gone = OfferCheckError(OfferCheckErrorCode.NOT_FOUND, "404", retryable=False)
        with patch(f"{service}.verify", return_value=_result(offer, availability=OfferAvailability.UNKNOWN, error=gone)):
            assert _check_at_seller(row, flo_color) == "gone"
        timeout = OfferCheckError(OfferCheckErrorCode.TIMEOUT, "timeout", retryable=True)
        with patch(
            f"{service}.verify",
            return_value=_result(offer, availability=OfferAvailability.SOURCE_UNREACHABLE, error=timeout),
        ):
            assert _check_at_seller(row, flo_color) == "unknown"


def test_flag_off_retired_shown_card_returns_hidden_pair_after_check(settings):
    settings.CROSS_SOURCE_DUPLICATES_ENABLED = False
    flo, flo_color, superstep, _ = _pair("3000", "3500")
    CrossSourceDuplicateService().resolve()
    assert not Product.objects.get(pk=flo.base_product_id).is_active

    _set_active(Product.objects.get(pk=superstep.base_product_id), False)
    # До подтверждения продавца скрытая пара не возвращается.
    assert not _active(flo_color)

    with patch("apps.catalog.services.cross_source_duplicates._check_at_seller", return_value="found"):
        verify_hidden_duplicate("shoes", flo_color.pk)

    assert _active(flo_color) and Product.objects.get(pk=flo.base_product_id).is_active
    assert not CrossSourceDuplicate.objects.exists()
    response = APIClient().get(f"/api/catalog/products/resolve/{Product.objects.get(pk=flo.base_product_id).slug}")
    assert response.status_code == 200 and response.data["redirect_permanent"] is True


def test_card_refresh_keeps_hidden_color_inactive():
    flo, flo_color, _, _ = _pair("3000", "3500")
    flo_other = _color(flo, "flo", "2500", gtins=["196968999999", "196968999998"], sort_order=1)
    CrossSourceDuplicateService().resolve()
    product = Product.objects.get(pk=flo.base_product_id)
    specs = [
        {
            "external_id": variant.external_id, "price": price, "currency": "TRY", "color": "Beyaz",
            "is_available": True, "sizes": [{"size": "40", "is_available": True}],
        }
        for variant, price in ((flo_color, 3000), (flo_other, 2500))
    ]

    ProductCardSourceRefreshService()._sync_fashion_inventory(product, specs, [])

    assert not _active(flo_color) and _active(flo_other)


def test_source_url_gone_marks_hidden_color_unavailable():
    flo, flo_color, _, _ = _pair("3000", "3500")
    CrossSourceDuplicateService().resolve()
    product = Product.objects.get(pk=flo.base_product_id)
    offer = _flo_offer(product, flo_color)

    ProductCardSourceRefreshService()._mark_source_url_unavailable(
        RefreshTarget(product=product, offer=offer, parser_class=FloParser)
    )

    flo_color.refresh_from_db()
    assert not flo_color.is_available and not flo_color.is_active
    assert set(flo_color.sizes.values_list("is_available", flat=True)) == {False}


def test_full_pass_runs_in_short_batches(monkeypatch):
    monkeypatch.setattr(cross_source_duplicates, "FULL_PASS_BATCH", 1)
    locks = []
    original = CrossSourceDuplicateService._lock
    monkeypatch.setattr(CrossSourceDuplicateService, "_lock", staticmethod(lambda: locks.append(1) or original()))
    _, first, _, _ = _pair("3000", "3500")
    other = ["196968333331", "196968333332"]
    flo = _shoe("flo", "2000")
    second = _color(flo, "flo", "2000", gtins=other)
    superstep = _shoe("superstep", "2500")
    _color(superstep, "superstep", "2500", gtins=[f"0{code}" for code in other])

    report = CrossSourceDuplicateService().resolve()

    assert report["hidden"] == 2 and not _active(first) and not _active(second)
    # Группа попадает в пачку каждого своего товара, но считается один раз.
    assert report["groups"] == 2 and report["kept"] == 0
    # Каждая пачка (здесь — один товар) — своя короткая транзакция со своей блокировкой.
    assert len(locks) == 4


def test_import_retiring_color_during_resolve_wins():
    _, flo_color, _, _ = _pair("3000", "3500")
    CrossSourceDuplicateService().resolve()
    ShoeVariant.objects.filter(pk=flo_color.pk).update(price=Decimal("4000"))
    CrossSourceDuplicate.objects.update(confirmed_at=timezone.now())
    service = CrossSourceDuplicateService(["shoes"])
    members = service.load_members("shoes")
    plan = service.plan("shoes", members)
    # Пока план считался, импорт снял цвет у продавца (удалил строку).
    cross_source_duplicates.forget_hidden_variants("shoes", [flo_color.pk])

    service.apply("shoes", members, plan)

    assert not _active(flo_color)


# --- третье ревью #305 ------------------------------------------------------------


def test_frozen_group_still_fixes_card_price_and_stock():
    flo = _shoe("flo", "3000")
    matched = _color(flo, "flo", "3000", gtins=UPC, sort_order=0)
    _color(flo, "flo", "2500", gtins=["196968999999", "196968999998"], sort_order=1, available=False)
    superstep = _shoe("superstep", "3500")
    _color(superstep, "superstep", "3500", gtins=EAN)
    CrossSourceDuplicateService().resolve()
    # FLO подорожал и подтверждён, но при выключенном флаге SuperStep не скрывается — группа
    # заморожена. Проверка карточки тем временем записала цену и наличие скрытого цвета.
    ShoeVariant.objects.filter(pk=matched.pk).update(price=Decimal("4000"))
    CrossSourceDuplicate.objects.update(confirmed_at=timezone.now())
    Product.objects.filter(pk=flo.base_product_id).update(price=Decimal("4000"), is_available=True)

    CrossSourceDuplicateService().resolve([flo.base_product_id], hide_new=False)

    assert not _active(matched)
    card = Product.objects.get(pk=flo.base_product_id)
    assert card.price == Decimal("2500") and not card.is_available


def test_flag_off_requests_seller_check_only_when_it_can_change_something():
    flo, flo_color, superstep, _ = _pair("3000", "3500")
    CrossSourceDuplicateService().resolve()
    ShoeVariant.objects.filter(pk=flo_color.pk).update(price=Decimal("4000"))

    # SuperStep показан и без новых скрытий не уйдёт — платная проверка FLO бесполезна.
    report = CrossSourceDuplicateService().resolve([flo.base_product_id], hide_new=False)
    assert report["verify"] == set()

    # Показанную карточку сняли — проверка нужна: от неё зависит, вернётся ли FLO.
    _set_active(Product.objects.get(pk=superstep.base_product_id), False)
    report = CrossSourceDuplicateService().resolve([flo.base_product_id], hide_new=False)
    assert report["verify"] == {("shoes", flo_color.pk)}
