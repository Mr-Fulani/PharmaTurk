from django.db import migrations, models
import django.db.models.deletion


def copy_legacy_sizes(apps, schema_editor):
    """Переносим старое поле size в таблицу размеров варианта."""
    ShoeVariant = apps.get_model("catalog", "ShoeVariant")
    ShoeVariantSize = apps.get_model("catalog", "ShoeVariantSize")
    ClothingVariant = apps.get_model("catalog", "ClothingVariant")
    ClothingVariantSize = apps.get_model("catalog", "ClothingVariantSize")

    for variant in ShoeVariant.objects.exclude(size=""):
        ShoeVariantSize.objects.create(
            variant=variant,
            size=variant.size,
            is_available=variant.is_available,
            stock_quantity=variant.stock_quantity,
            sort_order=variant.sort_order,
        )
    for variant in ClothingVariant.objects.exclude(size=""):
        ClothingVariantSize.objects.create(
            variant=variant,
            size=variant.size,
            is_available=variant.is_available,
            stock_quantity=variant.stock_quantity,
            sort_order=variant.sort_order,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0028_clothingvariant_clothingvariantimage_shoevariant_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClothingVariantSize",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("size", models.CharField(blank=True, help_text="Например S, M, L или 48, 50.", max_length=50, verbose_name="Размер")),
                ("is_available", models.BooleanField(default=True, verbose_name="Доступен")),
                ("stock_quantity", models.PositiveIntegerField(blank=True, null=True, verbose_name="Остаток")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                (
                    "variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sizes",
                        to="catalog.clothingvariant",
                        verbose_name="Вариант одежды",
                    ),
                ),
            ],
            options={
                "verbose_name": "Размер варианта одежды",
                "verbose_name_plural": "Размеры варианта одежды",
                "ordering": ["variant", "sort_order", "size"],
            },
        ),
        migrations.CreateModel(
            name="ShoeVariantSize",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("size", models.CharField(blank=True, help_text="EU размер, например 40, 41, 42.", max_length=20, verbose_name="Размер")),
                ("is_available", models.BooleanField(default=True, verbose_name="Доступен")),
                ("stock_quantity", models.PositiveIntegerField(blank=True, null=True, verbose_name="Остаток")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                (
                    "variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sizes",
                        to="catalog.shoevariant",
                        verbose_name="Вариант обуви",
                    ),
                ),
            ],
            options={
                "verbose_name": "Размер варианта обуви",
                "verbose_name_plural": "Размеры варианта обуви",
                "ordering": ["variant", "sort_order", "size"],
            },
        ),
        migrations.AddIndex(
            model_name="clothingvariantsize",
            index=models.Index(fields=["variant", "sort_order"], name="catalog_clothin_vari_492d2c_idx"),
        ),
        migrations.AddIndex(
            model_name="clothingvariantsize",
            index=models.Index(fields=["variant", "size"], name="catalog_clothin_vari_a93e34_idx"),
        ),
        migrations.AddIndex(
            model_name="shoevariantsize",
            index=models.Index(fields=["variant", "sort_order"], name="catalog_shoe_vari_685ad7_idx"),
        ),
        migrations.AddIndex(
            model_name="shoevariantsize",
            index=models.Index(fields=["variant", "size"], name="catalog_shoe_vari_d259d1_idx"),
        ),
        migrations.RunPython(copy_legacy_sizes, migrations.RunPython.noop),
    ]

