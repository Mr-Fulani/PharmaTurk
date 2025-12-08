from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0015_add_usdt_currency"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shoeproduct",
            name="category",
            field=models.ForeignKey(
                blank=True,
                help_text=_("Выберите категорию из дерева обуви; при необходимости создайте новую в ShoeCategory."),
                null=True,
                on_delete=models.SET_NULL,
                related_name="products",
                to="catalog.shoecategory",
                verbose_name=_("Категория"),
            ),
        ),
        migrations.AlterField(
            model_name="shoeproduct",
            name="brand",
            field=models.ForeignKey(
                blank=True,
                help_text=_("Если нет бренда в списке — создайте его в разделе брендов."),
                null=True,
                on_delete=models.SET_NULL,
                related_name="shoe_products",
                to="catalog.brand",
                verbose_name=_("Бренд"),
            ),
        ),
        migrations.AlterField(
            model_name="shoeproduct",
            name="size",
            field=models.CharField(
                blank=True,
                choices=[
                    ("35", "35"),
                    ("36", "36"),
                    ("37", "37"),
                    ("38", "38"),
                    ("39", "39"),
                    ("40", "40"),
                    ("41", "41"),
                    ("42", "42"),
                    ("43", "43"),
                    ("44", "44"),
                    ("45", "45"),
                    ("46", "46"),
                    ("47", "47"),
                    ("48", "48"),
                ],
                help_text=_("Выберите размер в EU-формате; при необходимости можно оставить пустым."),
                max_length=20,
                verbose_name=_("Размер"),
            ),
        ),
        migrations.AlterField(
            model_name="shoeproduct",
            name="main_image",
            field=models.URLField(
                blank=True,
                help_text=_("URL главного фото; дополнительные фото задаются в галерее ниже."),
                verbose_name=_("Главное изображение"),
            ),
        ),
        migrations.CreateModel(
            name="ShoeProductImage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "image_url",
                    models.URLField(
                        help_text=_(
                            "Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте."
                        ),
                        verbose_name=_("URL изображения"),
                    ),
                ),
                ("alt_text", models.CharField(blank=True, max_length=200, verbose_name=_("Alt текст"))),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name=_("Порядок сортировки"))),
                ("is_main", models.BooleanField(default=False, verbose_name=_("Главное изображение"))),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="images",
                        to="catalog.shoeproduct",
                        verbose_name=_("Товар обуви"),
                    ),
                ),
            ],
            options={
                "verbose_name": _("Изображение товара обуви"),
                "verbose_name_plural": _("Изображения товаров обуви"),
                "ordering": ["sort_order", "created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="shoeproductimage",
            index=models.Index(fields=["product", "sort_order"], name="catalog_sh_product_sort_9bce1d_idx"),
        ),
    ]

