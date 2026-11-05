"""Разделы по спросу в рунете: показ по умолчанию, запись с бэкапом, повтор ничего не меняет."""

import json

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import Category, CategoryTranslation


def _category(slug, name, parent=None, **extra):
    category = Category.objects.create(slug=slug, name=name, parent=parent, **extra)
    CategoryTranslation.objects.create(category=category, locale="ru", name=name)
    return category


@pytest.fixture
def tree(db):
    clothing = _category("clothing-root-x", "Одежда")
    _category("knitwear", "Трикотаж", clothing)
    _category("hoodies", "Худии", clothing, meta_title="Худии | Трикотаж | Mudaroba")
    bags = _category("bags-wallets", "Сумки и кошельки")
    _category("drinkware", "Стаканы и бокалы")
    sandals = _category("sandals", "Сандалии")
    _category("slides", "Слайды", sandals, meta_title="Слайды | Сандалии | Mudaroba", meta_description="Ручное описание")
    _category("flip-flops", "Шлёпанцы", sandals)
    return bags


def test_dry_run_changes_nothing(tree):
    call_command("ensure_demand_categories")

    assert not Category.objects.filter(slug__in=["fleece", "backpacks", "thermoses"]).exists()
    assert Category.objects.get(slug="slides").name == "Слайды"


def test_apply_requires_backup(tree):
    with pytest.raises(CommandError):
        call_command("ensure_demand_categories", "--apply")


def test_apply_creates_and_renames_with_backup(tree, tmp_path):
    backup = tmp_path / "categories.json"
    call_command("ensure_demand_categories", "--apply", "--backup", str(backup))

    backpacks = Category.objects.get(slug="backpacks")
    assert backpacks.parent == tree and backpacks.is_active
    assert set(backpacks.translations.values_list("locale", "name")) == {("ru", "Рюкзаки"), ("en", "Backpacks")}
    assert Category.objects.get(slug="thermoses").parent.slug == "drinkware"
    assert Category.objects.get(slug="fleece").parent.slug == "knitwear"

    slides = Category.objects.get(slug="slides")
    assert slides.name == "Шлёпанцы"
    assert slides.meta_title == ""  # шаблон со старым названием очищен
    assert slides.meta_description == "Ручное описание"  # без старого названия — не трогаем
    assert slides.translations.get(locale="ru").name == "Шлёпанцы"
    assert Category.objects.get(slug="flip-flops").name == "Сланцы и вьетнамки"
    assert Category.objects.get(slug="hoodies").name == "Толстовки и худи"

    saved = json.loads(backup.read_text(encoding="utf-8"))
    assert {row["slug"]: row["name"] for row in saved["renamed"]} == {
        "flip-flops": "Шлёпанцы",
        "slides": "Слайды",
        "hoodies": "Худии",
    }

    call_command("ensure_demand_categories", "--apply", "--backup", str(tmp_path / "again.json"))
    assert Category.objects.filter(slug="backpacks").count() == 1
    assert not (tmp_path / "again.json").exists()  # изменений нет — бэкап не пишется


def test_manual_rename_is_kept(tree):
    Category.objects.filter(slug="slides").update(name="Слайды и шлёпанцы")
    call_command("ensure_demand_categories", "--apply", "--backup", "/dev/null")

    assert Category.objects.get(slug="slides").name == "Слайды и шлёпанцы"
