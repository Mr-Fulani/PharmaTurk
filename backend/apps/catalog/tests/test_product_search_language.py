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
from apps.catalog.product_search import iter_search_rows, kind_words, search_plan
from apps.catalog.search_language import (
    closest_word, edit_distance, latin_to_cyrillic, letter_twin, stem, switch_layout, typo_limit,
)

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


def test_medicine_trade_name_in_cyrillic_after_ai_title(make_medicine):
    """Обработанное лекарство: name — русское название с МНН в скобках, бренд для словаря
    берётся из турецкого оригинала (21.11.2026: «тайлол» находил 6 карточек TYLOL из 14)."""
    remember(BRAND_NAMESPACE, {
        "TYLOL": {"ru": "Тайлол", "en": "TYLOL"}, "TYLOL HOT": {"ru": "Тайлол Хот", "en": "TYLOL HOT"},
    })
    stored = make_medicine("TYLOL (парацетамол) 500 мг, таблетки, 20 шт.", manufacturer="Nobel")
    Product.objects.filter(pk=stored.base_product_id).update(external_data={"source_name": "TYLOL 500 MG 20 TABLET"})
    # Оригинал не сохранён: название — строка вкладки аналогов с тем же штрихкодом.
    listed = make_medicine("TYLOL HOT (парацетамол + фенилэфрин), порошок, 12 шт.", manufacturer="Nobel")
    Product.objects.filter(pk=listed.base_product_id).update(external_data={"attributes": {
        "barcode": "8699000000017",
        "source_tabs": {"equivalents": {"text": "TYLOL HOT 12 POSET\nBARKOD: 8699000000017"}},
    }})
    _rebuild()

    rows = dict(iter_search_rows([stored.base_product_id, listed.base_product_id]))
    assert "тайлол" in rows[stored.base_product_id]["text"]
    assert "тайлол" in rows[listed.base_product_id]["text"]
    assert _ids({"search": "тайлол"}) == [stored.base_product_id, listed.base_product_id]


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


def test_synonym_keys_match_word_forms():
    from apps.catalog.search_language import QUERY_REPLACEMENTS, QUERY_SYNONYMS

    for word in ("детей", "тапочки", "ребенка", "женщинам", "мальчиков", "кроссы"):
        assert stem(word) in QUERY_SYNONYMS or stem(word) in QUERY_REPLACEMENTS, word


def test_synonyms_do_not_find_other_words(make_product):
    sneakers = make_product("Erkek Sneaker")
    make_product("PHYTOIL Кедровая вода, 100 мл")
    make_product("Кроссворды Пророки")
    make_product("NEUJOYS PUFFER спрей")
    _rebuild()

    assert _ids({"search": "кроссы"}) == [sneakers.pk]
    assert _ids({"search": "кеды"}) == [sneakers.pk]
    assert _ids({"search": "кроссовки"}) == [sneakers.pk]
    assert _ids({"search": "пуховик"}) == []


def test_prepositions_are_optional(make_product):
    nasal = make_product("OTRIVIN Назальный спрей 0,1%")
    burun = make_product("Burun Damlası")
    shampoo = make_product("Шампунь и кондиционер 2 в 1")
    tea = make_product("Чай травяной с ромашкой")
    make_product("Носки хлопковые")
    _rebuild()

    assert set(_ids({"search": "капли в нос"})) == {nasal.pk, burun.pk}
    assert _ids({"search": "шампунь 2 в 1"}) == [shampoo.pk]
    assert _ids({"search": "чай с ромашкой"}) == [tea.pk]
    assert _ids({"search": "крем для рук и ног"}) == []  # предлоги не находят «Носки» сами по себе


def test_short_brand_word_and_new_balance(make_product):
    on = make_product("Cloudmonster Erkek Sneaker", brand=_brand("On"))
    make_product("Sezon Erkek Sneaker")  # «он» внутри слова не считается
    nb = make_product("574 Erkek Sneaker", brand=_brand("New Balance"))
    _rebuild()

    assert _ids({"search": "кроссовки он"}) == [on.pk]
    assert _ids({"search": "нью баланс"}) == [nb.pk]
    assert _ids({"search": "нью беланс"}) == [nb.pk]


def test_rebuild_has_no_query_per_product(make_product):
    top = Category.objects.create(name="Обувь", slug=f"c-{uuid.uuid4().hex[:8]}")
    mid = Category.objects.create(name="Женская обувь", slug=f"c-{uuid.uuid4().hex[:8]}", parent=top)
    leaf = Category.objects.create(name="Кроссовки", slug=f"c-{uuid.uuid4().hex[:8]}", parent=mid)
    great = Category.objects.create(name="Ещё ниже", slug=f"c-{uuid.uuid4().hex[:8]}", parent=leaf)
    make_product("One", category=great)
    with CaptureQueriesContext(connection) as one:
        rows = dict(iter_search_rows())
    for index in range(5):
        make_product(f"More {index}", category=great)
    with CaptureQueriesContext(connection) as many:
        dict(iter_search_rows())
    assert len(many) == len(one)
    assert "женская обувь" in next(iter(rows.values()))["text"]


