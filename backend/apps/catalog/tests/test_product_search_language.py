"""Поиск: кириллица брендов и лекарств, раскладка, опечатки, синонимы, пол и раздел
(docs/PRODUCT_SEARCH.md, «Вторая очередь»; аудит 05.11.2026, P1)."""

import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.ai.services.medicine_seo import BRAND_NAMESPACE
from apps.ai.services.translation_memory import remember
from apps.catalog.models import Brand, Category, CategoryTranslation, MedicineProduct, Product
from apps.catalog.product_search import kind_words, search_plan
from apps.catalog.search_language import closest_word, edit_distance, latin_to_cyrillic, letter_twin, stem, switch_layout

from .test_product_search import URL, _ids, _rebuild


@pytest.fixture
def make_product(db, monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)

    def make(name, **fields):
        fields.setdefault("product_type", "accessories")
        return Product.objects.create(
            name=name, slug=f"lang-{uuid.uuid4().hex[:10]}", price=Decimal("10.00"), currency="TRY",
            is_active=True, is_available=True, **fields,
        )

    return make


@pytest.fixture
def make_medicine(db, monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)

    def make(name, **fields):
        medicine = MedicineProduct.objects.create(
            name=name, slug=f"lang-med-{uuid.uuid4().hex[:10]}", price=Decimal("10.00"), currency="TRY",
            is_active=True, **fields,
        )
        medicine.refresh_from_db()  # shadow-Product создаётся в save()
        return medicine

    return make


def _brand(name):
    return Brand.objects.create(name=name, slug=f"b-{uuid.uuid4().hex[:8]}")


def _search(query):
    response = APIClient().get(URL, {"search": query, "view": "card", "include_facets": "false", "page_size": 50})
    assert response.status_code == 200
    return response.data


@pytest.mark.parametrize(
    "raw, expected",
    [("gfhfwtnfvjk", "парацетамол"), ("ыфтщаш", "sanofi"), ("yehjaty", "нурофен"), ("Kfrjcn", "лакост"), ("ab где", "")],
)
def test_switch_layout(raw, expected):
    assert switch_layout(raw) == expected


def test_language_helpers():
    assert latin_to_cyrillic("euthyrox") == "эутирокс"
    assert latin_to_cyrillic("jordan") == "джордан"
    assert latin_to_cyrillic("d3") == ""
    assert stem("женские") == "женск" and stem("магния") == "магни" and stem("худи") == "худи"
    assert letter_twin("д3") == "d3" and letter_twin("c") == "с" and letter_twin("омега") == ""
    assert edit_distance("ибупорфен", "ибупрофен") == 1  # перестановка соседних букв
    assert closest_word("нурафен", ["нурофен 400", "нурофен", "норофен"]) == "нурофен"
    assert closest_word("магнум", ["магний"]) == ""  # две правки в коротком слове — другое слово


def test_kind_words_from_turkish_and_english_names():
    words = kind_words(["Lacoste L003 Kadın Bej Spor Ayakkabı"])
    assert {"женский", "Women's", "кроссовки", "Sneakers"} <= set(words)
    assert {"худи", "Hoodie"} <= set(kind_words(["Erkek Kapüşonlu Sweatshirt"]))


def test_brand_found_in_cyrillic(make_product):
    lacoste = make_product("L003 Kadın Spor Ayakkabı", brand=_brand("Lacoste"))
    nike = make_product("Court Vision Low", brand=_brand("Nike"))
    tommy = make_product("Erkek T-Shirt", brand=_brand("Tommy Hilfiger"))
    sanofi = make_product("Some product", brand=_brand("Sanofi"))
    abdi = make_product("Other product", brand=_brand("Abdi İbrahim"))
    _rebuild()

    assert _ids({"search": "лакост"}) == [lacoste.pk]
    assert _ids({"search": "найк"}) == [nike.pk]
    assert _ids({"search": "томми хилфигер"}) == [tommy.pk]
    assert _ids({"search": "санофи"}) == [sanofi.pk]
    assert _ids({"search": "абди ибрагим"}) == [abdi.pk]
    assert "search_info" not in _search("лакост")  # найдено как есть, без исправления


def test_medicine_trade_name_found_in_cyrillic(make_medicine):
    remember(BRAND_NAMESPACE, {"MAJEZIK": {"ru": "Мажезик", "en": "MAJEZIK"}})
    majezik = make_medicine("MAJEZIK 100 MG 15 FILM TABLET", manufacturer="Sanovel")
    euthyrox = make_medicine("EUTHYROX 50 MCG 50 TABLET", manufacturer="Merck")
    _rebuild()

    assert _ids({"search": "мажезик"}) == [majezik.base_product_id]  # словарь medicine_brand
    assert _ids({"search": "эутирокс"}) == [euthyrox.base_product_id]  # чтение латиницы
    assert _ids({"search": "мажезик 100"}) == [majezik.base_product_id]


