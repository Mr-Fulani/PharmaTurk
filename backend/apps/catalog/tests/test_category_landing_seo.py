"""SEO разделов через Claude: отбор разделов, факты, проверка ответа и запись в пустые поля."""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.models import Brand, Category, CategoryTranslation, Product
from apps.catalog.services.category_landing_seo import (
    apply_texts,
    collect_facts,
    generate_texts,
    select_categories,
    validate_texts,
)

BODY_RU = " ".join(["Раздел собран из товаров турецких брендов, состав указан на упаковке."] * 9)
BODY_EN = " ".join(["The section brings together products of Turkish brands, see the label."] * 9)


def _texts(**overrides):
    texts = {
        "ru": {
            "h1": "Турецкие витамины группы B",
            "meta_title": "Витамины B из Турции: Solgar, Venatura | Mudaroba",
            "meta_description": (
                "Комплексы витаминов группы B из Турции: капсулы и таблетки брендов Solgar и Venatura. "
                "Отправьте заявку — менеджер рассчитает стоимость с доставкой."
            ),
            "seo_text": f"{BODY_RU}\n\n## Как заказать\n\n{BODY_RU}",
        },
        "en": {
            "h1": "Turkish B Vitamin Supplements",
            "meta_title": "B Vitamins from Turkey: Solgar, Venatura | Mudaroba",
            "meta_description": (
                "B vitamin complexes from Turkey: capsules and tablets by Solgar and Venatura. "
                "Send a request and a manager will quote the price with delivery."
            ),
            "seo_text": f"{BODY_EN}\n\n## How to order\n\n{BODY_EN}",
        },
    }
    for key, value in overrides.items():
        locale, field = key.split("__")
        texts[locale][field] = value
    return texts


@pytest.fixture
def catalog(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)

    def category(slug, name, parent=None):
        return Category.objects.update_or_create(slug=slug, defaults={"name": name, "parent": parent, "is_active": True})[0]

    supplements = category("supplements", "БАДы")
    vitamins = category("lsv-vitamins", "Витамины", supplements)
    vitamin_b = category("lsv-vitamin-b", "Витамин B", vitamins)
    empty = category("lsv-empty", "Пустой", vitamins)
    medicines = category("medicines", "Медикаменты")
    cardio = category("lsv-cardio", "Сердце", medicines)
    solgar = Brand.objects.create(name="Solgar", slug="lsv-solgar")
    venatura = Brand.objects.create(name="Venatura", slug="lsv-venatura")
    for index, brand in enumerate([solgar, solgar, venatura]):
        Product.objects.create(
            name=f"Витамин B комплекс {index}", slug=f"lsv-b-{index}", category=vitamin_b,
            product_type="supplements", brand=brand, price=Decimal("1"),
        )
    Product.objects.create(name="Кардио", slug="lsv-cardio-1", category=cardio, price=Decimal("1"))
    return SimpleNamespace(supplements=supplements, vitamins=vitamins, vitamin_b=vitamin_b, empty=empty, cardio=cardio)


def test_valid_texts_have_no_problems():
    assert validate_texts(_texts()) == []


@pytest.mark.parametrize(
    "override, expected",
    [
        ({"ru__seo_text": BODY_RU + "\n\n## Польза\n\nВитамины лечат усталость. " + BODY_RU}, "запрещено «леч»"),
        ({"ru__meta_description": "В разделе 1 371 товар из Турции: витамины группы B брендов Solgar и Venatura, заявка менеджеру."}, "число"),
        ({"ru__meta_title": "Витамины B из Турции — Mudaroba"}, "ru.meta_title"),
        ({"en__h1": "Витамины B from Turkey"}, "en.h1: кириллица"),
        ({"en__meta_description": "The best B vitamins from Turkey: capsules and tablets by Solgar and Venatura with delivery on request."}, "запрещено «best»"),
        ({"ru__seo_text": BODY_RU}, "нет подзаголовков"),
    ],
)
def test_validation_flags_promises_counts_and_format(override, expected):
    problems = validate_texts(_texts(**override))
    assert any(expected in problem for problem in problems), problems


@pytest.mark.django_db
def test_select_skips_medicines_empty_and_filled_categories(catalog):
    selected = {c.slug for c in select_categories(roots=["supplements", "medicines"])}
    assert {"supplements", "lsv-vitamins", "lsv-vitamin-b"} <= selected
    assert "lsv-empty" not in selected
    assert "lsv-cardio" not in selected

    CategoryTranslation.objects.create(category=catalog.vitamin_b, locale="ru", name="Витамин B", seo_text="Текст")
    assert "lsv-vitamin-b" not in {c.slug for c in select_categories(slugs=["lsv-vitamin-b"])}
    assert "lsv-vitamin-b" in {c.slug for c in select_categories(slugs=["lsv-vitamin-b"], include_filled=True)}


@pytest.mark.django_db
def test_facts_contain_only_nonempty_sections_and_real_brands(catalog):
    facts = collect_facts(catalog.vitamins)
    assert facts["parents"] == ["БАДы"]
    assert facts["subsections"] == ["Витамин B"]
    assert facts["brands"] == ["Solgar", "Venatura"]
    assert "Витамин B комплекс 0" in facts["product_examples"]
    assert facts["is_supplements"] is True
    assert facts["delivery"] == "доставка 7–21 рабочий день"


def test_generate_parses_fenced_json():
    class FakeClient:
        def create(self, system_prompt, user_prompt, *, json_mode, max_tokens):
            assert "Solgar" in user_prompt and json_mode
            return "```json\n" + json.dumps(_texts(), ensure_ascii=False) + "\n```", SimpleNamespace(usage="u")

    texts, usage = generate_texts({"brands": ["Solgar"]}, FakeClient())
    assert texts == _texts()
    assert usage == "u"


@pytest.mark.django_db
def test_apply_fills_only_empty_fields_and_keeps_backup(catalog):
    CategoryTranslation.objects.create(category=catalog.vitamins, locale="ru", name="Витамины", h1="Своё из админки")
    entries = [{"slug": "lsv-vitamins", "name_en": "Vitamins", "texts": _texts()}]

    changes, _ = apply_texts(entries, dry_run=True)
    assert changes and CategoryTranslation.objects.get(category=catalog.vitamins, locale="ru").seo_text == ""

    changes, backup = apply_texts(entries)
    ru = CategoryTranslation.objects.get(category=catalog.vitamins, locale="ru")
    en = CategoryTranslation.objects.get(category=catalog.vitamins, locale="en")
    assert ru.h1 == "Своё из админки"
    assert ru.meta_title == _texts()["ru"]["meta_title"]
    assert en.name == "Vitamins" and en.seo_text == _texts()["en"]["seo_text"]
    assert {"slug": "lsv-vitamins", "locale": "ru", "created": False, "meta_title": "",
            "meta_description": "", "seo_text": ""} in backup

    changes, _ = apply_texts(entries)
    assert changes == []


@pytest.mark.django_db
def test_apply_command_refuses_draft_with_problems(catalog, tmp_path):
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps([{"slug": "lsv-vitamins", "texts": _texts(ru__h1="")}], ensure_ascii=False))
    with pytest.raises(CommandError, match="lsv-vitamins"):
        call_command("category_landing_seo", "apply", "--file", str(draft), "--backup", str(tmp_path / "b.json"))
    assert not CategoryTranslation.objects.filter(category=catalog.vitamins).exists()
