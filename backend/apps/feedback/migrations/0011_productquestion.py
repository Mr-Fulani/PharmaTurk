import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("feedback", "0010_productreview_productreviewmedia"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product_type", models.CharField(db_index=True, max_length=64, verbose_name="Тип товара/услуги")),
                ("product_slug", models.SlugField(db_index=True, max_length=600, verbose_name="Slug родительской карточки")),
                ("product_name", models.CharField(max_length=500, verbose_name="Название товара/услуги")),
                ("author_name", models.CharField(max_length=150, verbose_name="Имя автора")),
                ("is_anonymous", models.BooleanField(default=True, verbose_name="Скрывать имя на сайте")),
                ("question", models.TextField(verbose_name="Вопрос")),
                ("answer", models.TextField(blank=True, verbose_name="Ответ")),
                ("status", models.CharField(choices=[("pending", "Ожидает ответа"), ("answered", "Ответ опубликован"), ("rejected", "Отклонён")], db_index=True, default="pending", max_length=16, verbose_name="Статус")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создан")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Изменён")),
                ("answered_at", models.DateTimeField(blank=True, null=True, verbose_name="Ответ опубликован")),
                ("answered_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="answered_product_questions", to=settings.AUTH_USER_MODEL, verbose_name="Ответил")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_questions", to=settings.AUTH_USER_MODEL, verbose_name="Пользователь")),
            ],
            options={
                "verbose_name": "❓ Вопрос о товаре/услуге",
                "verbose_name_plural": "❓ Вопросы — Товары и услуги",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="productquestion",
            index=models.Index(fields=["product_type", "product_slug", "status"], name="feedback_pq_target_idx"),
        ),
        migrations.AddIndex(
            model_name="productquestion",
            index=models.Index(fields=["user", "status"], name="feedback_pq_user_idx"),
        ),
    ]
