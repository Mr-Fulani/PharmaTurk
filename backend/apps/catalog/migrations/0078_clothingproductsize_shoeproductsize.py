from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0077_alter_bookvariant_currency_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClothingProductSize",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("size", models.CharField(blank=True, help_text="Например S, M, L или 48, 50.", max_length=50, verbose_name="Размер")),
                ("is_available", models.BooleanField(default=True, verbose_name="Доступен")),
                ("stock_quantity", models.PositiveIntegerField(blank=True, null=True, verbose_name="Остаток")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sizes",
                        to="catalog.clothingproduct",
                        verbose_name="Товар одежды",
                    ),
                ),
            ],
            options={
                "verbose_name": "Размер товара одежды",
                "verbose_name_plural": "Размеры товара одежды",
                "ordering": ["product", "sort_order", "size"],
            },
        ),
        migrations.CreateModel(
            name="ShoeProductSize",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("size", models.CharField(blank=True, help_text="EU размер, например 40, 41, 42.", max_length=20, verbose_name="Размер")),
                ("is_available", models.BooleanField(default=True, verbose_name="Доступен")),
                ("stock_quantity", models.PositiveIntegerField(blank=True, null=True, verbose_name="Остаток")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sizes",
                        to="catalog.shoeproduct",
                        verbose_name="Товар обуви",
                    ),
                ),
            ],
            options={
                "verbose_name": "Размер товара обуви",
                "verbose_name_plural": "Размеры товара обуви",
                "ordering": ["product", "sort_order", "size"],
            },
        ),
        migrations.AddIndex(
            model_name="clothingproductsize",
            index=models.Index(fields=["product", "sort_order"], name="catalog_clo_product_94d68d_idx"),
        ),
        migrations.AddIndex(
            model_name="clothingproductsize",
            index=models.Index(fields=["product", "size"], name="catalog_clo_product_22d41e_idx"),
        ),
        migrations.AddIndex(
            model_name="shoeproductsize",
            index=models.Index(fields=["product", "sort_order"], name="catalog_sho_product_4c1e0d_idx"),
        ),
        migrations.AddIndex(
            model_name="shoeproductsize",
            index=models.Index(fields=["product", "size"], name="catalog_sho_product_93c1aa_idx"),
        ),
    ]
