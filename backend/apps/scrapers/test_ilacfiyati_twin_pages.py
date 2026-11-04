"""Две страницы ilacfiyati одного препарата: остаётся страница с ценой, сомнения — на проверку."""

import json
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command
from rest_framework.test import APIClient

from apps.catalog.models import Category, MedicineProduct, Product, ProductSlugHistory
from apps.scrapers import ilacfiyati_twins
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.ilacfiyati_twins import HIDE, REVIEW, TwinPage, decide_group, name_identity
from apps.scrapers.services import ScraperIntegrationService

TRIKAFTA = "TRIKAFTA (COPACKAGED) 100 MG,75 MG, 50 MG; 150 MG 84 TABLETS"
SERVICE_BARCODE = "1111111101867"


def _page(pk, name, price=None, *, ingredient="", available=True, url=""):
    return TwinPage(
        source_name=name, ingredient=ingredient, price=Decimal(price) if price else None,
        is_available=available, pk=pk, url=url,
    )


def test_name_identity_ignores_case_punctuation_and_form_spelling():
    assert name_identity("FEBUXT 40 MG 30 TB") == name_identity("Febuxt 40mg 30 tablets")
    assert name_identity("HEXAXIM 0,5 ML") == name_identity("HEXAXIM 0.5 ML")
    assert name_identity("STIMOL 1 G 36 POŞET") == name_identity("STIMOL 1 G 36 SACHETS")
    assert name_identity("ROSUSTAR 10 MG FILM KAPLI TABLET 28 ADET") == name_identity("ROSUSTAR 10 MG 28 TABLET")


def test_priced_page_is_kept_and_priceless_twin_hidden():
    # Страница TEB «0,00 TL» пишет состав иначе — порядок и İ не важны.
    priced = _page(10290, TRIKAFTA, "16109.59", ingredient="Elexacaftor/Tezacaftor/Ivacaftor And Ivacaftor",
                   url="https://ilacfiyati.com/ilaclar/trikafta-copackaged-100-mg-75-mg-50-mg-150-mg-84-tablets")
    priceless = _page(13753, TRIKAFTA, ingredient="Elexacaftor/İvacaftor/Tezacaftor, And İvacaftor",
                      url="https://ilacfiyati.com/ilaclar/trikafta-copackaged-84-tablets")

    [decision] = decide_group([priceless, priced])

    assert (decision.action, decision.keep.pk, decision.page.pk) == (HIDE, 10290, 13753)
    assert decision.reason == "вторая страница без цены"


def test_prekunil_url_with_other_dose_goes_to_review():
    name = "PREKUNIL 750 MG 550 TABLET"
    priced = _page(12329, name, "260", url="https://ilacfiyati.com/ilaclar/prekunil-500-mg-550-tablet")
    priceless = _page(13721, name, url="https://ilacfiyati.com/ilaclar/prekunil-750-mg-550-tablet")

    [decision] = decide_group([priced, priceless])

    assert decision.action == REVIEW
    assert "500" in decision.reason


def test_different_ingredients_go_to_review_but_fuller_list_does_not():
    name = "PREKUNIL 750 MG 550 TABLET"
    lnaa = _page(1, name, "260", ingredient="Large Neutral Amino Acis ( Lnaa)")
    full = _page(2, name, ingredient="Large Neutral Amino Acids, Vitamin B12, Vitamin B6, Calcium, Phosphorus")
    assert decide_group([lnaa, full])[0].reason == "разный состав"

    short = _page(3, "PYRIDOXAL PHOSPHATE 50 MG 60 KAPSUL", "10", ingredient="Pyridoxal Phosphate")
    longer = _page(4, "PYRIDOXAL PHOSPHATE 50 MG 60 CAPSULES", ingredient="Pyridoxal-5-Phosphate Monohydrate")
    assert decide_group([short, longer])[0].action == HIDE


