"""Замер точечного обхода «только посмотреть»: списки категорий без карточек.

Проходит списки категорий парсера тем же кодом, что и обычный обход, но
карточки не открывает и ничего не пишет в базу. Считает строки списка,
запросы и байты списков и сколько карточек открыл бы точечный обход:
по отпечаткам в базе (ListingSnapshot) или по файлу прошлого замера.
``--sample-cards N`` открывает N карточек, чтобы узнать цену карточки
(запросы, байты, время) — из неё оценка полного и точечного обхода.

    manage.py measure_listing_changes flo --categories 3 --pages 2 --save /tmp/flo.json
    manage.py measure_listing_changes flo --categories 3 --pages 2 --compare /tmp/flo.json
    manage.py measure_listing_changes zara --url https://www.zara.com/tr/tr/kadin-elbiseler-l1066.html

Прокси не используется, пока не передан ``--use-proxy`` (FLO через прокси
платный — большие замеры только с согласия владельца).
"""

import json
import time
from contextlib import contextmanager

import httpx
import requests
from django.core.management.base import BaseCommand, CommandError

from apps.scrapers.base.listing_snapshot import ListingGuard
from apps.scrapers.parsers.registry import get_parser, register_default_parsers

BASE_URLS = {
    "flo": "https://www.flo.com.tr",
    "zara": "https://www.zara.com",
    "lcw": "https://www.lcw.com",
    "ikea": "https://www.ikea.com.tr",
    "ummaland": "https://umma-land.com",
}
CARD_URL_CHECKS = {
    "flo": "is_flo_product_url",
    "zara": "is_zara_product_url",
    "lcw": "is_lcw_product_url",
    "ikea": "is_ikea_product_url",
    "ummaland": "is_product_url",
}


class MeasuringGuard(ListingGuard):
    """Решает как настоящий, но карточку открывает только для первых N строк."""

    def __init__(self, parser_key, *, previous=None, sample_cards=0):
        super().__init__(parser_key)
        self.previous = previous
        self.sample_cards = sample_cards
        self.rows = {}
        self.would_open = 0
        self.sampled = 0
        # Время карточки — от решения «открыть» до готового товара (с паузами парсера).
        self.card_seconds = 0.0
        self._mark = time.monotonic()

    def prefetch(self, identities):
        self._mark = time.monotonic()
        if self.previous is None:
            super().prefetch(identities)

    def should_open(self, identity, fingerprint):
        self._mark = time.monotonic()
        if not identity or identity in self.rows:
            return False
        self.rows[identity] = fingerprint
        if self.previous is None:
            opens = super().should_open(identity, fingerprint)
        else:
            opens = self.previous.get(identity) != fingerprint
        self.would_open += int(opens)
        if self.sampled < self.sample_cards:
            self.sampled += 1
            return True
        return False

    def attach(self, product, identity, fingerprint, *, covers=()):
        now = time.monotonic()
        self.card_seconds += now - self._mark
        self._mark = now

    def remember_covered(self, identity, fingerprint):
        return False


class TrafficCounter:
    """Считает запросы и байты всех HTTP-клиентов парсера (httpx и requests)."""

    def __init__(self, is_card_url):
        self.is_card_url = is_card_url
        self.stats = {
            kind: {"requests": 0, "wire_bytes": 0, "bytes": 0}
            for kind in ("list", "card")
        }

    def _count(self, url, response, wire_bytes):
        kind = "card" if self.is_card_url(str(url)) else "list"
        row = self.stats[kind]
        row["requests"] += 1
        size = len(response.content or b"")
        row["bytes"] += size
        row["wire_bytes"] += wire_bytes if wire_bytes is not None else size

    @contextmanager
    def patched(self):
        counter = self
        httpx_send = httpx.Client.send
        requests_send = requests.Session.send

        def counted_httpx(client, request, *args, **kwargs):
            response = httpx_send(client, request, *args, **kwargs)
            response.read()
            counter._count(request.url, response, response.num_bytes_downloaded)
            return response

        def counted_requests(session, request, *args, **kwargs):
            response = requests_send(session, request, *args, **kwargs)
            # requests распаковывает тело сам; сжатый размер — из Content-Length.
            length = response.headers.get("Content-Length")
            counter._count(request.url, response, int(length) if str(length).isdigit() else None)
            return response

        httpx.Client.send = counted_httpx
        requests.Session.send = counted_requests
        try:
            yield self
        finally:
            httpx.Client.send = httpx_send
            requests.Session.send = requests_send


