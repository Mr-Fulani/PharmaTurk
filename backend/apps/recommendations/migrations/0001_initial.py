# Generated manually for recommendations app

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("catalog", "0088_product_keywords_product_seo_description_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductVector",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("qdrant_id", models.CharField(db_index=True, max_length=50, unique=True)),
                ("vector_type", models.CharField(choices=[("text", "Текстовый"), ("image", "Изображение"), ("combined", "Комбинированный")], default="combined", max_length=20)),
                ("category_id", models.IntegerField(blank=True, db_index=True, null=True)),
                ("price", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("brand_id", models.IntegerField(blank=True, db_index=True, null=True)),
                ("color", models.CharField(blank=True, db_index=True, max_length=50)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("vector_quality_score", models.FloatField(blank=True, help_text="Уверенность энкодера", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("last_synced", models.DateTimeField(blank=True, help_text="Последняя синхронизация с Qdrant", null=True)),
                ("product", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="vector_data", to="catalog.product")),
            ],
            options={
                "verbose_name": "Вектор товара",
                "verbose_name_plural": "Векторы товаров",
            },
        ),
        migrations.CreateModel(
            name="UserEmbedding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("preference_vector", models.JSONField(blank=True, null=True)),
                ("category_weights", models.JSONField(blank=True, default=dict, help_text='{"medicines": 0.8, "supplements": 0.3}')),
                ("avg_price_viewed", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("price_sensitivity", models.CharField(choices=[("low", "Низкая"), ("medium", "Средняя"), ("high", "Высокая")], default="medium", max_length=20)),
                ("last_updated", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="embedding", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Эмбеддинг пользователя",
                "verbose_name_plural": "Эмбеддинги пользователей",
            },
        ),
        migrations.CreateModel(
            name="RecommendationEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_id", models.CharField(blank=True, db_index=True, max_length=100)),
                ("event_type", models.CharField(choices=[("impression", "Показ"), ("click", "Клик"), ("cart_add", "В корзину"), ("purchase", "Покупка")], max_length=20)),
                ("algorithm", models.CharField(choices=[("vector_text", "Векторный (текст)"), ("vector_image", "Векторный (изображение)"), ("vector_combined", "Векторный (комбинированный)"), ("collaborative", "Коллаборативный"), ("trending", "Тренды"), ("hybrid", "Гибрид")], max_length=20)),
                ("position", models.PositiveSmallIntegerField(help_text="Позиция в списке (1-20)")),
                ("filters_applied", models.JSONField(blank=True, default=dict, help_text="Примененные фильтры")),
                ("similarity_score", models.FloatField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("recommended_product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recommendation_targets", to="catalog.product")),
                ("source_product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recommendation_sources", to="catalog.product")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Событие рекомендации",
                "verbose_name_plural": "События рекомендаций",
            },
        ),
        migrations.AddIndex(
            model_name="productvector",
            index=models.Index(fields=["category_id", "is_active"], name="rec_pv_cat_active"),
        ),
        migrations.AddIndex(
            model_name="productvector",
            index=models.Index(fields=["price", "is_active"], name="rec_pv_price_active"),
        ),
        migrations.AddIndex(
            model_name="productvector",
            index=models.Index(fields=["color", "is_active"], name="rec_pv_color_active"),
        ),
        migrations.AddIndex(
            model_name="recommendationevent",
            index=models.Index(fields=["session_id", "created_at"], name="rec_ev_sess_created"),
        ),
        migrations.AddIndex(
            model_name="recommendationevent",
            index=models.Index(fields=["algorithm", "event_type"], name="rec_ev_algo_type"),
        ),
        migrations.AddIndex(
            model_name="recommendationevent",
            index=models.Index(fields=["source_product", "event_type"], name="rec_ev_src_type"),
        ),
    ]
