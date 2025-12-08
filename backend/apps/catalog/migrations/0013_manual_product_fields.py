from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0012_banner_description_alter_banner_title_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="name_en",
            field=models.CharField(
                _("Название (англ.)"),
                max_length=500,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="description_en",
            field=models.TextField(
                _("Описание (англ.)"),
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="product_type",
            field=models.CharField(
                _("Тип товара"),
                max_length=32,
                choices=[
                    ("medicines", "Лекарства"),
                    ("supplements", "БАДы"),
                    ("tableware", "Посуда"),
                    ("furniture", "Мебель"),
                    ("medical_equipment", "Медицинская техника"),
                    ("clothing", "Одежда"),
                    ("shoes", "Обувь"),
                    ("electronics", "Электроника"),
                    ("other", "Прочее"),
                ],
                default="medicines",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="availability_status",
            field=models.CharField(
                _("Статус доступности"),
                max_length=32,
                choices=[
                    ("in_stock", "В наличии"),
                    ("backorder", "Под заказ"),
                    ("preorder", "Предзаказ"),
                    ("out_of_stock", "Нет в наличии"),
                    ("discontinued", "Снят с производства"),
                ],
                default="in_stock",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="min_order_quantity",
            field=models.PositiveIntegerField(
                _("Минимальное количество заказа"),
                default=1,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="pack_quantity",
            field=models.PositiveIntegerField(
                _("Количество в упаковке"),
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="country_of_origin",
            field=models.CharField(
                _("Страна происхождения"),
                max_length=100,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="gtin",
            field=models.CharField(
                _("GTIN"),
                max_length=64,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="mpn",
            field=models.CharField(
                _("MPN"),
                max_length=64,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="weight_value",
            field=models.DecimalField(
                _("Вес"),
                max_digits=8,
                decimal_places=3,
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="weight_unit",
            field=models.CharField(
                _("Единица веса"),
                max_length=10,
                default="g",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="length",
            field=models.DecimalField(
                _("Длина"),
                max_digits=8,
                decimal_places=3,
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="width",
            field=models.DecimalField(
                _("Ширина"),
                max_digits=8,
                decimal_places=3,
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="height",
            field=models.DecimalField(
                _("Высота"),
                max_digits=8,
                decimal_places=3,
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="dimensions_unit",
            field=models.CharField(
                _("Единица размера"),
                max_length=10,
                default="cm",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="meta_title",
            field=models.CharField(
                _("Meta Title"),
                max_length=255,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="meta_description",
            field=models.CharField(
                _("Meta Description"),
                max_length=500,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="meta_keywords",
            field=models.CharField(
                _("Meta Keywords"),
                max_length=500,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="og_title",
            field=models.CharField(
                _("OG Title"),
                max_length=255,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="og_description",
            field=models.CharField(
                _("OG Description"),
                max_length=500,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="og_image_url",
            field=models.URLField(
                _("OG Image URL"),
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="meta_title_en",
            field=models.CharField(
                _("Meta Title (англ.)"),
                max_length=255,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="meta_description_en",
            field=models.CharField(
                _("Meta Description (англ.)"),
                max_length=500,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="meta_keywords_en",
            field=models.CharField(
                _("Meta Keywords (англ.)"),
                max_length=500,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="og_title_en",
            field=models.CharField(
                _("OG Title (англ.)"),
                max_length=255,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="og_description_en",
            field=models.CharField(
                _("OG Description (англ.)"),
                max_length=500,
                blank=True,
                default="",
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["product_type"],
                name="catalog_product_product_type_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["availability_status"],
                name="catalog_product_availability_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["country_of_origin"],
                name="catalog_product_country_of_origin_idx",
            ),
        ),
    ]

