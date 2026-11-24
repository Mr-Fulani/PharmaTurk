"""Настройка парсера Aloparça в «Конфигурациях парсеров» (решение владельца 24.11.2026).

Без сети и R2: только строка ScraperConfig, как у SPX (0037). Автосинхронизация выключена,
«Включен» — да, иначе задачу из админки не запустить. Магазин разных брендов, раздел товара
выбирает парсер; «Автозапчасти» — категория по умолчанию. Без прокси, пауза не меньше 2,5 с.
Уже существующую запись миграция не трогает.
"""

from django.db import migrations

CONFIG = {
    "name": "aloparca",
    "parser_class": "aloparca",
    "base_url": "https://aloparca.com",
    "description": (
        "Автозапчасти Aloparça: цена, наличие, OEM-номера, применимость, фото. Обход по карте сайта, "
        "один поток, без прокси, не чаще запроса в 2,5 с. Каталог ~340 тыс. карточек — целиком не "
        "обходить, объём задаёт «Макс. товаров» задачи. Автосинхронизация выключена."
    ),
    "status": "active",
    "is_enabled": True,
    "is_multibrand": True,
    "priority": 100,
    "delay_min": 2.5,
    "delay_max": 4.0,
    "timeout": 30,
    "max_retries": 3,
    # «Страница» обхода — 20 карточек карты сайта (≈ 1 минута).
    "max_pages_per_run": 5,
    "max_products_per_run": 50,
    "max_images_per_product": 8,
    "sync_enabled": False,
    "sync_interval_hours": 24,
    "use_proxy": False,
}


def create_config(apps, schema_editor):
    ScraperConfig = apps.get_model("scrapers", "ScraperConfig")
    Category = apps.get_model("catalog", "Category")
    if ScraperConfig.objects.filter(parser_class__iexact="aloparca").exists():
        return
    if ScraperConfig.objects.filter(name=CONFIG["name"]).exists():
        return
    auto_parts = Category.objects.filter(slug="auto-parts").first()
    if auto_parts is None:
        return  # пустая база (тесты, новый стенд): настройку заведут в админке
    ScraperConfig.objects.create(default_category=auto_parts, **CONFIG)


def delete_config(apps, schema_editor):
    ScraperConfig = apps.get_model("scrapers", "ScraperConfig")
    ScraperConfig.objects.filter(name=CONFIG["name"], parser_class="aloparca", total_runs=0).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("scrapers", "0037_spx_scraper_config"),
        ("catalog", "0248_auto_part_numbers_fitments"),
    ]

    operations = [
        migrations.RunPython(create_config, delete_config),
    ]