@pytest.mark.parametrize(
    ("first", "second", "reason"),
    [
        ("MARKUMAR 3 MG 100 TABLET", "MARCUMAR 3 MG 1X98 TABS", "в названиях разные числа (дозировка или количество)"),
        ("ABRAXANE 100 MG 1 AMPUL", "ABRAXANE 100 MG 1 VIAL", "в названиях разные слова: ampul, flakon"),
        ("GLYCOPYRROLATE 1 MG 100 TABLET", "GLYCOPYRROLATE 1 MG TABLETS USP", "в названиях разные числа (дозировка или количество)"),
    ],
)
def test_different_names_go_to_review(first, second, reason):
    [decision] = decide_group([_page(1, first, "100"), _page(2, second)])
    assert (decision.action, decision.reason) == (REVIEW, reason)


def test_equal_priced_pages_keep_older_and_different_prices_go_to_review():
    name = "VIGRANDE 50 MG 4 TABLET"
    [same] = decide_group([_page(9610, name, "66.80"), _page(801, name, "66.8")])
    assert (same.action, same.keep.pk, same.page.pk) == (HIDE, 801, 9610)

    [different] = decide_group([_page(9610, name, "70"), _page(801, name, "66.8")])
    assert (different.action, different.reason) == (REVIEW, "у страниц разные цены")


def test_unavailable_keeper_goes_to_review():
    name = "GTO 1000 ML 4 OIL"
    [decision] = decide_group([_page(7524, name, "50", available=False), _page(13150, name)])
    assert (decision.action, decision.reason) == (REVIEW, "оставляемая страница не в наличии")


def test_repeat_suffix_in_url_is_not_a_dose():
    name = "QUENSYL 200 MG 100 TABLET"
    [decision] = decide_group([
        _page(11409, name, "40", url="https://ilacfiyati.com/ilaclar/quensyl-200-mg-100-tablet"),
        _page(13374, name, url="https://ilacfiyati.com/ilaclar/quensyl-200-mg-100-tablet-2"),
    ])
    assert decision.action == HIDE


# --- БД: парсер и команда -------------------------------------------------------------

def _medicine(slug, *, name=TRIKAFTA, price=None, barcode=SERVICE_BARCODE, ingredient="", available=True):
    category, _ = Category.objects.get_or_create(slug="twin-pages-medicines", defaults={"name": "Medicines"})
    product = Product.objects.create(
        name=name,
        slug=slug,
        category=category,
        product_type="medicines",
        price=price,
        currency="EUR",
        is_available=available,
        is_active=True,
        external_id=slug,
        external_url=f"https://ilacfiyati.com/ilaclar/{slug}",
        external_data={"source": "ilacfiyati", "source_name": name, "attributes": {"active_ingredient": ingredient}},
    )
    MedicineProduct.objects.filter(base_product=product).update(barcode=barcode)
    return product


def _scraped(slug, *, name=TRIKAFTA, price=None, barcode=SERVICE_BARCODE):
    return ScrapedProduct(
        name=name,
        price=price,
        url=f"https://ilacfiyati.com/ilaclar/{slug}",
        external_id=slug,
        barcode=barcode,
        source="ilacfiyati",
        attributes={"barcode": barcode},
    )


def _active(product):
    product.refresh_from_db()
    return product.is_active, MedicineProduct.objects.get(base_product=product).is_active


@pytest.mark.django_db
def test_parser_skips_priceless_page_of_existing_priced_medicine(monkeypatch):
    priced = _medicine("trikafta-copackaged-100-mg-84-tablets", price=Decimal("16109.59"))
    service = ScraperIntegrationService()
    monkeypatch.setattr(service, "_create_new_product", lambda *a, **k: pytest.fail("twin must not be created"))
    scraped = _scraped("trikafta-copackaged-84-tablets")

    action, product = service._process_single_product(None, scraped)

    assert (action, product) == ("skipped", None)
    assert f"на сайте товар {priced.pk}" in scraped._medicine_import_skip_reason
    assert Product.objects.filter(product_type="medicines").count() == 1