def test_long_garbage_query_is_bounded(make_product):
    make_product("Парацетамол 500 мг")
    _rebuild()
    garbage = " ".join(f"щжфывапролд{index}х" for index in range(30))
    with CaptureQueriesContext(connection) as queries:
        assert _ids({"search": garbage}) == []
    search_sql = [q for q in queries if "catalog_productsearchindex" in q["sql"] or "word_similarity" in q["sql"]]
    assert len(search_sql) <= 10, [q["sql"][:80] for q in search_sql]


def test_section_search_chooses_plan_once(make_product):
    make_product("Парацетамол 500 мг")
    _rebuild()
    with CaptureQueriesContext(connection) as queries:
        response = APIClient().get("/api/catalog/clothing/products", {"search": "gfhfwtnfvjk"})
    assert response.status_code == 200
    checks = [q for q in queries if q["sql"].startswith('SELECT 1 AS "a" FROM "catalog_productsearchindex"')]
    # индекс заполнен? + запрос как есть + раскладка — один раз, хотя get_queryset вызывается 3–4 раза
    assert len(checks) == 3, [q["sql"][:120] for q in checks]


def test_no_correction_note_when_nothing_visible(make_product):
    hidden = make_product("Парацетамол 500 мг")
    _rebuild()
    Product.objects.filter(pk=hidden.pk).update(is_active=False)
    data = _search("gfhfwtnfvjk")
    assert data["count"] == 0 and "search_info" not in data


def test_pharmacy_names_find_by_substance(make_product):
    """Прод 23.11.2026: «анальгин» находил PANALGINE, «найз» — органайзер IKEA, «мидокалм»
    исправлялся в MIDOLAM (мидазолам), «л-тироксин» — пусто."""
    metamizole = make_product("NOVALGIN (метамизол), 2 мл, 10 ампул")
    nimesulide = make_product("FRENAG (нимесулид) 1%, гель, 30 г")
    tolperisone = make_product("VYXTRA (толперизон) 50 мг, таблетки")
    thyroxine = make_product("LEVOTIRON (левотироксин) 100 мкг")
    make_product("Выдвижной органайзер для полки IKEA")
    make_product("MIDOLAM 5 мг/1 мл, раствор")
    make_product("PANALGINE (кофеин + пропифеназон), таблетки")
    _rebuild()

    data = _search("анальгин")
    assert [row["id"] for row in data["results"]] == [metamizole.pk]
    assert "search_info" not in data  # найдено по словарю, это не исправление
    assert _ids({"search": "анальгина"}) == [metamizole.pk]
    assert _ids({"search": "найз"}) == [nimesulide.pk]
    assert _ids({"search": "мидокалм"}) == [tolperisone.pk]
    assert _ids({"search": "л-тироксин"}) == [thyroxine.pk]


def test_pharmacy_dictionary_keys_are_stems():
    from apps.catalog.search_language import _PHARMACY_NAMES, _PHARMACY_SHORT_NAMES, QUERY_REPLACEMENTS, QUERY_SYNONYMS

    assert all(stem(name) in QUERY_SYNONYMS for name in _PHARMACY_NAMES)
    assert all(stem(name) in QUERY_REPLACEMENTS for name in _PHARMACY_SHORT_NAMES)
    # Вещество ищется частью слова: не короче 6 букв, чтобы не находить чужое.
    assert all(len(value) >= 6 for values in {**_PHARMACY_NAMES, **_PHARMACY_SHORT_NAMES}.values() for value in values)


def test_two_edits_only_in_long_words_and_unfinished_word(make_product):
    """«глюкофаж» → «глюконат», «диабетон» → «диабет» — две правки в слове из 8 букв давали
    другое слово. В подсказках запрос приходит недописанным: «нурафе» было пусто."""
    make_product("Цинк глюконат 10 мг")
    nurofen = make_product("Нурофен 200 мг")
    _rebuild()

    assert typo_limit("диабетон") == 1 and typo_limit("парацитам") == 2
    assert _ids({"search": "глюкотаж"}) == []
    data = _search("нурафе")
    assert [row["id"] for row in data["results"]] == [nurofen.pk]
    assert data["search_info"] == {"mode": "typo", "query": "нурофен"}
    # Дописывается только последнее слово и только с той же первой буквы:
    # «пальто» превращалось в «мальтодекстрин» (прод 23.11.2026).
    make_product("RETISOL Альфа-липоевая кислота, мальтодекстрин")
    _rebuild()
    assert _ids({"search": "пальто"}) == []
    assert _ids({"search": "нурафе 200"}) == []
    assert closest_word("нураф", ["нурофен 400"], unfinished=True) == "нурофен"
    assert closest_word("нураф", ["нурофен 400"]) == ""


def test_typo_candidates_do_not_scan_whole_index(make_product):
    """LIMIT в одном запросе с ``%>`` уводил планировщик в перебор таблицы (прод: 2 с на слово)."""
    make_product("Метформин 500 мг")
    _rebuild()
    with CaptureQueriesContext(connection) as queries:
        assert search_plan("метформн").query == "метформин"
    candidates = [q["sql"] for q in queries if "%>" in q["sql"]]
    assert candidates and all("AS MATERIALIZED" in sql for sql in candidates)


