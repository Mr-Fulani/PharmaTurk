"""Дубли лекарств и БАДов ilacfiyati по списку пар: скрывается только полное совпадение."""

import csv
import json
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import CommandError, call_command
from rest_framework.test import APIClient

from apps.catalog.models import (
    Category, Favorite, MedicineProduct, Product, ProductSlugHistory, SupplementProduct,
)
from apps.orders.models import Cart, CartItem
from apps.scrapers import ilacfiyati_duplicates as dups

AKNETRENT_10 = "AKNETRENT 10 MG YUMUSAK JELATIN 30 KAPSUL"
AKNETRENT_20 = "AKNETRENT 20 MG YUMUSAK JELATIN 30 KAPSUL"
INOVIT = "INOVIT MULTIVITAMIN 20 EFERVESAN TABLET"


def _product(slug, *, name=AKNETRENT_10, product_type="medicines", price=None, currency="TRY", barcode="",
             available=True, manufacturer="Recordati", url_path="ilaclar"):
    category, _ = Category.objects.get_or_create(slug=f"dups-{product_type}", defaults={"name": product_type})
    product = Product.objects.create(
        name=name,
        slug=slug,
        category=category,
        product_type=product_type,
        price=price,
        currency=currency,
        is_available=available,
        is_active=True,
        external_id=slug,
        external_url=f"https://ilacfiyati.com/{url_path}/{slug}",
        external_data={
            "source": "ilacfiyati", "source_name": name,
            "attributes": {"manufacturer": manufacturer, "barcode": barcode},
        },
    )
    if product_type == "medicines":
        MedicineProduct.objects.filter(base_product=product).update(barcode=barcode)
    return product


def _medicine_pair():
    keep = _product("aknetrent-10-mg-yumusak-jelatin-30-kapsul", price=Decimal("289.77"), barcode="8699559190038")
    # Страница источника «-2»: старый штрихкод, «Pasif», без цены.
    hide = _product("aknetrent-10-mg-yumusak-jelatin-30-kapsul-2", barcode="")
    return keep, hide


def _domain_active(product):
    product.refresh_from_db()
    model = MedicineProduct if product.product_type == "medicines" else SupplementProduct
    return product.is_active, model.objects.get(base_product=product).is_active


def _pairs_csv(tmp_path, *pairs):
    path = tmp_path / "pairs.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["keep_id", "hide_id", "комментарий"])
        for keep, hide in pairs:
            writer.writerow([keep.pk, hide.pk, ""])
    return str(path)


def _problem(keep, hide):
    keep.refresh_from_db()
    hide.refresh_from_db()
    return dups.pair_problem(keep, hide)


@pytest.mark.django_db
def test_priceless_repeat_page_of_same_medicine_is_a_duplicate():
    keep, hide = _medicine_pair()
    assert _problem(keep, hide) == ""


@pytest.mark.django_db
def test_other_dose_is_not_a_duplicate():
    # Владелец сам поймал: AKNETRENT 10 мг и 20 мг — не дубли.
    keep = _product("aknetrent-10-mg-yumusak-jelatin-30-kapsul", price=Decimal("289.77"))
    other = _product("aknetrent-20-mg-yumusak-jelatin-30-kapsul", name=AKNETRENT_20)
    assert "числа" in _problem(keep, other)


@pytest.mark.django_db
def test_two_real_barcodes_of_medicine_go_to_review():
    keep = _product("liphonis-267-mg-sert-kapsul", name="LIPHONIS 267 MG SERT KAPSUL", barcode="8680760150430")
    other = _product("liphonis-267-mg-sert-kapsul-2", name="LIPHONIS 267 MG SERT KAPSUL", barcode="8680760150447")
    assert _problem(keep, other) == "разные штрихкоды: 8680760150430 / 8680760150447"


