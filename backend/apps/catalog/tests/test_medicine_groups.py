"""Страницы препаратов (/drugs/<slug>): формы бренда, запрет продвижения, ссылка с карточки."""

import importlib
import json
from decimal import Decimal

import pytest
from django.apps import apps as django_apps
from django.core.cache import cache
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from apps.catalog.controlled_substances import DATA_PATH, restrictions
from apps.catalog.models import Category, MedicineGroup, MedicineGroupTranslation, MedicineProduct, Product
from apps.catalog.views import MedicineProductViewSet

group_texts = importlib.import_module("apps.catalog.migrations.0225_medicine_group_texts")


def _medicine_slugs(**params):
    view = MedicineProductViewSet()
    view.request = Request(APIRequestFactory().get("/api/catalog/medicines/products", params))
    view.action = "list"
    return set(view.get_queryset().values_list("slug", flat=True))


@pytest.fixture
def catalog(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    cache.clear()
    # Данные миграции 0225: транзакционные тесты могли очистить таблицы до этого теста
    group_texts.create_groups(django_apps, None)

    def category(slug, name, parent=None):
        return Category.objects.update_or_create(slug=slug, defaults={"name": name, "parent": parent})[0]

    root = category("medicines", "Medicine")
    painkillers = category("painkillers", "Pain", root)

    def create(slug, name, *, ingredient="", prescription="Beyaz Reçete", category=painkillers, atc=""):
        base = Product.objects.create(
            name=name, slug=slug, product_type="medicines", category=category,
            price=Decimal("10.00"), currency="TRY", is_active=True,
        )
        # update() обходит сигнал TD-024 — отметку «ввоз ограничен» ставим тем же расчётом
        MedicineProduct.objects.filter(base_product=base).update(
            active_ingredient=ingredient, prescription_type=prescription, atc_code=atc,
            import_restricted_countries=restrictions(ingredient)[0],
        )
        return MedicineProduct.objects.get(base_product=base)

    create("majezik-100", "MAJEZIK 100 MG 15 FILM TABLET", ingredient="Flurbiprofen")
    create("majezik-sprey", "MAJEZIK % 0.25 ORAL SPREY, COZELTI 30 ML", ingredient="Flurbiprofen")
    create("majezik-ru", "MAJEZIK (флурбипрофен) 100 мг, таблетки", ingredient="Флурбипрофен")
    create("majezikplus", "MAJEZIKPLUS 50 MG", ingredient="Flurbiprofen")
    create("a-ferin-zero", "A-FERIN ZERO 120 MG/5 ML PEDIATRIK SURUP", ingredient="Parasetamol")
    create("a-ferin-codeine", "A-FERIN 300 MG/2 MG/10 MG KAPSUL", ingredient="Klorfeniramin Maleat + Kodein Fosfat + Parasetamol",
           prescription="Kontrole Tabi Reçete")
    create("a-ferin-plus", "A-FERIN PLUS PEDIYATRIK SURUP", ingredient="Klorfeniramin Maleat + Psödoefedrin Hidroklorür")
    tylol = MedicineGroup.objects.create(slug="tylolhot", name="TYLOLHOT")
    MedicineGroupTranslation.objects.create(group=tylol, locale="ru", name="Тайлолхот")
    create("tylolhot-day", "TYLOLHOT DAY 500 MG + 30 MG + 2 MG", ingredient="Parasetamol + Psödoefedrin Hidroklorür + Klorfeniramin")
    return {"root": root, "painkillers": painkillers, "create": create}


@pytest.mark.parametrize("ingredient, restricted", [
    ("Klorfeniramin Maleat + Psödoefedrin Hidroklorür", True),
    ("Klorfeniramin Maleat + Kodein Fosfat + Parasetamol", True),
    ("Parasetamol + Psödoefedrin Hidroklorür + Klorfeniramin", True),
    ("Klorfeniramin Maleat + Parasetamol", False),
    ("Flurbiprofen", False),
    ("Desloratadin", False),
    ("Levotiroksin Sodyum", False),
])
def test_drug_pages_rely_on_td024_mark_for_codeine_and_pseudoephedrine(ingredient, restricted):
    # Страницы препаратов отсекают формы по отметке TD-024 — справочник должен ловить эти вещества
    assert bool(restrictions(ingredient)[0]) is restricted


def test_group_rule_needs_separator_after_brand():
    group = MedicineGroup(name="MAJEZIK")
    assert group.matches_name("MAJEZIK 100 MG")
    assert group.matches_name("majezik, спрей")
    assert group.matches_name("MAJEZIK (флурбипрофен) 100 мг")
    assert group.matches_name("MAJEZIK")
    assert not group.matches_name("MAJEZIKPLUS 50 MG")
    assert not group.matches_name("SUPER MAJEZIK 100 MG")
    assert MedicineGroup(name="TAMOXIFEN", name_prefixes="TAMOXIFEN, NOLVADEX").matches_name("NOLVADEX 10 MG")


@pytest.mark.django_db
def test_drug_group_products_are_brand_forms_without_restricted(catalog):
    assert _medicine_slugs(drug_group="majezik") == {"majezik-100", "majezik-sprey", "majezik-ru"}
    # A-FERIN создан выключенным (в линейке есть формы с кодеином и псевдоэфедрином)
    assert _medicine_slugs(drug_group="a-ferin") == set()
    MedicineGroup.objects.filter(slug="a-ferin").update(is_active=True)
    # Включённый владельцем: формы с кодеином и псевдоэфедрином на страницу не попадают
    assert _medicine_slugs(drug_group="a-ferin") == {"a-ferin-zero"}
    assert _medicine_slugs(drug_group="unknown") == set()
    MedicineGroup.objects.filter(slug="majezik").update(is_active=False)
    assert _medicine_slugs(drug_group="majezik") == set()


@pytest.mark.django_db
def test_drug_group_detail_returns_texts_and_404_without_visible_forms(catalog):
    client = APIClient()

    response = client.get("/api/catalog/medicine-groups/majezik")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "MAJEZIK"
    assert body["forms_count"] == 3
    assert body["prescription"] is True
    assert body["cold_chain"] is False
    ru = next(t for t in body["translations"] if t["locale"] == "ru")
    assert ru["name"] == "Мажезик"
    assert ru["active_ingredient"] == "флурбипрофен"
    assert ru["indications"] and ru["usage_summary"]

    # Все формы TYLOLHOT содержат псевдоэфедрин — страницы нет
    assert client.get("/api/catalog/medicine-groups/tylolhot").status_code == 404
    assert client.get("/api/catalog/medicine-groups/unknown").status_code == 404


@pytest.mark.django_db
def test_drug_group_marks_cold_chain_and_otc_by_source_fields(catalog):
    group = MedicineGroup.objects.create(slug="ozempic", name="OZEMPIC")
    MedicineGroupTranslation.objects.create(group=group, locale="ru", name="Оземпик")
    pen = catalog["create"]("ozempic-1", "OZEMPIC 1 MG KALEM", ingredient="Semaglutid", prescription="Reçetesiz")
    MedicineProduct.objects.filter(pk=pen.pk).update(storage_conditions="2°C - 8°C arasında buzdolabında saklayınız.")

    body = APIClient().get("/api/catalog/medicine-groups/ozempic").json()
    assert body["cold_chain"] is True
    assert body["prescription"] is False


@pytest.mark.django_db
def test_sitemap_lists_only_drug_groups_with_visible_forms(catalog):
    response = APIClient().get("/api/catalog/sitemap-entries", {"kind": "drug_groups"})
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.json()["results"]}
    assert "majezik" in slugs
    assert "tylolhot" not in slugs
    assert "a-ferin" not in slugs  # выключен миграцией
    assert "crestor" not in slugs  # у бренда из миграции нет товаров в этой базе


