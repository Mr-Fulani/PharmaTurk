"""category_instruction: подкатегории наследуют шаблон корневой категории + seed-команда."""

import pytest
from django.core.management import call_command

from apps.ai.models import AITemplate
from apps.ai.services.content_generator import ContentGenerator
from apps.catalog.models import Category


@pytest.mark.django_db
def test_category_instruction_inherits_from_parent_category():
    root = Category.objects.create(name="Парфюмерия", slug="perfumery")
    child = Category.objects.create(name="Духи", slug="mens-parfum-edp", parent=root)
    AITemplate.objects.create(
        name="perf-instr",
        template_type="category_instruction",
        category=root,
        content="ПАРФЮМ-ИНСТРУКЦИЯ",
        is_active=True,
    )
    gen = ContentGenerator.__new__(ContentGenerator)  # без тяжёлого __init__

    # подкатегория наследует шаблон корня
    assert gen._get_prompt_template("category_instruction", "", category=child) == "ПАРФЮМ-ИНСТРУКЦИЯ"
    # сам корень тоже находит свой шаблон
    assert gen._get_prompt_template("category_instruction", "", category=root) == "ПАРФЮМ-ИНСТРУКЦИЯ"
    # несвязанная категория получает дефолт
    other = Category.objects.create(name="Книги", slug="books-x")
    assert gen._get_prompt_template("category_instruction", "DEFAULT", category=other) == "DEFAULT"


@pytest.mark.django_db
def test_seed_command_creates_perfumery_instruction():
    Category.objects.create(name="Парфюмерия", slug="perfumery")
    call_command("seed_ai_category_instructions")
    tpl = AITemplate.objects.get(template_type="category_instruction", category__slug="perfumery")
    assert tpl.is_active
    assert "парфюмери" in tpl.content.lower()
    # идемпотентность: повторный запуск не падает и не плодит дубли
    call_command("seed_ai_category_instructions")
    assert AITemplate.objects.filter(category__slug="perfumery", template_type="category_instruction").count() == 1
