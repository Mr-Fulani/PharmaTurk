"""Настройка парсера SPX в «Конфигурациях парсеров» (решение владельца 12.11.2026).

Без сети и R2: только строка ScraperConfig, как у Intersport (0035). Автосинхронизация
выключена до пилота, «Включен» — да, иначе задачу из админки не запустить. Магазин разных
брендов, раздел товара выбирает парсер; «Спорттовары» — только обязательная категория по
умолчанию. Уже существующую запись миграция не трогает.
"""

from django.db import migrations

CONFIG = {
    "name": "spx",
    "parser_class": "spx",
    "base_url": "https://www.spx.com.tr",
    "description": (
        "Спортивное снаряжение SPX — Sport Point Extreme (Akinon, открытый JSON, без прокси). "
        "Одежда и обувь не загружаются. Автосинхронизация выключена до пилота."
    ),
    "status": "active",
    "is_enabled": True,
    "is_multibrand": True,
    "priority": 100,
    "delay_min": 1.5,
    "delay_max": 3.0,
    "timeout": 30,
    "max_retries": 3,
    # Раздел «Ekipman» — до 32 страниц по 24 строки.
    "max_pages_per_run": 40,
    "max_products_per_run": 100,
    "max_images_per_product": 8,
    "sync_enabled": False,
    "sync_interval_hours": 24,
    "use_proxy": False,
}


def create_config(apps, schema_editor):
    ScraperConfig = apps.get_model("scrapers", "ScraperConfig")
    Category = apps.get_model("catalog", "Category")
    if ScraperConfig.objects.filter(parser_class__iexact="spx").exists():
        return
    if ScraperConfig.objects.filter(name=CONFIG["name"]).exists():
        return
    sports = Category.objects.filter(slug="sports").first()
    if sports is None:
        return  # пустая база (тесты, новый стенд): настройку заведут в админке
    ScraperConfig.objects.create(default_category=sports, **CONFIG)


def delete_config(apps, schema_editor):
    ScraperConfig = apps.get_model("scrapers", "ScraperConfig")
    ScraperConfig.objects.filter(name=CONFIG["name"], parser_class="spx", total_runs=0).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("scrapers", "0036_rename_mckinley_brand"),
    ]

    operations = [
        migrations.RunPython(create_config, delete_config),
    ]
