"""Подраздел «Скейтбординг и ролики» в «Спорттоварах» (решение владельца 13.11.2026).

Скейтборды и шлем для скейта Intersport лежали в корне «Спорттоваров»: своего раздела у них
не было. Раздел — тот же, что в ``SPORTS_SUBCATEGORIES`` (сид создаёт его на новом стенде);
здесь — для прода, без сети и R2. Мета-поля — по образцу соседних подразделов
(«Название | Спорттовары | Mudaroba»), наценка не задана: наследуется от «Спорттоваров».
Уже существующий раздел (заведённый руками или сидом) миграция не трогает.
"""

from django.db import migrations

SLUG = "skateboarding-roller"
NAME_RU = "Скейтбординг и ролики"
NAME_EN = "Skateboarding & Roller"
DESCRIPTION_RU = "Скейтборды, роликовые коньки и защита"
DESCRIPTION_EN = "Skateboards, roller skates and protective gear"
# Место в списке подразделов — как у сида (порядковый номер в SPORTS_SUBCATEGORIES).
SORT_ORDER = 10


def create_category(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    CategoryTranslation = apps.get_model("catalog", "CategoryTranslation")
    sports = Category.objects.filter(slug="sports", parent__isnull=True).first()
    if sports is None or Category.objects.filter(slug=SLUG).exists():
        return  # пустая база (тесты, новый стенд) — раздел создаст сид
    meta_title = f"{NAME_RU} | {sports.name} | Mudaroba"
    category = Category.objects.create(
        slug=SLUG,
        name=NAME_RU,
        description=DESCRIPTION_RU,
        category_type=sports.category_type,
        parent=sports,
        is_active=True,
        sort_order=SORT_ORDER,
        meta_title=meta_title,
        meta_description=DESCRIPTION_RU,
        meta_keywords=f"{NAME_RU}, {sports.name}, skateboarding roller",
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
        ("catalog", "0239_medicines_supplements_delivery_terms"),
    ]

    operations = [
        migrations.RunPython(create_category, delete_category),
    ]
