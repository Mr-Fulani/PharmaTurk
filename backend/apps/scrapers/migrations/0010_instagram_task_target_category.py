"""Миграция: добавляет поле target_category (ForeignKey → Category) в InstagramScraperTask.

target_category позволяет выбирать категорию из каталога через выпадающий список
в Admin — аналогично SiteScraperTask.target_category. Имеет приоритет над
старым полем category (CharField со списком slug-значений).
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        # Зависимость от предыдущей миграции скраперов (которая уже зависит от catalog)
        ("scrapers", "0009_target_category_on_task_and_session"),
    ]

    operations = [
        migrations.AddField(
            model_name="instagramscrapertask",
            name="target_category",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Категория из каталога (выпадающий список). Имеет приоритет над полем «Категория товаров». "
                    "Определяет product_type (книги → BookProduct, одежда → ClothingProduct и т.д.)."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="instagram_tasks",
                to="catalog.category",
                verbose_name="Целевая категория",
            ),
        ),
        # Обновляем verbose_name для поля category (fallback)
        migrations.AlterField(
            model_name="instagramscrapertask",
            name="category",
            field=models.CharField(
                choices=[
                    ("books", "Книги"),
                    ("clothing", "Одежда"),
                    ("shoes", "Обувь"),
                    ("electronics", "Электроника"),
                    ("supplements", "Добавки"),
                    ("medical-equipment", "Медицинское оборудование"),
                    ("furniture", "Мебель"),
                    ("tableware", "Посуда"),
                    ("accessories", "Аксессуары"),
                    ("jewelry", "Ювелирные изделия"),
                    ("underwear", "Нижнее белье"),
                    ("headwear", "Головные уборы"),
                ],
                default="books",
                help_text=(
                    "Используется только если «Целевая категория» не выбрана. "
                    "Рекомендуется использовать «Целевая категория»."
                ),
                max_length=50,
                verbose_name="Категория товаров (fallback)",
            ),
        ),
    ]
