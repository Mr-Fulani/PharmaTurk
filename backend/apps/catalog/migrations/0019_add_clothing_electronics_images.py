from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0018_currency_choices_for_shoes_electronics"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClothingProductImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image_url", models.URLField(help_text="Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.", verbose_name="URL изображения")),
                ("alt_text", models.CharField(blank=True, max_length=200, verbose_name="Alt текст")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")),
                ("is_main", models.BooleanField(default=False, verbose_name="Главное изображение")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="catalog.clothingproduct", verbose_name="Товар одежды")),
            ],
            options={
                "verbose_name": "Изображение товара одежды",
                "verbose_name_plural": "Изображения товаров одежды",
                "ordering": ["sort_order", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="ElectronicsProductImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image_url", models.URLField(help_text="Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.", verbose_name="URL изображения")),
                ("alt_text", models.CharField(blank=True, max_length=200, verbose_name="Alt текст")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")),
                ("is_main", models.BooleanField(default=False, verbose_name="Главное изображение")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="catalog.electronicsproduct", verbose_name="Товар электроники")),
            ],
            options={
                "verbose_name": "Изображение товара электроники",
                "verbose_name_plural": "Изображения товаров электроники",
                "ordering": ["sort_order", "created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="clothingproductimage",
            index=models.Index(fields=["product", "sort_order"], name="catalog_clo_product_b05bc4_idx"),
        ),
        migrations.AddIndex(
            model_name="electronicsproductimage",
            index=models.Index(fields=["product", "sort_order"], name="catalog_ele_product_f42259_idx"),
        ),
    ]

