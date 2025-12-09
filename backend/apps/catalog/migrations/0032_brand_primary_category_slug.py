from django.db import migrations, models

# Дублируем выбор slugs здесь, чтобы не тянуть модель (избегаем ModuleNotFoundError в миграции)
TOP_CATEGORY_SLUG_CHOICES = [
    ("medicines", "medicines"),
    ("supplements", "supplements"),
    ("medical-equipment", "medical-equipment"),
    ("clothing", "clothing"),
    ("shoes", "shoes"),
    ("electronics", "electronics"),
    ("furniture", "furniture"),
    ("tableware", "tableware"),
    ("accessories", "accessories"),
    ("jewelry", "jewelry"),
    ("underwear", "underwear"),
    ("headwear", "headwear"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0031_card_media_for_marketing_cards"),
    ]

    operations = [
        migrations.AddField(
            model_name="brand",
            name="primary_category_slug",
            field=models.CharField(
                blank=True,
                choices=TOP_CATEGORY_SLUG_CHOICES,
                help_text="Явно укажите ключевой slug для бренда (clothing, shoes, electronics и т.д.).",
                max_length=64,
                verbose_name="Основная категория (slug)",
            ),
        ),
    ]

