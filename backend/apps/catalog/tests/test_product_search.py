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
    # Каждое слово должно найтись; не нашлось — лишнее слово убирается, и ответ говорит об этом.
    response = APIClient().get(URL, {"search": "polo kadın", "view": "card", "include_facets": "false"})
    assert [row["id"] for row in response.data["results"]] == [shirt.pk]
    assert response.data["search_info"] == {"mode": "partial", "query": "polo"}


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


def test_short_query_is_newest_first_without_relevance(make_product):
    older = make_product("Кр")  # точное совпадение, но запрос короче 3 символов
    newer = make_product("Крем для рук")
    Product.objects.filter(pk=older.pk).update(created_at=older.created_at.replace(year=2020))
    _rebuild()

    assert _ids({"search": "кр"})[:2] == [newer.pk, older.pk]


def test_search_excludes_service_rows_without_external_data_condition(make_product):
    """Служебные строки — подзапросом по частичному индексу 0217: условие на external_data
    в основном запросе детоастило дампы парсеров по каждому совпадению (прод: «кр» 20 с)."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    public = make_product("Krem public")
    variant = make_product("Krem variant copy", external_data={"source_variant_id": 1})
    stub = make_product("Krem stub", product_type="medicines", external_data={"is_stub": True})
    _rebuild()

    with CaptureQueriesContext(connection) as queries:
        found = _ids({"search": "krem"})

    assert found == [public.pk]
    assert variant.pk not in found and stub.pk not in found
    search_sql = [q["sql"] for q in queries.captured_queries if "catalog_productsearchindex" in q["sql"]]
    assert search_sql
    for sql in search_sql:
        assert '"catalog_product"."external_data" ?' not in sql


def _search_queryset(params):
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    from apps.catalog.views import ProductViewSet

    view = ProductViewSet()
    view.request = Request(APIRequestFactory().get(URL, params))
    view.action = "list"
    view.format_kwarg = None
    return view.get_queryset()


def test_search_queryset_can_use_nonpublic_partial_index(make_product):
    """§2.9: предикат подзапроса совпадает с частичным индексом 0217 — без детоаста external_data."""
    from django.db import connection

    make_product("Krem")
    _rebuild()
    sql, params = _search_queryset({"search": "krem", "view": "card"}).query.sql_with_params()

    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")  # пустая тестовая БД — иначе seq scan
        cursor.execute(f"EXPLAIN {sql}", params)
        plan = "\n".join(row[0] for row in cursor.fetchall())

    assert "catalog_product_nonpublic_id_idx" in plan
    assert '"catalog_product"."external_data" ?' not in sql
    assert '"catalog_product"."external_data"' not in sql.split(" FROM ")[0]  # отложен в карточках


def test_relevance_sort_uses_only_cheap_keys(make_product):
    make_product("Krem nemlendirici")
    _rebuild()
    sql = str(_search_queryset({"search": "krem nemlendirici", "view": "card"}).query)

    assert "ORDER BY" in sql
    assert "similarity(" not in sql.lower()
    assert " ~ " not in sql  # без регулярных выражений


def test_search_pages_are_consistent_with_count(make_product):
    created = [make_product(f"Krem {i:02d}").pk for i in range(25)]
    Product.objects.filter(pk__in=created).update(created_at=Product.objects.get(pk=created[0]).created_at)
    _rebuild()

    seen = []
    for page in (1, 2, 3):
        response = APIClient().get(
            URL, {"search": "krem", "view": "card", "include_facets": "false", "page_size": 10, "page": page}
        )
        assert response.status_code == 200
        assert response.data["count"] == 25
        seen += [row["id"] for row in response.data["results"]]

    assert sorted(seen) == sorted(created) and len(seen) == len(set(seen))


def test_short_words_with_space_are_not_ranked(make_product):
    older = make_product("кр ма")  # точное совпадение, но слова короче 3 символов
    newer = make_product("Крем маска")
    Product.objects.filter(pk=older.pk).update(created_at=older.created_at.replace(year=2020))
    _rebuild()

    assert _ids({"search": "кр ма"})[:2] == [newer.pk, older.pk]


def test_legacy_search_endpoint_excludes_service_rows_without_external_data_condition(make_product):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    public = make_product("Krem public")
    make_product("Krem variant copy", external_data={"source_variant_id": 1})
    _rebuild()

    with CaptureQueriesContext(connection) as queries:
        response = APIClient().get("/api/catalog/products/search", {"q": "krem"})

    assert response.status_code == 200
    assert [row["id"] for row in response.data] == [public.pk]
    for sql in (q["sql"] for q in queries.captured_queries if "catalog_productsearchindex" in q["sql"]):
        assert '"catalog_product"."external_data" ?' not in sql


def test_search_page_queries_are_counted(make_product):
    """Учёт запросов: страница /search (search_source=page) пишет запрос, число найденного и то,
    как он понят; подсказки в шапке и «Показать ещё» не пишут ничего."""
    from apps.catalog.models_search import SearchQueryStat

    make_product("Парацетамол 500 мг")
    _rebuild()
    page = {"view": "card", "include_facets": "false", "search_source": "page"}

    for query in ("Парацитамол", "парацитамол", "шуба"):
        assert APIClient().get(URL, {"search": query, **page}).status_code == 200
    APIClient().get(URL, {"search": "парац", "view": "card", "page_size": 6})  # подсказка
    APIClient().get(URL, {"search": "парацетамол", "page": 2, **page})  # «Показать ещё»

    APIClient().get(URL, {"search": "парацетамол", "product_type": "books", **page})  # с фильтром

    rows = {row.query: row for row in SearchQueryStat.objects.all()}
    assert set(rows) == {"парацитамол", "шуба"}
    typo = rows["парацитамол"]
    assert (typo.searches, typo.results, typo.mode, typo.corrected_query) == (2, 1, "typo", "парацетамол")
    assert (rows["шуба"].searches, rows["шуба"].results, rows["шуба"].corrected_query) == (1, 0, "")


def test_search_stat_failure_does_not_break_search(make_product, monkeypatch):
    from apps.catalog import search_stats

    make_product("Парацетамол 500 мг")
    _rebuild()
    monkeypatch.setattr(search_stats.SearchQueryStat.objects, "filter", lambda **kwargs: 1 / 0)

    response = APIClient().get(URL, {"search": "парацетамол", "search_source": "page", "view": "card"})
    assert response.status_code == 200 and response.data["count"] == 1


def test_search_queries_admin_list_and_not_found_filter(db, rf):
    from django.contrib import admin
    from django.contrib.auth import get_user_model

    from apps.catalog.models_search import SearchQueryStat

    SearchQueryStat.objects.create(query="шуба", searches=7, results=0)
    SearchQueryStat.objects.create(query="мидокалм", searches=3, results=7)
    SearchQueryStat.objects.create(query="парацитамол", searches=2, results=1, mode="typo", corrected_query="парацетамол")
    admin_user = get_user_model().objects.create_superuser(
        username="search-admin", email="search-admin@example.com", password="x" * 12
    )
    model_admin = admin.site._registry[SearchQueryStat]

    def rows(params=""):
        request = rf.get(f"/admin/catalog/searchquerystat/{params}")
        request.user = admin_user
        return list(model_admin.get_changelist_instance(request).get_queryset(request))

    everything = rows()
    assert [row.query for row in everything] == ["шуба", "мидокалм", "парацитамол"]  # частые сверху
    assert model_admin.understood(everything[2]) == "исправлена опечатка → «парацетамол»"
    assert 'href="/search?query=' in model_admin.open_search(everything[0])
    assert [row.query for row in rows("?found=none")] == ["шуба"]
    assert [row.query for row in rows("?found=fixed")] == ["парацитамол"]


def test_search_facets_types_brands_and_filters(make_product):
    """Фильтры страницы /search: разделы и бренды найденного с количеством; после выбора
    фильтра список разделов и брендов не схлопывается, а выдача сужается и сортируется."""
    nike = Brand.objects.create(name="Nike", slug=f"nike-{uuid.uuid4().hex[:6]}")
    puma = Brand.objects.create(name="Puma", slug=f"puma-{uuid.uuid4().hex[:6]}")
    shoes = [
        make_product("Run Sneaker", brand=nike, product_type="shoes"),
        make_product("Run Sneaker Pro", brand=nike, product_type="shoes"),
        make_product("Run Sneaker Lite", brand=puma, product_type="shoes"),
    ]
    Product.objects.filter(pk=shoes[0].pk).update(price=Decimal("300.00"))
    Product.objects.filter(pk=shoes[1].pk).update(price=Decimal("100.00"), is_available=False)
    Product.objects.filter(pk=shoes[2].pk).update(price=Decimal("200.00"))
    shirt = make_product("Run Shirt", brand=puma, product_type="clothing")
    _rebuild()
    base = {"search": "run", "view": "card", "include_facets": "false", "search_facets": "1"}

    data = APIClient().get(URL, base).data
    assert data["count"] == 4
    assert data["search_facets"]["types"] == [{"value": "shoes", "count": 3}, {"value": "clothing", "count": 1}]
    assert [(row["name"], row["count"]) for row in data["search_facets"]["brands"]] == [("Nike", 2), ("Puma", 2)]

    data = APIClient().get(URL, {**base, "product_type": "shoes", "brand_id": nike.pk, "ordering": "price_asc"}).data
    assert [row["id"] for row in data["results"]] == [shoes[1].pk, shoes[0].pk]
    assert len(data["search_facets"]["types"]) == 2 and len(data["search_facets"]["brands"]) == 2
    data = APIClient().get(URL, {**base, "product_type": "shoes", "is_available": "true"}).data
    assert {row["id"] for row in data["results"]} == {shoes[0].pk, shoes[2].pk}
    assert "search_facets" not in APIClient().get(URL, {"search": "run", "view": "card"}).data  # подсказкам не нужны
    assert shirt.pk in _ids({"search": "run"})
