"""Настройка парсера Seniorah в «Конфигурациях парсеров» (решение владельца 07.11.2026).

Без сети и R2: только строка ScraperConfig. Автосинхронизация выключена до пилота
(расписание ``run_all_active_scrapers`` берёт только ``sync_enabled``), «Включен» — да,
иначе задачу из админки не запустить. Бренд — со страницы (парсер отдаёт «Seniorah»);
если бренд уже есть в каталоге — он и «Бренд по умолчанию». Раздел каждого товара парсер
выбирает сам по виду обуви, «Обувь» — только обязательная категория по умолчанию.
Уже существующую запись (заведённую руками) миграция не трогает.
"""

from django.db import migrations

CONFIG = {
    "name": "seniorah",
    "parser_class": "seniorah",
    "base_url": "https://seniorah.com",
    "description": (
        "Женская обувь Seniorah (Shopify, открытый JSON, без прокси). Раздел — по виду обуви "
        "в названии. Автосинхронизация выключена до пилота."
    ),
    "status": "active",
    "is_enabled": True,
    "is_multibrand": False,
    "priority": 100,
    "delay_min": 1.0,
    "delay_max": 2.0,
    "timeout": 30,
    "max_retries": 3,
    # Каталог ~255 товаров: страница раздела — 250, весь раздел — один запуск.
    "max_pages_per_run": 10,
    "max_products_per_run": 300,
    "max_images_per_product": 8,
    "sync_enabled": False,
    "sync_interval_hours": 24,
    "use_proxy": False,
}


def create_config(apps, schema_editor):
    ScraperConfig = apps.get_model("scrapers", "ScraperConfig")
    Category = apps.get_model("catalog", "Category")
    Brand = apps.get_model("catalog", "Brand")
    if ScraperConfig.objects.filter(parser_class__iexact="seniorah").exists():
        return
    if ScraperConfig.objects.filter(name=CONFIG["name"]).exists():
        return
    shoes = Category.objects.filter(slug="shoes").first()
    if shoes is None:
        return  # пустая база (тесты, новый стенд): настройку заведут в админке
    ScraperConfig.objects.create(
        default_category=shoes,
        default_brand=Brand.objects.filter(name__iexact="Seniorah").first(),
        **CONFIG,
    )


def delete_config(apps, schema_editor):
    ScraperConfig = apps.get_model("scrapers", "ScraperConfig")
    ScraperConfig.objects.filter(name=CONFIG["name"], parser_class="seniorah", total_runs=0).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("scrapers", "0032_remove_scraperconfig_ai_flags"),
        ("catalog", "0237_product_search_index"),
    ]

    operations = [
        migrations.RunPython(create_config, delete_config),
    ]
