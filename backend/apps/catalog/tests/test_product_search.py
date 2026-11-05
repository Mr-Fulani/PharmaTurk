"""Поиск товаров по подготовленному тексту (docs/PRODUCT_SEARCH.md, аудит 05.11.2026)."""

import uuid
from decimal import Decimal

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.catalog.models import (
    Brand,
    MedicineProduct,
    MedicineProductTranslation,
    Product,
    ProductTranslation,
)
from apps.catalog.models_search import ProductSearchIndex
from apps.catalog.product_search import (
    build_search_row,
    normalize_search_text,
    reindex_products,
    search_words,
    write_search_rows,
    iter_search_rows,
)

URL = "/api/catalog/products"
MEDICINES_URL = "/api/catalog/medicines/products"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Плёночной оболочкой", "пленочной оболочкой"),
        ("ЁЖИК", "ежик"),
        ("Abdi İbrahim", "abdi ibrahim"),
        ("HELVACIZADE Helvacızade", "helvacizade helvacizade"),
        ("Sırt Çantası Şapka Ğ Öz Ürün", "sirt cantasi sapka g oz urun"),
        ("İBUMENT", "ibument"),
        ("Омега-3", "омега 3"),
        ("U.S. Polo Assn.", "u s polo assn"),
        ("VOGAST (лансопразол) 30 мг, капсулы", "vogast лансопразол 30 мг капсулы"),
        ("  a__b  ", "a b"),
        (None, ""),
    ],
)
def test_normalize_search_text(raw, expected):
    assert normalize_search_text(raw) == expected


def test_query_words_make_numbers_optional_next_to_words():
    assert search_words("Nurofen 400") == ("nurofen 400", ["nurofen"])
    assert search_words("омега-3") == ("омега 3", ["омега"])
    assert search_words("8699479160029") == ("8699479160029", ["8699479160029"])
    assert search_words(" - ") == ("", [])


@pytest.fixture
def make_product(db, monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)

    def make(name, **fields):
        fields.setdefault("product_type", "accessories")
        return Product.objects.create(
            name=name,
            slug=f"search-{uuid.uuid4().hex[:10]}",
            price=Decimal("10.00"),
            currency="TRY",
            is_active=True,
            is_available=True,
            **fields,
        )

    return make


@pytest.fixture
def make_medicine(db, monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)

    def make(name, **fields):
        medicine = MedicineProduct.objects.create(
            name=name,
            slug=f"med-{uuid.uuid4().hex[:10]}",
            price=Decimal("10.00"),
            currency="TRY",
            is_active=True,
            **fields,
        )
        medicine.refresh_from_db()  # shadow-Product создаётся в save()
        return medicine

    return make


def _rebuild():
    return write_search_rows(list(iter_search_rows()))


def _ids(params, url=URL):
    response = APIClient().get(url, {"view": "card", "include_facets": "false", "page_size": 50, **params})
    assert response.status_code == 200
    return [row["id"] for row in response.data["results"]]


def test_search_finds_brand_translation_codes_and_spelling_variants(make_product):
    polo = Brand.objects.create(name="U.S. Polo Assn.", slug=f"uspa-{uuid.uuid4().hex[:6]}")
    shirt = make_product("Erkek Gömlek", brand=polo, sku="JL9188", barcode="8699479160029")
    ProductTranslation.objects.create(product=shirt, locale="en", name="Men's shirt")
    omega = make_product("Омега-3 рыбий жир, капсулы")
    film = make_product("Таблетки, покрытые плёночной оболочкой")
    _rebuild()

    assert _ids({"search": "US Polo"}) == [shirt.pk]
    assert _ids({"search": "u.s. polo"}) == [shirt.pk]
    assert _ids({"search": "shirt"}) == [shirt.pk]
    assert _ids({"search": "gomlek"}) == [shirt.pk]
    assert _ids({"search": "jl9188"}) == [shirt.pk]
    assert _ids({"search": "8699479160029"}) == [shirt.pk]
    assert _ids({"search": "омега 3"}) == [omega.pk]
    assert _ids({"search": "пленочной оболочкой"}) == [film.pk]
    assert _ids({"search": "polo kadın"}) == []  # каждое слово должно найтись