class Command(BaseCommand):
    help = "Замер точечного обхода без открытия карточек и без записи в базу."

    def add_arguments(self, parser):
        parser.add_argument("parser_name", choices=sorted(BASE_URLS))
        parser.add_argument("--url", action="append", default=[], help="Категория (можно несколько).")
        parser.add_argument(
            "--categories", type=int, default=0,
            help="Взять первые N категорий сайта (parse_categories), если --url не задан.",
        )
        parser.add_argument("--pages", type=int, default=1, help="Страниц списка на категорию.")
        parser.add_argument("--sample-cards", type=int, default=0, help="Открыть N карточек для оценки их цены.")
        parser.add_argument("--save", help="Сохранить отпечатки строк в JSON.")
        parser.add_argument("--compare", help="Сравнить с JSON прошлого замера вместо базы.")
        parser.add_argument(
            "--baseline", action="store_true",
            help="Первый замер без базы и без файла: все строки считаются новыми.",
        )
        parser.add_argument("--use-proxy", action="store_true", help="Идти через прокси (платно для FLO).")

    def handle(self, *args, **options):
        name = options["parser_name"]
        register_default_parsers()
        parser_cls = get_parser(name)
        if parser_cls is None:
            raise CommandError(f"Парсер {name} не найден")
        previous = {} if options["baseline"] else None
        if options["compare"]:
            with open(options["compare"], encoding="utf-8") as handle:
                previous = json.load(handle)["rows"]

        with parser_cls(base_url=BASE_URLS[name], use_proxy=options["use_proxy"]) as parser:
            check = getattr(parser, CARD_URL_CHECKS[name])
            counter = TrafficCounter(check)
            guard = MeasuringGuard(
                parser.get_name(), previous=previous, sample_cards=options["sample_cards"],
            )
            parser.listing_guard = guard
            started = time.monotonic()
            with counter.patched():
                urls = options["url"] or [
                    row["url"] for row in parser.parse_categories()[: options["categories"]]
                ]
                if not urls:
                    raise CommandError("Укажите --url или --categories N")
                for url in urls:
                    kwargs = {"max_pages": options["pages"]}
                    if getattr(parser, "SUPPORTS_PAGE_CHUNKING", False):
                        kwargs["start_page"] = 1
                    for _ in parser.parse_product_list(url, **kwargs):
                        pass
            elapsed = time.monotonic() - started

        report = self._report(name, urls, guard, counter.stats, elapsed, previous is not None)
        if options["save"]:
            with open(options["save"], "w", encoding="utf-8") as handle:
                json.dump({**report, "rows": guard.rows}, handle, ensure_ascii=False)
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))

    @staticmethod
    def _report(name, urls, guard, stats, elapsed, compared):
        rows = len(guard.rows)
        cards = stats["card"]
        sampled = max(1, guard.sampled)
        per_card = {
            "requests": round(cards["requests"] / sampled, 2),
            "wire_bytes": round(cards["wire_bytes"] / sampled),
            "seconds": round(guard.card_seconds / sampled, 2),
        }
        listing = stats["list"]
        list_seconds = elapsed - guard.card_seconds

        def estimate(opened):
            return {
                "requests": listing["requests"] + round(opened * per_card["requests"]),
                "wire_bytes": listing["wire_bytes"] + round(opened * per_card["wire_bytes"]),
                "seconds": round(list_seconds + opened * per_card["seconds"]),
            }

        common = [i for i in guard.rows if guard.previous and i in guard.previous]
        return {
            "parser": name,
            "categories": len(urls),
            "rows": rows,
            "would_open": guard.would_open,
            "compared_with": "file" if compared else "ListingSnapshot",
            # Строки, что были и в прошлом замере, и сколько из них изменилось.
            "common_rows": len(common),
            "changed_common": sum(guard.rows[i] != guard.previous[i] for i in common),
            "list": {**listing, "seconds": round(list_seconds)},
            "sampled_cards": guard.sampled,
            "per_card": per_card if guard.sampled else None,
            "full_estimate": estimate(rows) if guard.sampled else None,
            "incremental_estimate": estimate(guard.would_open) if guard.sampled else None,
            "elapsed_seconds": round(elapsed),
        }