@pytest.mark.django_db
def test_parser_new_priced_page_hides_shown_priceless_twin(monkeypatch):
    priceless = _medicine("trikafta-copackaged-84-tablets")
    service = ScraperIntegrationService()
    created = {}

    def fake_create(_session, scraped):
        created["product"] = _medicine(scraped.external_id, price=scraped.price)
        return "created", created["product"]

    monkeypatch.setattr(service, "_create_new_product", fake_create)

    action, product = service._process_single_product(
        None, _scraped("trikafta-copackaged-100-mg-84-tablets", price=Decimal("16109.59")),
    )

    assert action == "created"
    assert _active(priceless) == (False, False)
    assert _active(product) == (True, True)
    assert priceless.external_data[ilacfiyati_twins.TWIN_OF_KEY] == product.pk
    assert ProductSlugHistory.objects.get(old_slug=priceless.slug).product_id == product.pk


@pytest.mark.django_db
def test_parser_creates_page_with_other_dose_and_marks_it_for_review(monkeypatch):
    _medicine("prekunil-500-mg-550-tablet", name="PREKUNIL 750 MG 550 TABLET", price=Decimal("260"))
    service = ScraperIntegrationService()
    monkeypatch.setattr(
        service, "_create_new_product",
        lambda _s, scraped: ("created", _medicine(scraped.external_id, name=scraped.name)),
    )
    scraped = _scraped("prekunil-750-mg-550-tablet", name="PREKUNIL 750 MG 550 TABLET")

    action, product = service._process_single_product(None, scraped)

    assert action == "created"
    assert "на проверку" in scraped._ilacfiyati_twin_review
    assert Product.objects.filter(product_type="medicines", is_active=True).count() == 2


@pytest.mark.django_db
def test_rescrape_does_not_return_hidden_twin():
    priced = _medicine("trikafta-copackaged-100-mg-84-tablets", price=Decimal("16109.59"))
    priceless = _medicine("trikafta-copackaged-84-tablets")
    ilacfiyati_twins.hide_twin(priceless, priced)

    action, product = ScraperIntegrationService()._process_single_product(
        None, _scraped("trikafta-copackaged-84-tablets"),
    )

    assert product.pk == priceless.pk
    assert _active(priceless) == (False, False)


@pytest.mark.django_db
def test_hidden_twin_address_redirects_to_kept_product():
    priced = _medicine("trikafta-copackaged-100-mg-84-tablets", price=Decimal("16109.59"))
    priceless = _medicine("trikafta-copackaged-84-tablets")
    ilacfiyati_twins.hide_twin(priceless, priced)

    response = APIClient().get(f"/api/catalog/products/resolve/{priceless.slug}")

    assert response.status_code == 200
    assert response.data["canonical_path"] == f"/product/{priced.slug}"
    assert response.data["redirect_permanent"] is True


@pytest.mark.django_db
def test_command_shows_by_default_and_apply_requires_backup(tmp_path, capsys):
    priced = _medicine("trikafta-copackaged-100-mg-84-tablets", price=Decimal("16109.59"))
    priceless = _medicine("trikafta-copackaged-84-tablets")
    _medicine("prekunil-500-mg-550-tablet", name="PREKUNIL 750 MG 550 TABLET", price=Decimal("260"),
              barcode="1111111100599")
    doubtful = _medicine("prekunil-750-mg-550-tablet", name="PREKUNIL 750 MG 550 TABLET", barcode="1111111100599")
    _medicine("single-page", barcode="1111111100001")

    call_command("hide_ilacfiyati_twin_pages", csv=str(tmp_path / "twins.csv"))
    output = capsys.readouterr().out
    assert "Групп: 2, скрыть: 1, на проверку: 1" in output
    assert _active(priceless) == (True, True)
    assert "prekunil-750-mg-550-tablet" in (tmp_path / "twins.csv").read_text(encoding="utf-8")

    with pytest.raises(CommandError):
        call_command("hide_ilacfiyati_twin_pages", apply=True)

    backup = tmp_path / "before.json"
    call_command("hide_ilacfiyati_twin_pages", apply=True, backup=str(backup))

    assert _active(priceless) == (False, False)
    assert _active(priced) == (True, True)
    assert _active(doubtful) == (True, True)
    [row] = json.loads(backup.read_text(encoding="utf-8"))
    assert (row["product_id"], row["keep_id"], row["is_active"]) == (priceless.pk, priced.pk, True)
    assert ilacfiyati_twins.TWIN_OF_KEY not in row["external_data"]
