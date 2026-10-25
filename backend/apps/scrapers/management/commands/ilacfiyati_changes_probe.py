"""«Только посмотреть» для режима «Только изменения» IlacFiyati: ничего не пишет.

Проходит листинги лекарств и БАДов, сравнивает строки с БД (отпечатки
SourceListingRow и сохранённые товары) и sitemap, печатает, сколько карточек
режим откроет, сколько снимет с продажи и сколько запросов и времени это займёт
против полного обхода. В БД ничего не меняется.

    manage.py ilacfiyati_changes_probe                 # всё: листинги + sitemap
    manage.py ilacfiyati_changes_probe --pages 20      # по 20 страниц листинга, без sitemap
"""
import time
from collections import Counter

from django.core.management.base import BaseCommand

from apps.scrapers.base.listing_changes import GONE, OPEN, SKIP
from apps.scrapers.listing_changes import ListingChangeTracker
from apps.scrapers.models import ScraperConfig
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser


def _parser() -> IlacFiyatiParser:
    """Парсер с задержками и заголовками конфигурации — как в настоящей задаче."""
    config = ScraperConfig.objects.filter(parser_class="ilacfiyati").order_by("pk").first()
    if config is None:
        return IlacFiyatiParser(base_url="https://ilacfiyati.com")
    parser = IlacFiyatiParser(
        base_url=config.base_url, timeout=config.timeout, max_retries=config.max_retries,
        use_proxy=config.use_proxy, username=config.scraper_username,
    )
    parser.delay_range = (config.delay_min, config.delay_max)
    parser.configure_request_identity(
        user_agent=config.user_agent, headers=config.headers, cookies=config.cookies,
    )
    return parser


class Command(BaseCommand):
    help = "Оценка режима «Только изменения» IlacFiyati без записи в БД."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pages", type=int, default=0,
            help="Страниц на каждый листинг (0 — до конца). С ограничением sitemap не считается.",
        )
        parser.add_argument(
            "--sample-cards", type=int, default=5,
            help="Сколько карточек скачать для замера времени одной карточки.",
        )

    def handle(self, *args, **options):
        tracker = ListingChangeTracker("ilacfiyati", None, dry_run=True)
        requests = 0
        started = time.monotonic()
        listing_pages = 0
        sample_urls = []
        with _parser() as parser:
            for source in parser.parse_categories():
                counts = Counter()
                first_urls = previous_urls = None
                page = 1
                while not options["pages"] or page <= options["pages"]:
                    url = parser._listing_page_url(source["url"], page)
                    html = parser._make_request(url)
                    requests += 1
                    rows = parser.parse_listing_rows(html or "")
                    if rows is None:
                        raise RuntimeError(f"Нет блока «Arama Sonuçları»: {url}")
                    urls = {row.url for row in rows}
                    # После последней страницы сайт отдаёт первую заново.
                    if not urls or urls == first_urls or urls == previous_urls:
                        break
                    listing_pages += 1
                    counts["pages"] += 1
                    first_urls = first_urls or urls
                    previous_urls = urls
                    new_before = tracker.counts["new"]
                    for decision in tracker.decide(rows).values():
                        counts[decision] += 1
                    counts["new"] += tracker.counts["new"] - new_before
                    sample_urls.extend(row.url for row in rows[:1])
                    if parser._listing_has_next_page(html, source["url"], page) is False:
                        break
                    page += 1
                self.stdout.write(
                    f"{source['url']}: страниц {counts['pages']}, "
                    f"без изменений {counts[SKIP]}, открыть {counts[OPEN]} (нет у нас {counts['new']}), "
                    f"снять с продажи {counts[GONE]}"
                )

            to_open = to_check = []
            sitemap_size = 0
            if not options["pages"]:
                sitemap_urls = parser.fetch_sitemap_product_urls()
                requests += 1
                sitemap_size = len(sitemap_urls)
                to_open, to_check = tracker.sitemap_work(
                    sitemap_urls, parser.is_product_url, parser._canonical_product_url,
                )
                self.stdout.write(
                    f"Sitemap: карточек {sitemap_size}; листинг не показал {len(to_open)} "
                    f"(откроются); наших в продаже нет в sitemap и листинге: {len(to_check)} "
                    "(проверятся запросом: 404/Pasif — снять)"
                )
            listing_seconds = time.monotonic() - started

            card_seconds = 0.0
            for url in sample_urls[: options["sample_cards"]]:
                card_started = time.monotonic()
                parser.parse_product_detail(url)
                card_seconds += time.monotonic() - card_started
            sampled = min(len(sample_urls), options["sample_cards"])
            per_card = card_seconds / sampled if sampled else 0.0

        per_page = listing_seconds / max(requests, 1)
        cards = tracker.counts[OPEN] + len(to_open) + len(to_check)
        changes_requests = requests + cards
        self.stdout.write(
            f"Режим изменений: запросов {changes_requests} (листинг+sitemap {requests}, "
            f"карточек {cards}); ≈ {(listing_seconds + cards * per_card) / 3600:.1f} ч"
        )
        if sitemap_size:
            full_requests = listing_pages + sitemap_size
            self.stdout.write(
                f"Полный обход: запросов ≈ {full_requests} (страниц {listing_pages}, "
                f"карточек {sitemap_size}); ≈ {(listing_pages * per_page + sitemap_size * per_card) / 3600:.1f} ч"
            )
        self.stdout.write(
            f"Замер: страница листинга {per_page:.2f} с, карточка {per_card:.2f} с "
            f"(по {sampled}). В БД ничего не записано."
        )
