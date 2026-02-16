from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0097_add_author_name_en_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductGenre",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sort_order", models.IntegerField(default=0, verbose_name="Порядок сортировки")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("genre", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="book_genre_products", to="catalog.category", verbose_name="Жанр")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="book_genres", to="catalog.product", verbose_name="Товар")),
            ],
            options={
                "verbose_name": "Жанр книги",
                "verbose_name_plural": "Жанры книг",
                "ordering": ["sort_order", "created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="productgenre",
            index=models.Index(fields=["product", "genre"], name="catalog_pro_product_23f2b7_idx"),
        ),
        migrations.AddIndex(
            model_name="productgenre",
            index=models.Index(fields=["sort_order"], name="catalog_pro_sort_or_1c6f30_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="productgenre",
            unique_together={("product", "genre")},
        ),
    ]