def test_wrong_layout_and_latin_reading(make_product):
    paracetamol = make_product("Парацетамол 500 мг таблетки")
    sanofi = make_product("Product", brand=_brand("Sanofi"))
    _rebuild()

    data = _search("gfhfwtnfvjk")
    assert [row["id"] for row in data["results"]] == [paracetamol.pk]
    assert data["search_info"] == {"mode": "layout", "query": "парацетамол"}
    assert _ids({"search": "ыфтщаш"}) == [sanofi.pk]
    make_product("Elbise")
    _rebuild()
    assert _ids({"search": "худи"}) == []  # раскладка «[elb» без «[» — не «elbise»
    data = _search("paracetamol")
    assert [row["id"] for row in data["results"]] == [paracetamol.pk]
    assert data["search_info"] == {"mode": "translit", "query": "парацетамол"}


def test_typos_are_corrected_without_garbage(make_product):
    paracetamol = make_product("Парацетамол 500 мг таблетки")
    ibuprofen = make_product("Ибупрофен 400 мг")
    make_product("Магний B6")
    _rebuild()

    data = _search("парацитамол")
    assert [row["id"] for row in data["results"]] == [paracetamol.pk]
    assert data["search_info"] == {"mode": "typo", "query": "парацетамол"}
    assert _ids({"search": "ибупрафен 400"}) == [ibuprofen.pk]
    assert _ids({"search": "магнум"}) == []
    assert _ids({"search": "абвгдежз"}) == []


def test_synonyms_gender_and_section(make_product):
    women_shoes = make_product("Lacoste L003 Kadın Bej Spor Ayakkabı")
    men_shoes = make_product("Erkek Sneaker", gender="men")
    hoodie = make_product("Erkek Kapüşonlu Sweatshirt")
    bags = Category.objects.create(name="Sırt Çantası", slug=f"c-{uuid.uuid4().hex[:8]}")
    CategoryTranslation.objects.create(category=bags, locale="ru", name="Рюкзаки")
    backpack = make_product("Unisex Okul Modeli", category=bags)
    _rebuild()

    assert _ids({"search": "женские кроссовки"}) == [women_shoes.pk]
    assert set(_ids({"search": "кроссы"})) == {women_shoes.pk, men_shoes.pk}
    assert _ids({"search": "мужские кроссовки"}) == [men_shoes.pk]
    assert set(_ids({"search": "sneakers"})) == {women_shoes.pk, men_shoes.pk}
    assert _ids({"search": "толстовка"}) == [hoodie.pk]
    assert _ids({"search": "худи"}) == [hoodie.pk]
    assert _ids({"search": "рюкзак"}) == [backpack.pk]


def test_kind_words_skip_medicines(make_medicine):
    # «SET», «BOT» в названии лекарства — не тип товара.
    medicine = make_medicine("BOTOX 100 U SET")
    _rebuild()
    assert _ids({"search": "ботинки"}) == []
    assert _ids({"search": "botox"}) == [medicine.base_product_id]


def test_vitamin_letter_in_cyrillic(make_product):
    d3 = make_product("Vitamin D3 1000 IU")
    c = make_product("Витамин C 500 мг")
    zinc = make_product("Витамин D3 с цинком")
    _rebuild()

    assert set(_ids({"search": "витамин д3"})) == {d3.pk, zinc.pk}
    assert set(_ids({"search": "витамин с"})) == {c.pk, zinc.pk}  # «с» целым словом, не любая буква с
    assert zinc.pk not in _ids({"search": "витамин к"})


def test_found_query_costs_one_index_check(make_product):
    make_product("Парацетамол 500 мг")
    _rebuild()
    with CaptureQueriesContext(connection) as queries:
        plan = search_plan("парацетамол")
    assert plan.mode == "words"
    assert len(queries) == 2  # индекс заполнен? + EXISTS по словам


def test_corrected_search_sql_uses_only_like(make_product):
    make_product("Парацетамол 500 мг")
    _rebuild()
    with CaptureQueriesContext(connection) as queries:
        _ids({"search": "парацитамол"})
    page_sql = [q["sql"] for q in queries if "catalog_product" in q["sql"] and "ORDER BY" in q["sql"]]
    assert page_sql and all("%>" not in sql and "similarity(" not in sql for sql in page_sql)


def test_category_change_reindexes_product(make_product, django_capture_on_commit_callbacks):
    make_product("Other")
    _rebuild()  # индекс не пуст — сигналы работают
    shoes = Category.objects.create(name="Кроссовки", slug=f"c-{uuid.uuid4().hex[:8]}")
    product = make_product("Model X")
    with django_capture_on_commit_callbacks(execute=True):
        product.category = shoes
        product.save(update_fields=["category"])
    assert _ids({"search": "кроссовки"}) == [product.pk]