@pytest.mark.django_db
def test_placeholder_barcode_is_not_compared():
    keep = _product("febuxt-40-mg-30-tablet", name="FEBUXT 40 MG 30 TABLET", price=Decimal("10"),
                    barcode="8699000000001")
    other = _product("febuxt-40-mg-30-tablet-2", name="FEBUXT 40 MG 30 TABLET", barcode="1111111100001")
    assert _problem(keep, other) == ""


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("keep_kwargs", "hide_kwargs", "reason"),
    [
        ({"price": Decimal("289.77")}, {"price": Decimal("300")}, "разные цены"),
        ({}, {"price": Decimal("289.77")}, "у скрываемой есть цена, у оставляемой нет"),
        ({"price": Decimal("289.77"), "available": False}, {}, "оставляемая не в наличии, скрываемая в наличии"),
        ({"price": Decimal("289.77")}, {"manufacturer": "Other Pharma"}, "разные производители"),
    ],
)
def test_medicine_discrepancies_go_to_review(keep_kwargs, hide_kwargs, reason):
    keep = _product("aknetrent-10-mg-yumusak-jelatin-30-kapsul", **keep_kwargs)
    hide = _product("aknetrent-10-mg-yumusak-jelatin-30-kapsul-2", **hide_kwargs)
    assert _problem(keep, hide) == reason


@pytest.mark.django_db
def test_analog_stub_keeper_is_not_shown_so_pair_goes_to_review():
    keep, hide = _medicine_pair()
    Product.objects.filter(pk=keep.pk).update(external_data={**keep.external_data, "is_stub": True})
    assert _problem(keep, hide) == "оставляемая — заглушка аналога, на сайте не видна"


@pytest.mark.django_db
def test_supplement_with_other_barcode_and_price_is_a_duplicate():
    # БАД: у источника две карточки одного товара — разные штрихкоды и цены (одна устарела).
    keep = _product("inovit-multivitamin-20-efervesan-tablet", name=INOVIT, product_type="supplements",
                    price=Decimal("299"), barcode="8680000000011", url_path="takviye-edici-gida")
    hide = _product("inovit-multivitamin-20-efervesan-tablet-2", name=INOVIT, product_type="supplements",
                    price=Decimal("249"), barcode="8680000000028", url_path="takviye-edici-gida")
    assert _problem(keep, hide) == ""


@pytest.mark.django_db
def test_chain_and_repeated_hide_go_to_review():
    keep, hide = _medicine_pair()
    third = _product("aknetrent-10-mg-yumusak-jelatin-30-kapsul-3")
    decisions, missing = dups.decide_pairs([(keep.pk, hide.pk), (hide.pk, third.pk), (keep.pk, 999999)])

    assert [(d.action, d.reason) for d in decisions] == [
        (dups.REVIEW, "скрываемая оставляется в другой паре"),
        (dups.HIDE, "полный дубль"),
    ]
    assert missing == [(keep.pk, 999999, "товара нет в базе")]


@pytest.mark.django_db
def test_command_shows_by_default_apply_needs_new_backup(tmp_path, capsys):
    keep, hide = _medicine_pair()
    other_dose = _product("aknetrent-20-mg-yumusak-jelatin-30-kapsul", name=AKNETRENT_20)
    pairs = _pairs_csv(tmp_path, (keep, hide), (keep, other_dose))

    call_command("hide_ilacfiyati_duplicates", pairs=pairs, csv=str(tmp_path / "out.csv"))
    assert "Пар: 2, скрыть: 1, сомнительно: 1" in capsys.readouterr().out
    assert _domain_active(hide) == (True, True)
    assert "aknetrent-20-mg" in (tmp_path / "out.csv").read_text(encoding="utf-8")

    with pytest.raises(CommandError):
        call_command("hide_ilacfiyati_duplicates", pairs=pairs, apply=True)
    existing = tmp_path / "exists.json"
    existing.write_text("[]", encoding="utf-8")
    with pytest.raises(CommandError):
        call_command("hide_ilacfiyati_duplicates", pairs=pairs, apply=True, backup=str(existing))
    assert existing.read_text(encoding="utf-8") == "[]"
    assert _domain_active(hide) == (True, True)


