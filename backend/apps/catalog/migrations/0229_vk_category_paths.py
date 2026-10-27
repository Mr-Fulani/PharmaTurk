"""Пути категорий ВК для всех типов товаров, мужское/женское/детское раздельно.

Решение владельца 27.10.2026 («решай сам, проверь информацию в вк»). Названия второго
уровня — из дерева ВК (market.getCategories): «Женщинам» 20000, «Мужчинам» 20001,
«Детям» 20002, «Мебель» 20026, «Посуда и товары для кухни» 20020 и т.д.; разделы
«Гардероб», «Дом и дача» и третий уровень «Обувь»/«Аксессуары» — из записей владельца
(апрель 2026), продублированы для женского и детского. Лекарства в фиды не идут.

Прежний путь сохраняется в «Примечаниях» записи; откат миграции возвращает четыре
апрельские записи как были. Заодно удаляются прежние готовые фиды (в них были лекарства).
"""

from django.db import migrations

WARDROBE_LEVEL3 = {
    "shoes": "Обувь",
    "headwear": "Аксессуары",
    "accessories": "Аксессуары",
    "jewelry": "Аксессуары",
    "clothing": "",
    "underwear": "",
    "islamic_clothing": "",
}
WARDROBE_GENDERS = {"men": "Мужчинам", "women": "Женщинам", "kids": "Детям"}
VK_IDS = {"Мужчинам": 20001, "Женщинам": 20000, "Детям": 20002}
# Товар без пола или унисекс: обувь и головные уборы — как было в апрельских записях.
WARDROBE_DEFAULT = {"shoes": "Мужчинам", "headwear": "Мужчинам"}

PLAIN = {
    "furniture": ("Дом и дача > Мебель", 20026),
    "tableware": ("Дом и дача > Посуда и товары для кухни", 20020),
    "books": ("Книги и журналы", 20029),
    "perfumery": ("Парфюмерия", 20093),
    "incense": ("Ароматерапия", 20094),
    "supplements": ("Витамины, БАДы и пищевые добавки", 20098),
    "medical_equipment": ("Медицинские изделия и расходные материалы", 20178),
    "electronics": ("Смартфоны и гаджеты", 20003),
    "sports": ("Спортивная одежда", 20038),
    "auto_parts": ("Запчасти", 20122),
}

APRIL_ROWS = {
    "furniture": "Дом и дача Мебель",
    "headwear": "Гардероб > Мужчинам > Аксессуары",
    "shoes": "Гардероб > Мужчинам > Обувь",
    "supplements": "Витамины, БАДы и пищевые добавки",
}


def _wardrobe_path(product_type: str, leaf: str) -> str:
    level3 = WARDROBE_LEVEL3[product_type]
    return f"Гардероб > {leaf} > {level3}" if level3 else f"Гардероб > {leaf}"


def _rows():
    for product_type in WARDROBE_LEVEL3:
        default_leaf = WARDROBE_DEFAULT.get(product_type, "Женщинам")
        yield product_type, "", _wardrobe_path(product_type, default_leaf), VK_IDS[default_leaf]
        for gender, leaf in WARDROBE_GENDERS.items():
            yield product_type, gender, _wardrobe_path(product_type, leaf), VK_IDS[leaf]
    for product_type, (path, vk_id) in PLAIN.items():
        yield product_type, "", path, vk_id


def set_paths(apps, schema_editor):
    VKCategoryMapping = apps.get_model("catalog", "VKCategoryMapping")
    for product_type, gender, path, vk_id in _rows():
        note = f"ВК: категория {vk_id} (market.getCategories), миграция 0229 от 27.10.2026."
        row = VKCategoryMapping.objects.filter(product_type=product_type, gender=gender).first()
        if row is None:
            VKCategoryMapping.objects.create(product_type=product_type, gender=gender, vk_category_path=path, notes=note)
            continue
        if row.vk_category_path != path:
            note = f"{note} Было: «{row.vk_category_path}»."
        row.notes = "\n".join(part for part in (row.notes, note) if part)
        row.vk_category_path = path
        row.save(update_fields=["vk_category_path", "notes", "updated_at"])


def restore_april_rows(apps, schema_editor):
    VKCategoryMapping = apps.get_model("catalog", "VKCategoryMapping")
    VKCategoryMapping.objects.exclude(product_type__in=APRIL_ROWS, gender="").delete()
    for product_type, path in APRIL_ROWS.items():
        row = VKCategoryMapping.objects.filter(product_type=product_type, gender="").first()
        if row is None:
            VKCategoryMapping.objects.create(product_type=product_type, gender="", vk_category_path=path)
            continue
        row.vk_category_path = path
        row.notes = "\n".join(line for line in row.notes.splitlines() if "миграция 0229" not in line)
        row.save(update_fields=["vk_category_path", "notes", "updated_at"])


def reset_feed_snapshots(apps, schema_editor):
    """
    Прежние готовые фиды собраны с лекарствами и без деления на части — удаляем.
    Первый же запрос фида после деплоя ответит 503 и запустит новую сборку.
    """
    from django.core.files.storage import default_storage

    YMLFeedSnapshot = apps.get_model("catalog", "YMLFeedSnapshot")
    for snapshot in YMLFeedSnapshot.objects.all():
        if snapshot.file:
            default_storage.delete(snapshot.file.name)
        snapshot.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0228_vk_mapping_gender_feed_parts"),
    ]

    operations = [
        migrations.RunPython(set_paths, restore_april_rows),
        migrations.RunPython(reset_feed_snapshots, migrations.RunPython.noop),
    ]