def test_search_finds_medicine_by_manufacturer_ingredient_and_atc(make_medicine):
    abdi = Brand.objects.create(name="Abdi İbrahim", slug=f"abdi-{uuid.uuid4().hex[:6]}")
    parol = make_medicine(
        "PAROL 500 mg 20 tablet",
        brand=abdi,
        manufacturer="Atabay İlaç",
        active_ingredient="parasetamol",
        atc_code="N02BE01",
    )
    MedicineProductTranslation.objects.create(
        product=parol, locale="ru", name="PAROL 500 мг, 20 таблеток", active_ingredient="парацетамол"
    )
    MedicineProductTranslation.objects.create(
        product=parol, locale="en", name="PAROL 500 mg, 20 tablets", active_ingredient="paracetamol"
    )
    other = make_medicine("NUROFEN 400 mg", manufacturer="Reckitt", active_ingredient="ibuprofen")
    _rebuild()

    product_id = parol.base_product_id
    for query in ("Abdi Ibrahim", "atabay ilac", "парацетамол", "paracetamol", "parasetamol", "n02be01", "таблеток"):
        assert _ids({"search": query}) == [product_id], query
    assert _ids({"search": "Nurofen 200"}) == [other.base_product_id]  # число необязательно

    # Поиск внутри раздела «Медикаменты» идёт по тому же тексту.
    assert _ids({"search": "Atabay"}, url=MEDICINES_URL) == [parol.pk]


def test_exact_and_prefix_matches_come_first(make_product):
    newest_combo = make_product("Grip Cold (парацетамол + фенилэфрин) порошок")
    starts_with = make_product("Парацетамол 500 мг таблетки")
    in_brackets = make_product("PAROL (парацетамол) 500 мг")
    exact = make_product("Парацетамол")
    # Сначала новые — так было до правки: самый новый товар шёл первым.
    for position, product in enumerate([exact, in_brackets, starts_with, newest_combo]):
        Product.objects.filter(pk=product.pk).update(created_at=product.created_at.replace(year=2020 + position))
    _rebuild()

    assert _ids({"search": "парацетамол"}) == [exact.pk, starts_with.pk, in_brackets.pk, newest_combo.pk]
    # Явная сортировка из запроса важнее точности.
    assert _ids({"search": "парацетамол", "ordering": "newest"})[0] == newest_combo.pk


def test_brand_exact_match_comes_first(make_product):
    lacoste = Brand.objects.create(name="Lacoste", slug=f"lacoste-{uuid.uuid4().hex[:6]}")
    mention = make_product("Сумка в стиле Lacoste для обуви")
    branded = make_product("Slam Break Kadın Spor Ayakkabı", brand=lacoste)
    Product.objects.filter(pk=branded.pk).update(created_at=branded.created_at.replace(year=2020))
    _rebuild()

    assert _ids({"search": "lacoste"}) == [branded.pk, mention.pk]


def test_empty_index_keeps_old_name_search(make_product):
    product = make_product("Cleocin 150 mg")
    make_product("Other")

    assert not ProductSearchIndex.objects.exists()
    assert _ids({"search": "Cleocin 150"}) == [product.pk]
    assert _ids({"search": "cleocin capsules"}) == []


def test_saving_product_updates_ready_index(make_product, django_capture_on_commit_callbacks):
    product = make_product("Old title")
    _rebuild()

    product.name = "Yeni Başlık"
    with django_capture_on_commit_callbacks(execute=True):
        product.save()
        ProductTranslation.objects.create(product=product, locale="en", name="New title")

    row = ProductSearchIndex.objects.get(product=product)
    assert row.name.splitlines() == ["yeni baslik", "new title"]
    assert _ids({"search": "new title"}) == [product.pk]