@pytest.mark.django_db
def test_apply_hides_redirects_and_restore_returns(tmp_path):
    keep, hide = _medicine_pair()
    # Старый адрес, которым товар уже владел до скрытия, вернётся при откате.
    ProductSlugHistory.objects.create(old_slug="aknetrent-old", product=hide, product_type="medicines")
    hide_slug = MedicineProduct.objects.get(base_product=hide).slug
    backup = tmp_path / "before.json"

    call_command("hide_ilacfiyati_duplicates", pairs=_pairs_csv(tmp_path, (keep, hide)), apply=True,
                 backup=str(backup))

    assert _domain_active(hide) == (False, False)
    assert _domain_active(keep) == (True, True)
    assert hide.external_data[dups.DUPLICATE_OF_KEY] == keep.pk
    response = APIClient().get(f"/api/catalog/products/resolve/{hide_slug}")
    assert response.status_code == 200
    assert response.data["canonical_path"] == f"/product/{keep.slug}"
    assert response.data["redirect_permanent"] is True
    [row] = json.loads(backup.read_text(encoding="utf-8"))
    assert (row["product_id"], row["keep_id"], row["is_active"]) == (hide.pk, keep.pk, True)
    assert dups.DUPLICATE_OF_KEY not in row["external_data"]

    call_command("hide_ilacfiyati_duplicates", restore=str(backup))  # показ отката ничего не меняет
    assert _domain_active(hide) == (False, False)

    call_command("hide_ilacfiyati_duplicates", restore=str(backup), apply=True)

    assert _domain_active(hide) == (True, True)
    assert dups.DUPLICATE_OF_KEY not in hide.external_data
    assert not ProductSlugHistory.objects.filter(old_slug=hide_slug).exists()
    assert ProductSlugHistory.objects.get(old_slug="aknetrent-old").product_id == hide.pk


@pytest.mark.django_db
def test_hidden_supplement_leaves_catalog_sitemap_but_cart_and_favorites_work(tmp_path):
    keep = _product("inovit-multivitamin-20-efervesan-tablet", name=INOVIT, product_type="supplements",
                    price=Decimal("299"), url_path="takviye-edici-gida")
    hide = _product("inovit-multivitamin-20-efervesan-tablet-2", name=INOVIT, product_type="supplements",
                    price=Decimal("299"), url_path="takviye-edici-gida")
    cart_item = CartItem.objects.create(cart=Cart.objects.create(session_key="dups"), product=hide, quantity=1,
                                        price=1)
    Favorite.objects.create(session_key="dups-fav", content_type=ContentType.objects.get_for_model(Product),
                            object_id=hide.pk)
    hide_slug = SupplementProduct.objects.get(base_product=hide).slug

    call_command("hide_ilacfiyati_duplicates", pairs=_pairs_csv(tmp_path, (keep, hide)), apply=True,
                 backup=str(tmp_path / "before.json"))

    client = APIClient()
    listed = client.get("/api/catalog/supplements/products", {"page_size": 50}).data
    listed = listed.get("results", listed) if isinstance(listed, dict) else listed
    assert [row["base_product_id"] for row in listed] == [keep.pk]
    sitemap = client.get("/api/catalog/sitemap-products", {"domain": "supplements"}).data["results"]
    assert hide_slug not in {row["slug"] for row in sitemap}
    resolved = client.get(f"/api/catalog/products/resolve/{hide_slug}")
    assert resolved.data["canonical_path"] == f"/product/{keep.slug}"
    # Строка Списка заявки и избранное остаются и не ломаются.
    assert CartItem.objects.get(pk=cart_item.pk).product_id == hide.pk
    favorites = client.get("/api/catalog/favorites", HTTP_X_CART_SESSION="dups-fav")
    assert favorites.status_code == 200
    assert [row["product"]["id"] for row in favorites.data] == [hide.pk]


# --- Парсер: тот же товар источника не заводится второй раз ----------------------------

def _scraped(slug, *, name=AKNETRENT_10, barcode="8699559190038", price=None, inactive=False):
    from apps.scrapers.base.scraper import ScrapedProduct

    scraped = ScrapedProduct(
        name=name, price=price, url=f"https://ilacfiyati.com/ilaclar/{slug}", external_id=slug,
        barcode=barcode, source="ilacfiyati", is_available=not inactive,
        attributes={"barcode": barcode, "manufacturer": "Recordati"},
    )
    scraped.source_inactive = inactive
    return scraped


