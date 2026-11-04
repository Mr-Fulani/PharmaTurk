from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Только схема: поле GTIN у размеров и таблица скрытых дублей. Данные не трогает, в сеть не ходит."""

    dependencies = [
        ("catalog", "0234_indexnow_url_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="clothingvariantsize",
            name="gtin",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Штрихкод производителя (EAN/UPC), дополненный нулями до 14 цифр. По нему находим тот же товар у другого продавца.",
                max_length=14,
                verbose_name="GTIN размера",
            ),
        ),
        migrations.AddField(
            model_name="shoevariantsize",
            name="gtin",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Штрихкод производителя (EAN/UPC), дополненный нулями до 14 цифр. По нему находим тот же товар у другого продавца.",
                max_length=14,
                verbose_name="GTIN размера",
            ),
        ),
        migrations.AddField(
            model_name="headwearvariantsize",
            name="gtin",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Штрихкод производителя (EAN/UPC), дополненный нулями до 14 цифр. По нему находим тот же товар у другого продавца.",
                max_length=14,
                verbose_name="GTIN размера",
            ),
        ),
        migrations.AddField(
            model_name="underwearvariantsize",
            name="gtin",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Штрихкод производителя (EAN/UPC), дополненный нулями до 14 цифр. По нему находим тот же товар у другого продавца.",
                max_length=14,
                verbose_name="GTIN размера",
            ),
        ),
        migrations.CreateModel(
            name="CrossSourceDuplicate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product_type", models.CharField(max_length=30, verbose_name="Тип товара")),
                ("hidden_variant_id", models.PositiveBigIntegerField(verbose_name="Скрытый цвет (ID варианта)")),
                (
                    "shown_variant_id",
                    models.PositiveBigIntegerField(blank=True, null=True, verbose_name="Показанный цвет (ID варианта)"),
                ),
                (
                    "match",
                    models.CharField(
                        choices=[("ean", "Штрихкод производителя"), ("article", "Бренд + артикул")],
                        max_length=20,
                        verbose_name="Как узнали",
                    ),
                ),
                (
                    "reason",
                    models.CharField(
                        choices=[("price", "Показан более дорогой"), ("stock", "У более дорогого нет размеров в наличии")],
                        max_length=20,
                        verbose_name="Почему показан другой",
                    ),
                ),
                (
                    "hidden_price",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name="Цена скрытого"),
                ),
                (
                    "shown_price",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name="Цена показанного"),
                ),
                ("currency", models.CharField(blank=True, max_length=5, verbose_name="Валюта")),
                (
                    "product_hidden",
                    models.BooleanField(
                        default=False,
                        help_text="Все цвета товара оказались дублями — товар снят с сайта, его адрес ведёт на показанный.",
                        verbose_name="Скрыта вся карточка",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Скрыт")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Проверено")),
                (
                    "hidden_product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hidden_duplicate_rows",
                        to="catalog.product",
                        verbose_name="Скрытый товар",
                    ),
                ),
                (
                    "shown_product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="shown_duplicate_rows",
                        to="catalog.product",
                        verbose_name="Показан вместо него",
                    ),
                ),
            ],
            options={
                "verbose_name": "Дубль у другого продавца",
                "verbose_name_plural": "Дубли у других продавцов",
                "indexes": [models.Index(fields=["product_type", "shown_variant_id"], name="cross_dup_shown_variant_idx")],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("product_type", "hidden_variant_id"), name="uniq_cross_source_duplicate_variant"
                    )
                ],
            },
        ),
    ]
