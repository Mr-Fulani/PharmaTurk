"""Seniorah: задержка между запросами 2,5–4 с (проба на проде 08.11.2026 — 429 от Shopify).

Без сети. Меняется только запись, у которой задержка ещё та, что поставила 0033 (1–2 с):
ручную правку админа миграция не трогает. Парсер и сам не ходит в магазин чаще раза в 2,5 с.
"""

from django.db import migrations


def raise_delay(apps, schema_editor):
    ScraperConfig = apps.get_model("scrapers", "ScraperConfig")
    ScraperConfig.objects.filter(parser_class="seniorah", delay_min=1.0, delay_max=2.0).update(
        delay_min=2.5, delay_max=4.0,
    )


def lower_delay(apps, schema_editor):
    ScraperConfig = apps.get_model("scrapers", "ScraperConfig")
    ScraperConfig.objects.filter(parser_class="seniorah", delay_min=2.5, delay_max=4.0).update(
        delay_min=1.0, delay_max=2.0,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("scrapers", "0033_seniorah_scraper_config"),
    ]

    operations = [
        migrations.RunPython(raise_delay, lower_delay),
    ]
