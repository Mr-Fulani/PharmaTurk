from django.db import migrations
from django.utils.text import slugify


PRESETS = {
    "medicines": [
        ("Антибиотики", "antibiotics"),
        ("Обезболивающие", "painkillers"),
        ("Кардио", "cardio"),
        ("Дерматология", "dermatology"),
        ("Простуда/ОРВИ", "cold-flu"),
        ("ЖКТ", "gastro"),
        ("Эндокринология/Диабет", "endocrinology-diabetes"),
        ("Офтальмология", "ophthalmology"),
        ("ЛОР", "ent"),
        ("Ортопедия/Травмы", "orthopedics"),
    ],
    "supplements": [
        ("Витамины", "vitamins"),
        ("Минералы", "minerals"),
        ("Омега/рыбий жир", "omega-fish-oil"),
        ("Протеин/аминокислоты", "protein-amino"),
        ("Коллаген", "collagen"),
        ("Пробиотики", "probiotics"),
        ("Иммунитет", "immunity"),
        ("Детские БАДы", "kids-supplements"),
    ],
    "medical_equipment": [
        ("Измерительные (тонометры, глюкометры)", "measuring-devices"),
        ("Уход/устройства (небулайзеры, ингаляторы)", "care-devices"),
        ("Реабилитация/ортезы", "rehab-orthoses"),
        ("Расходники (маски, перчатки)", "consumables"),
        ("Стоматология — инструменты", "dentistry-tools"),
        ("Стоматология — расходники", "dentistry-consumables"),
    ],
    "tableware": [
        ("Кухонная (сковороды/кастрюли)", "kitchen-cookware"),
        ("Сервировка", "serving"),
        ("Хранение", "storage"),
        ("Материал: медная", "copper"),
        ("Материал: фарфор", "porcelain"),
        ("Материал: стекло/керамика", "glass-ceramic"),
    ],
    "furniture": [
        ("Гостиная", "living-room"),
        ("Спальня", "bedroom"),
        ("Офис", "office"),
        ("Кухня/столовая", "kitchen-dining"),
    ],
    "jewelry": [
        ("Кольца", "rings"),
        ("Цепочки", "chains"),
        ("Браслеты", "bracelets"),
        ("Серьги", "earrings"),
        ("Подвески", "pendants"),
        ("Обручальные", "wedding"),
        ("Женские", "women"),
        ("Мужские", "men"),
    ],
    # accessories — свободные, не создаем
}


def create_presets(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    for cat_type, items in PRESETS.items():
        sort = 0
        for name, slug in items:
            Category.objects.get_or_create(
                slug=slugify(slug),
                defaults={
                    "name": name,
                    "description": name,
                    "category_type": cat_type,
                    "is_active": True,
                    "sort_order": sort,
                },
            )
            sort += 1


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0023_category_type_and_product_types"),
    ]

    operations = [
        migrations.RunPython(create_presets, noop_reverse),
    ]