def _service_without_create(monkeypatch):
    from apps.scrapers.services import ScraperIntegrationService

    service = ScraperIntegrationService()
    monkeypatch.setattr(service, "_create_new_product", lambda *a, **k: pytest.fail("копия не должна заводиться"))
    return service


@pytest.mark.django_db
def test_parser_moves_renamed_page_to_existing_product(monkeypatch):
    # Источник переименовал страницу («…-ampul-2» → «…-ampul»): тот же штрихкод и название.
    existing = _product("adeleks-4-mg-2-ml-ampul-6-ampul-2", name="ADELEKS 4 MG/2 ML 6 AMPUL",
                        price=Decimal("152.63"), barcode="8685119899022")
    service = _service_without_create(monkeypatch)

    action, product = service._process_single_product(
        None, _scraped("adeleks-4-mg-2-ml-ampul-6-ampul", name="ADELEKS 4 MG/2 ML 6 AMPUL", barcode="8685119899022",
                       price=Decimal("152.63")),
    )

    assert product.pk == existing.pk
    existing.refresh_from_db()
    assert existing.external_id == "adeleks-4-mg-2-ml-ampul-6-ampul"
    assert existing.external_url == "https://ilacfiyati.com/ilaclar/adeleks-4-mg-2-ml-ampul-6-ampul"
    assert Product.objects.filter(product_type="medicines").count() == 1


@pytest.mark.django_db
def test_parser_creates_other_dose_with_same_barcode(monkeypatch):
    from apps.scrapers.services import ScraperIntegrationService

    _product("aknetrent-10-mg-yumusak-jelatin-30-kapsul", price=Decimal("289.77"), barcode="8699559190038")
    service = ScraperIntegrationService()
    created = []
    monkeypatch.setattr(service, "_create_new_product", lambda _s, scraped: created.append(scraped) or ("created", None))

    service._process_single_product(None, _scraped("aknetrent-20-mg-yumusak-jelatin-30-kapsul", name=AKNETRENT_20))

    assert [scraped.external_id for scraped in created] == ["aknetrent-20-mg-yumusak-jelatin-30-kapsul"]


@pytest.mark.django_db
def test_parser_leaves_placeholder_barcode_to_twin_rule(monkeypatch):
    from apps.scrapers.services import ScraperIntegrationService

    keep = _product("felbamate-400-mg-100-tablets", name="FELBAMATE 400 MG 100 TABLETS", barcode="1111111101085",
                    price=Decimal("100"))
    assert ScraperIntegrationService()._find_ilacfiyati_moved_page(
        _scraped("felbamate-400-mg-100-tablets-2", name="FELBAMATE 400 MG 100 TABLETS", barcode="1111111101085"),
    ) is None
    assert keep.is_active


@pytest.mark.django_db
def test_parser_does_not_create_passive_page(monkeypatch):
    # Страница «…-2» со старым штрихкодом и «İlaç Durumu: Pasif» — снятая регистрация.
    _product("aknetrent-10-mg-yumusak-jelatin-30-kapsul", price=Decimal("289.77"), barcode="8699559190038")
    service = _service_without_create(monkeypatch)
    scraped = _scraped("aknetrent-10-mg-yumusak-jelatin-30-kapsul-2", barcode="8699559190014", inactive=True)

    assert service._process_single_product(None, scraped) == ("skipped", None)
    assert "Pasif" in scraped._medicine_import_skip_reason
    assert Product.objects.filter(product_type="medicines").count() == 1


@pytest.mark.django_db
def test_source_url_lookup_does_not_take_repeat_page_for_its_prefix():
    from apps.scrapers.services import ScraperIntegrationService

    repeat = _product("aknetrent-10-mg-yumusak-jelatin-30-kapsul-2")
    service = ScraperIntegrationService()

    assert service._find_ilacfiyati_medicine_product_by_source_url(
        _scraped("aknetrent-10-mg-yumusak-jelatin-30-kapsul"),
    ) is None
    assert service._find_ilacfiyati_medicine_product_by_source_url(
        _scraped("aknetrent-10-mg-yumusak-jelatin-30-kapsul-2"),
    ) == repeat
