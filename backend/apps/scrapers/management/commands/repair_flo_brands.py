"""Бренды товаров FLO вместо заглушки «Другое» (dry-run по умолчанию).

Новый бренд со страницы раньше не создавался, и товары FLO получали «Другое».
Ссылка карточки FLO начинается со slug бренда (`/urun/lumberjack-...-102265597`),
а фильтр «Marka» на листинге отдаёт пары slug → название бренда. Поэтому
команда загружает только корневые листинги FLO (по умолчанию 4 запроса через
прокси из настроек парсера), карточки не обходит. Бренд — самый длинный slug из
фильтра, с которого начинается ссылка товара. Ручные бренды не трогаются.

    manage.py repair_flo_brands                          # отчёт, без записи
    manage.py repair_flo_brands --apply                  # проставить бренды
    manage.py repair_flo_brands --listing-html a.html    # без сети: сохранённые листинги
"""
import csv
import html as html_lib
import json
import re
from collections import Counter, defaultdict
from urllib.parse import unquote, urljoin, urlparse

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.catalog.domain_sync import domain_models
from apps.catalog.models import Brand, Product
from apps.catalog.utils.manufacturer_brands import OTHER_BRAND_SLUG
from apps.scrapers.services import clean_scraped_brand_name, get_or_create_scraped_brand

DEFAULT_LISTINGS = ("/ayakkabi", "/giyim", "/canta", "/aksesuar")
BRAND_FILTER_RE = re.compile(r'data-value="manufacturer__\d+__([^"]+?)__\d+__([a-z0-9-]+)"')
PRODUCT_SLUG_RE = re.compile(r"/urun/([a-z0-9-]+?)-\d{4,}", re.IGNORECASE)


def listing_brands(html: str) -> dict:
    """slug → название бренда из фильтра «Marka» листинга FLO."""
    return {
        slug: html_lib.unescape(unquote(name)).strip()
        for name, slug in BRAND_FILTER_RE.findall(html or "")
    }


def brand_for_url(url: str, brands: dict) -> str:
    match = PRODUCT_SLUG_RE.search(urlparse(url or "").path)
    if not match:
        return ""
    slug = match.group(1).lower()
    prefix = max((s for s in brands if slug == s or slug.startswith(f"{s}-")), key=len, default="")
    return brands.get(prefix, "")


class Command(BaseCommand):
    help = "Бренды товаров FLO вместо «Другое» по ссылке товара (по умолчанию dry-run с CSV-отчётом)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Проставить бренды товарам.")
        parser.add_argument(
            "--listing-url", action="append", default=[],
            help=f"Листинг FLO для списка брендов (можно несколько; по умолчанию {', '.join(DEFAULT_LISTINGS)}).",
        )
        parser.add_argument(
            "--listing-html", action="append", default=[],
            help="Сохранённый HTML листинга вместо запроса к FLO (можно несколько).",
        )
        parser.add_argument("--report", default="", help="Путь CSV-отчёта (по умолчанию /tmp/...).")

    def handle(self, *args, **options):
        stamp = f"{timezone.now():%Y%m%d_%H%M%S}"
        report_path = options["report"] or f"/tmp/flo_brands_{stamp}.csv"
        brands = self._load_brands(options["listing_html"], options["listing_url"] or list(DEFAULT_LISTINGS))
        if not brands:
            raise CommandError("В листингах FLO нет фильтра брендов — разметка сайта изменилась?")

        other_id = Brand.objects.filter(slug=OTHER_BRAND_SLUG).values_list("id", flat=True).first()
        placeholder = Q(brand__isnull=True) | Q(brand_id=other_id)
        products = list(
            Product.objects.filter(placeholder)
            .filter(Q(external_data__source="flo") | Q(external_url__icontains="flo.com.tr"))
            .values_list("pk", "product_type", "external_url", "brand_id")
        )

        plan = defaultdict(list)  # (название, product_type) → [(pk, старый brand_id)]
        unmatched = []
        for pk, product_type, url, brand_id in products:
            name = clean_scraped_brand_name(brand_for_url(url, brands))
            if name:
                plan[(name, product_type or "")].append((pk, brand_id))
            else:
                unmatched.append((pk, url))

        to_assign = sum(len(items) for items in plan.values())
        by_name = Counter()
        for (name, _), items in plan.items():
            by_name[name] += len(items)
        with open(report_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["brand", "products", "exists_in_catalog"])
            for name, count in by_name.most_common():
                writer.writerow([name, count, Brand.objects.filter(name__iexact=name).exists()])
            for pk, url in unmatched:
                writer.writerow([f"НЕ НАЙДЕН: product {pk}", url, ""])

        self.stdout.write(
            f"{'APPLY' if options['apply'] else 'DRY-RUN'}: брендов_FLO_в_фильтре={len(brands)} "
            f"товаров_с_заглушкой={len(products)} проставить={to_assign} брендов={len(by_name)} "
            f"не_найдено={len(unmatched)}"
        )
        self.stdout.write(f"Отчёт: {report_path}")
        if not options["apply"] or not plan:
            return

        backup_path = f"/tmp/flo_brands_backup_{stamp}.json"
        with open(backup_path, "w", encoding="utf-8") as fh:
            json.dump({str(pk): brand_id for items in plan.values() for pk, brand_id in items}, fh)
        self.stdout.write(f"Бэкап прежних брендов (product_id → brand_id): {backup_path}")

        domain_map = domain_models()
        with transaction.atomic():
            for (name, product_type), items in plan.items():
                brand = get_or_create_scraped_brand(name, product_type)
                ids = [pk for pk, _ in items]
                # .update(): без сигналов автоскачивания медиа; доменная запись
                # (ShoeProduct и т.п.) получает тот же бренд отдельно.
                Product.objects.filter(placeholder, pk__in=ids).update(brand=brand)
                if product_type in domain_map:
                    domain_map[product_type].objects.filter(placeholder, base_product_id__in=ids).update(brand=brand)

        try:
            from apps.catalog.brand_counts import refresh_brand_product_counts

            refresh_brand_product_counts()
        except Exception as exc:  # счётчики обновит Beat через минуту
            self.stderr.write(f"Счётчики брендов не обновлены: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Готово: проставлено {to_assign}, брендов {len(by_name)}"))

    def _load_brands(self, html_paths, listing_urls) -> dict:
        brands = {}
        if html_paths:
            for path in html_paths:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    brands.update(listing_brands(fh.read()))
            return brands

        from apps.scrapers.models import ScraperConfig
        from apps.scrapers.parsers.flo import FloParser

        config = ScraperConfig.objects.filter(parser_class__iexact="flo").first()
        with FloParser(use_proxy=bool(config and config.use_proxy)) as parser:
            for url in listing_urls:
                brands.update(listing_brands(parser._fetch(urljoin(parser.base_url, url))))
                self.stdout.write(f"Листинг {url}: брендов всего {len(brands)}")
        return brands