@pytest.mark.django_db
def test_resolve_links_medicine_card_to_its_drug_page(catalog):
    client = APIClient()

    body = client.get("/api/catalog/products/resolve/majezik-100", HTTP_ACCEPT_LANGUAGE="ru").json()
    assert body["drug_group"] == {"slug": "majezik", "name": "Мажезик", "latin": "MAJEZIK"}
    body = client.get("/api/catalog/products/resolve/majezik-100", HTTP_ACCEPT_LANGUAGE="en").json()
    assert body["drug_group"]["name"] == "Majezik"

    # Выключенный препарат и форма с кодеином на страницу не ссылаются
    assert client.get("/api/catalog/products/resolve/a-ferin-zero").json()["drug_group"] is None
    MedicineGroup.objects.filter(slug="a-ferin").update(is_active=True)
    cache.clear()
    assert client.get("/api/catalog/products/resolve/a-ferin-zero").json()["drug_group"]["slug"] == "a-ferin"
    assert client.get("/api/catalog/products/resolve/a-ferin-codeine").json()["drug_group"] is None
    assert client.get("/api/catalog/products/resolve/majezikplus").json()["drug_group"] is None


def _all_texts(item):
    for locale in ("ru", "en"):
        yield from (str(value) for value in item[locale].values())


def test_drug_group_texts_are_complete_and_follow_seo_restrictions():
    banned_phrases = ("без рецепта", "без назначения", "without a prescription", "without prescription", "купить")
    entries = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    # Названия контролируемых веществ из справочника TD-024 (по первому слову, от 5 букв)
    stems = {
        word.lower()
        for entry in entries
        for name in [entry.get("inn_ru"), entry.get("inn_en"), *(entry.get("tr_keys") or [])]
        for word in str(name or "").split()[:1]
        if len(word) >= 5
    }
    slugs = [item["slug"] for item in group_texts.GROUPS]
    assert len(slugs) == len(set(slugs))
    assert "tylolhot" not in slugs
    inactive = {item["slug"] for item in group_texts.GROUPS if item.get("is_active") is False}
    assert inactive == {"a-ferin", "katarin", "aerius"}
    for item in group_texts.GROUPS:
        for locale in ("ru", "en"):
            for field in ("name", "active_ingredient", "indications", "usage_summary"):
                assert item[locale][field].strip(), (item["slug"], locale, field)
        for text in _all_texts(item):
            lowered = text.lower()
            assert not any(phrase in lowered for phrase in banned_phrases), (item["slug"], text)
            assert not any(stem in lowered for stem in stems), (item["slug"], text)