def test_extra_word_does_not_empty_results(make_product, monkeypatch):
    """В названии должно быть каждое слово: «мазь диклофенак» (в каталоге гель), «нурофен детский»
    давали пустую страницу. Убирается самое частое слово, о замене говорит search_info."""
    gel = make_product("TRUJEL (диклофенак) 5%, гель")
    nurofen = make_product("Нурофен 200 мг")
    for name in ("Мазь календулы", "Мазь ихтиоловая", "Детский крем", "Детский шампунь"):
        make_product(name)
    _rebuild()

    data = _search("мазь диклофенак")
    assert [row["id"] for row in data["results"]] == [gel.pk]
    assert data["search_info"] == {"mode": "partial", "query": "диклофенак"}
    data = _search("нурафен детский 200")  # опечатка исправляется до того, как убираются слова
    assert [row["id"] for row in data["results"]] == [nurofen.pk]
    assert data["search_info"] == {"mode": "partial", "query": "нурофен 200"}
    assert "search_info" not in _search("диклофенак гель")
    assert _ids({"search": "щшгнекуц абвгдежз"}) == []
    # Остаться должно редкое слово: «мазь» (2 товара) при пороге 1 — общее, не ответ.
    monkeypatch.setattr("apps.catalog.product_search._PARTIAL_SPECIFIC", 1)
    assert _ids({"search": "мазь детская"}) == []
    assert _ids({"search": "мазь диклофенак"}) == [gel.pk]
    with CaptureQueriesContext(connection) as queries:
        search_plan("мазь диклофенак")
    assert len(queries) <= 9, [q["sql"][:80] for q in queries]


def test_words_in_name_rank_before_matches_by_ingredient(make_product, make_medicine):
    """«витамин д3»: первым шёл сироп POLIVIT (короткое название, найден по составу),
    а «d3» одним словом находил шлем «Mod3»."""
    syrup = make_medicine("POLIVIT, сироп", active_ingredient="Витамин D3 + Витамин A")
    drops = make_product("NONDO Витамин D3, капли для приёма внутрь, 10 мл")
    make_product("Горнолыжный шлем Oakley Mod3")
    _rebuild()

    assert _ids({"search": "витамин д3"}) == [drops.pk, syrup.base_product_id]
    assert set(_ids({"search": "d3"})) == {drops.pk, syrup.base_product_id}
    tablets = make_product("Магний B6, 60 таблеток")
    _rebuild()
    assert _ids({"search": "магний б6 таблетки"}) == [tablets.pk]


def test_purpose_finds_medicines_of_the_group(make_product, make_medicine):
    """Прод 23.11.2026: «от головной боли», «жаропонижающее», «таблетки от давления» — пусто:
    в карточках таких слов нет. Назначение ищет лекарства лечебной группы по коду ATC."""
    parol = make_medicine("PAROL (парацетамол) 500 мг, таблетки, 20 шт.", atc_code="N02BE01")
    syrup = make_medicine("CALPOL (парацетамол) 120 мг/5 мл, детский сироп", atc_code="N02BE01")
    concor = make_medicine("CONCOR (бисопролол) 5 мг, таблетки", atc_code="C07AB07")
    herbal = make_product("ORGANIER Сироп от кашля, 120 мл")
    codeine = make_medicine("LEVOPRONT (леводропропизин), сироп", atc_code="R05DB27")
    make_product("Мужской головной убор Huf")
    _rebuild()

    medicine_ids = lambda *medicines: {medicine.base_product_id for medicine in medicines}  # noqa: E731
    assert set(_ids({"search": "от головной боли"})) == medicine_ids(parol, syrup)
    assert set(_ids({"search": "жаропонижающее"})) == medicine_ids(parol, syrup)
    assert _ids({"search": "жаропонижающее детское"}) == [syrup.base_product_id]
    assert _ids({"search": "таблетки от давления"}) == [concor.base_product_id]
    # Товар, где слова написаны, находится вместе с группой; «лекарство», «чем лечить» не мешают.
    assert set(_ids({"search": "лекарство от кашля"})) == {herbal.pk, codeine.base_product_id}
    assert set(_ids({"search": "чем лечить кашель"})) == {herbal.pk, codeine.base_product_id}
    assert "search_info" not in _search("от головной боли")


def test_purpose_keys_are_stems_and_codes_are_atc():
    import re

    from apps.catalog.search_language import _PURPOSES, PURPOSE_GROUPS, STOP_WORDS

    for phrases, codes in _PURPOSES:
        assert all(re.fullmatch(r"[a-z]\d{2}[a-z]{0,2}\d{0,2}", code) for code in codes), codes
        for phrase in phrases:
            key = tuple(stem(word) for word in phrase.split() if word not in STOP_WORDS)
            assert key and PURPOSE_GROUPS[key] == codes, phrase
    # Успокоительных, снотворных и антидепрессантов в словаре нет намеренно.
    assert not any(code.startswith(("n05", "n06")) for codes in PURPOSE_GROUPS.values() for code in codes)
