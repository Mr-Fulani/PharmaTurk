"""Названия LCW вместо рекламного og:title с ценой (dry-run по умолчанию).

С октября 2026 og:title карточек LCW рекламный («Deodorant - Markalar -
319,89 TL»); парсер брал его как название, а повторный парсинг название
существующего товара не меняет. Команда перечитывает страницу товара и
берёт полное название из <title> (как парсер после исправления). Товары с
применённым AI-результатом не трогает.

    manage.py repair_lcw_names --limit 20      # отчёт по 20 товарам, без изменений
    manage.py repair_lcw_names --apply         # заменить у всех
"""
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.db.models.fields.json import KT

from apps.ai.services.ownership import has_applied_ai_content
from apps.catalog.models import Product
from apps.http_errors import ExternalAccessBlockedError
from apps.scrapers.parsers.lcw import LcwParser

PRICE_IN_NAME_REGEX = r"[0-9],[0-9]{2} *(TL|₺)"


class Command(BaseCommand):
    help = "Заменяет рекламные названия LCW («… - 319,89 TL») полными из <title>."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Изменить названия (иначе только отчёт).")
        parser.add_argument("--limit", type=int, default=0, help="Сколько товаров обработать (0 — все).")

    def handle(self, *args, **options):
        products = (
            Product.objects.annotate(source=KT("external_data__source"))
            .filter(source="lcw", name__regex=PRICE_IN_NAME_REGEX)
            .exclude(external_url="")
            .order_by("id")
        )
        total = products.count()
        if options["limit"]:
            products = products[: options["limit"]]
        fixed = skipped = failed = 0
        with LcwParser() as parser:
            for product in products:
                if has_applied_ai_content(product):
                    skipped += 1
                    continue
                try:
                    html = parser._make_request(product.external_url)
                except ExternalAccessBlockedError:
                    raise
                except Exception as exc:  # noqa: BLE001 — одна карточка не останавливает обход
                    failed += 1
                    self.stdout.write(f"{product.pk}: ошибка загрузки {exc}")
                    continue
                name = parser._extract_name(BeautifulSoup(html, "html.parser")) if html else ""
                if not name or parser.PRICE_RE.search(name):
                    failed += 1
                    self.stdout.write(f"{product.pk}: название не найдено ({product.external_url})")
                    continue
                self.stdout.write(f"{product.pk}: {product.name!r} -> {name!r}")
                if options["apply"]:
                    product.name = name[:500]
                    product.save(update_fields=["name"])
                fixed += 1
        mode = "заменено" if options["apply"] else "к замене (dry-run)"
        self.stdout.write(
            f"Найдено {total}; {mode}: {fixed}; пропущено (AI): {skipped}; не удалось: {failed}"
        )