def test_saving_product_does_not_start_empty_index(make_product, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        make_product("Before backfill")

    assert not ProductSearchIndex.objects.exists()
    assert reindex_products([1]) == 0


def test_build_row_without_brand_or_domain(make_product):
    product = make_product("Kahve Fincanı", sku="TW-01")

    row = build_search_row(product)

    assert row == {"name": "kahve fincani", "brand": "", "text": "kahve fincani tw 01"}


def test_rebuild_command_shows_by_default_and_writes_with_apply(make_product, capsys):
    product = make_product("İnci Kolye")

    call_command("rebuild_product_search_index")
    assert not ProductSearchIndex.objects.exists()
    assert "новых строк: 1" in capsys.readouterr().out

    call_command("rebuild_product_search_index", "--apply")
    assert ProductSearchIndex.objects.get(product=product).text == "inci kolye"

    call_command("rebuild_product_search_index", "--apply")
    assert "без изменений: 1" in capsys.readouterr().out

    call_command("rebuild_product_search_index", "--clear", "--apply")
    assert not ProductSearchIndex.objects.exists()


def _seed_index(make_product):
    """Непустой индекс: сигналы пишут только в заполненный (как на проде после бэкафилла)."""
    make_product("Seed product")
    _rebuild()


@pytest.mark.django_db(transaction=True)
def test_new_domain_product_is_indexed_with_domain_fields(make_product, make_medicine):
    _seed_index(make_product)

    medicine = make_medicine("CORASPIN 100 mg", manufacturer="Bayer Türk", active_ingredient="asetilsalisilik asit")

    row = ProductSearchIndex.objects.get(product_id=medicine.base_product_id)
    assert "bayer turk" in row.text and "asetilsalisilik asit" in row.text


@pytest.mark.django_db(transaction=True)
def test_variant_codes_are_indexed_on_save(make_product, monkeypatch):
    from apps.catalog.models import ClothingProduct, ClothingVariant

    _seed_index(make_product)
    clothing = ClothingProduct.objects.create(
        name="Basic Tişört", slug=f"cl-{uuid.uuid4().hex[:8]}", price=Decimal("5"), currency="TRY", is_active=True
    )
    clothing.refresh_from_db()

    ClothingVariant.objects.create(product=clothing, name="Beyaz", slug=f"v-{uuid.uuid4().hex[:8]}", sku="JL9188")

    assert "jl9188" in ProductSearchIndex.objects.get(product_id=clothing.base_product_id).text


def test_save_without_search_fields_does_not_reindex(make_product, django_capture_on_commit_callbacks, monkeypatch):
    product = make_product("Stock item")
    _rebuild()
    calls = []
    monkeypatch.setattr("apps.catalog.product_search.reindex_products", lambda ids: calls.append(ids))

    with django_capture_on_commit_callbacks(execute=True):
        product.is_available = False
        product.save(update_fields=["is_available"])
    assert calls == []

    with django_capture_on_commit_callbacks(execute=True):
        product.save(update_fields=["name"])
    assert calls == [{product.pk}]


def test_unchanged_text_is_not_rewritten(make_product):
    product = make_product("Same title")
    _rebuild()

    assert reindex_products([product.pk]) == 0
    Product.objects.filter(pk=product.pk).update(name="Other title")
    assert reindex_products([product.pk]) == 1


def test_reindex_error_does_not_break_save(make_product, django_capture_on_commit_callbacks, monkeypatch):
    product = make_product("Robust title")
    _rebuild()

    def boom(ids):
        raise RuntimeError("index down")

    monkeypatch.setattr("apps.catalog.product_search.reindex_products", boom)
    with django_capture_on_commit_callbacks(execute=True):
        product.name = "Saved anyway"
        product.save()

    assert Product.objects.get(pk=product.pk).name == "Saved anyway"


def test_single_character_query_keeps_newest_first(make_product):
    older = make_product("a older")
    newer = make_product("b newer a")
    Product.objects.filter(pk=older.pk).update(created_at=older.created_at.replace(year=2020))
    _rebuild()

    assert _ids({"search": "a"})[:2] == [newer.pk, older.pk]


def test_rebuild_ids_refused_while_index_is_empty(make_product):
    from django.core.management.base import CommandError

    product = make_product("Lonely")
    with pytest.raises(CommandError):
        call_command("rebuild_product_search_index", "--ids", str(product.pk), "--apply")
    assert not ProductSearchIndex.objects.exists()
