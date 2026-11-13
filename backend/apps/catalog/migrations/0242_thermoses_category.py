"""Подраздел «Термосы и термокружки» в «Посуде → Стаканы и бокалы» (решение владельца 13.11.2026).

Раздел ``thermoses`` давно описан в ``TABLEWARE_SUBCATEGORIES``, и раскладка SuperStep и SPX
кладёт туда термосы, но на проде раздела не было: товар падал в родителя «Стаканы и бокалы».
Здесь — для прода, без сети и R2. Мета-поля — по образцу соседних подразделов («Кружки»,
«Чашки»), наценка не задана: наследуется. Уже существующий раздел миграция не трогает.
"""

from django.db import migrations

SLUG = "thermoses"
PARENT_SLUG = "drinkware"
NAME_RU = "Термосы и термокружки"
NAME_EN = "Thermoses & Travel Mugs"
DESCRIPTION_RU = "Термосы, термокружки и термобутылки"
DESCRIPTION_EN = "Thermoses, travel mugs and insulated bottles"
# Место в списке подразделов — как у сида (порядковый номер в TABLEWARE_SUBCATEGORIES).
SORT_ORDER = 6


def create_category(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    CategoryTranslation = apps.get_model("catalog", "CategoryTranslation")
    parent = Category.objects.filter(slug=PARENT_SLUG).select_related("parent").first()
    if parent is None or Category.objects.filter(slug=SLUG).exists():
        return  # пустая база (тесты, новый стенд) — раздел создаст сид
    meta_title = f"{NAME_RU} | {parent.name} | Mudaroba"
    root_name = parent.parent.name if parent.parent_id else ""
    keywords = ", ".join(part for part in (NAME_RU, parent.name, root_name, "thermoses") if part)
    category = Category.objects.create(
        slug=SLUG,
        name=NAME_RU,
        description=DESCRIPTION_RU,
        category_type=parent.category_type,
        parent=parent,
        is_active=True,
        sort_order=SORT_ORDER,
        meta_title=meta_title,
        meta_description=DESCRIPTION_RU,
        meta_keywords=keywords,
        og_title=meta_title,
        og_description=DESCRIPTION_RU,
    )
    CategoryTranslation.objects.bulk_create(
        [
            CategoryTranslation(category=category, locale="ru", name=NAME_RU, description=DESCRIPTION_RU),
            CategoryTranslation(category=category, locale="en", name=NAME_EN, description=DESCRIPTION_EN),
        ]
    )


def delete_category(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Product = apps.get_model("catalog", "Product")
    category = Category.objects.filter(slug=SLUG).first()
    # Откат не удаляет раздел, в котором уже есть товары или подразделы.
    if category and not Product.objects.filter(category=category).exists() and not Category.objects.filter(parent=category).exists():
        category.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0241_medicine_is_hospital"),
    ]

    operations = [
        migrations.RunPython(create_category, delete_category),
    ]
