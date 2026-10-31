"""ID категории ВК в маппинге: без него API не добавит товар (market.add, category_id).

ID те же, что записаны в миграции 0229 и таблице docs/VK_YML_FEED.md. Заполняются по
пути категории: путь, изменённый в админке, остаётся без ID, в сеть миграция не ходит.
"""

from django.db import migrations, models

WARDROBE_IDS = {"Мужчинам": 20001, "Женщинам": 20000, "Детям": 20002}
PLAIN_IDS = {
    "Дом и дача > Мебель": 20026,
    "Дом и дача > Посуда и товары для кухни": 20020,
    "Книги и журналы": 20029,
    "Парфюмерия": 20093,
    "Ароматерапия": 20094,
    "Витамины, БАДы и пищевые добавки": 20098,
    "Медицинские изделия и расходные материалы": 20178,
    "Смартфоны и гаджеты": 20003,
    "Спортивная одежда": 20038,
    "Запчасти": 20122,
}


def category_id(path):
    parts = path.split(" > ")
    if parts[0] == "Гардероб" and len(parts) > 1:
        return WARDROBE_IDS.get(parts[1])
    return PLAIN_IDS.get(path)


def fill_category_ids(apps, schema_editor):
    VKCategoryMapping = apps.get_model("catalog", "VKCategoryMapping")
    for row in VKCategoryMapping.objects.all():
        row.vk_category_id = category_id(row.vk_category_path)
        if row.vk_category_id:
            row.save(update_fields=["vk_category_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0231_stale_products_deletion"),
    ]

    operations = [
        migrations.AddField(
            model_name="vkcategorymapping",
            name="vk_category_id",
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    "Нужен, чтобы добавлять товары через API (market.add). Пусто — новые товары "
                    "этой категории не добавляются, в отчёте синхронизации они указаны отдельно."
                ),
                null=True,
                verbose_name="ID категории ВК",
            ),
        ),
        migrations.RunPython(fill_category_ids, migrations.RunPython.noop),
    ]
