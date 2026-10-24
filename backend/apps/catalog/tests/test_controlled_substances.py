"""Препараты, запрещённые к ввозу в РФ и СНГ (TD-024): отметка, админка, без продвижения."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.test import RequestFactory
from rest_framework.test import APIClient

from apps.catalog import controlled_substances
from apps.catalog.admin_wave2 import ImportRestrictionFilter, MedicineProductAdmin
from apps.catalog.models import Category, CategoryCollection, MedicineProduct, Product

pytestmark = pytest.mark.django_db

REFERENCE = {
    "pregabalin": {
        "inn_ru": "прегабалин",
        "countries": {"RU": {"list": "ПП 964, сильнодействующие"}, "KZ": {"list": "Список III"}},
    },
    "psodoefedrin hidroklorur": {"inn_ru": "псевдоэфедрин", "countries": {"RU": {"list": "ПП 681, Список IV"}}},
}


@pytest.fixture(autouse=True)
def reference(monkeypatch):
    monkeypatch.setattr(controlled_substances, "_index", lambda: REFERENCE)
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)


def _medicine(slug, active, atc="N03AX16", **extra):
    category = Category.objects.get_or_create(slug="medicines", defaults={"name": "Medicine"})[0]
    medicine = MedicineProduct.objects.create(
        name=slug.upper(), slug=slug, category=category, active_ingredient=active, atc_code=atc,
        price=100, currency="TRY", is_active=True, **extra,
    )
    medicine.refresh_from_db()
    return medicine


def test_restrictions_by_active_ingredient_including_combinations():
    assert controlled_substances.restrictions("Pregabalin") == (
        "KZ,RU", "Казахстан: прегабалин — Список III\nРоссия: прегабалин — ПП 964, сильнодействующие",
    )
    countries, note = controlled_substances.restrictions("Psödoefedrin Hidroklorür + Ibuprofen")
    assert countries == "RU" and "псевдоэфедрин" in note
    assert controlled_substances.restrictions("Ibuprofen") == ("", "")


def test_saved_medicine_is_marked_and_unmarked_with_its_substance():
    medicine = _medicine("perge", "Pregabalin")
    assert medicine.import_restricted_countries == "KZ,RU"
    medicine.active_ingredient = "Ibuprofen"
    medicine.save(update_fields=["active_ingredient"])
    medicine.refresh_from_db()
    assert medicine.import_restricted_countries == "" and medicine.import_restriction_note == ""


def test_restricted_medicine_is_not_featured_and_not_in_collections():
    restricted = _medicine("perge", "Pregabalin", is_featured=True)
    allowed = _medicine("lyrica-free", "Gabapentin", is_featured=True)
    slugs = {row["slug"] for row in APIClient().get("/api/catalog/products/featured", {"limit": 20}).json()}
    assert allowed.slug in slugs and restricted.slug not in slugs

    root = Category.objects.get(slug="medicines")
    collection = CategoryCollection.objects.create(parent=root, name="Нервная система", slug="nerves", atc_prefixes="N03")
    chosen = set(MedicineProduct.objects.filter(collection.medicine_filter()).values_list("slug", flat=True))
    assert chosen == {"lyrica-free"}


def test_admin_filter_badge_and_banner():
    restricted = _medicine("perge", "Pregabalin")
    _medicine("ibufen", "Ibuprofen", atc="M01AE01")
    admin = MedicineProductAdmin(MedicineProduct, AdminSite())
    request = RequestFactory().get("/")
    for value, expected in (("any", {"perge"}), ("KZ", {"perge"}), ("UZ", set()), ("no", {"ibufen"})):
        flt = ImportRestrictionFilter(request, {"import_restricted": [value]}, MedicineProduct, admin)
        assert set(flt.queryset(request, MedicineProduct.objects.all()).values_list("slug", flat=True)) == expected
    assert "Запрещён к ввозу: KZ, RU" in admin.import_restriction_badge(restricted)
    assert "Не продвигать" in admin.import_restriction_banner(restricted)


def test_command_recomputes_after_reference_update(capsys, monkeypatch):
    medicine = _medicine("tramal", "Tramadol")
    assert medicine.import_restricted_countries == ""
    monkeypatch.setattr(
        controlled_substances, "_index", lambda: {**REFERENCE, "tramadol": {"inn_ru": "трамадол", "countries": {"RU": {"list": "ПП 964"}}}}
    )
    call_command("refresh_import_restrictions", "--dry-run")
    medicine.refresh_from_db()
    assert medicine.import_restricted_countries == ""
    call_command("refresh_import_restrictions")
    medicine.refresh_from_db()
    assert medicine.import_restricted_countries == "RU"
    assert "с отметкой всего: 1" in capsys.readouterr().out


def test_order_admin_warns_about_restricted_items():
    from apps.orders.admin import OrderAdmin
    from apps.orders.models import Order, OrderItem

    restricted = _medicine("perge", "Pregabalin")
    order = Order.objects.create(number="T-1", contact_name="A", contact_phone="+90")
    OrderItem.objects.create(order=order, product=restricted.base_product, product_name="PERGE 75 MG", quantity=1, price=1, total=1)
    admin = OrderAdmin(Order, AdminSite())
    assert "1 поз." in admin.import_restriction_badge(order)
    assert "PERGE 75 MG — KZ, RU" in admin.import_restriction_banner(order)


def test_buyer_sees_restriction_in_search_catalog_card_and_cart():
    from apps.orders.models import Cart, CartItem
    from apps.orders.serializers import CartItemSerializer

    restricted = _medicine("perge", "Pregabalin")
    _medicine("ibufen", "Ibuprofen", atc="M01AE01")
    client = APIClient()

    search = client.get("/api/catalog/products", {"search": "e", "view": "card"}).json()["results"]
    assert {row["slug"]: row["import_restricted_countries"] for row in search} == {"perge": ["KZ", "RU"], "ibufen": []}

    cards = client.get("/api/catalog/medicines/products", {"view": "card"}).json()["results"]
    assert {row["slug"]: row.get("import_restricted_countries") for row in cards} == {"perge": ["KZ", "RU"], "ibufen": None}

    detail = client.get("/api/catalog/medicines/products/perge").json()
    assert detail["import_restricted_countries"] == ["KZ", "RU"]

    item = CartItem.objects.create(cart=Cart.objects.create(session_key="s1"), product=restricted.base_product, quantity=1, price=1)
    assert CartItemSerializer(item, context={}).data["product_import_restricted_countries"] == ["KZ", "RU"]


def test_half_cyrillic_abbreviation_is_not_untranslated_turkish():
    from apps.catalog.product_semantics import looks_untranslated_turkish

    # Пилот 6, KLOROBEN: «ТÜFAM» с кириллической «Т» в переводе инструкции.
    assert not looks_untranslated_turkish("Сообщите в Турецкий центр фармаконадзора (ТÜFAM) по номеру 0 800 314 00 08.")
    assert looks_untranslated_turkish("Doktorunuza danışınız.")
