"""Режим «Только изменения»: что парсер уже видел в листинге и что лежит в БД.

Парсер разбирает строки листинга и спрашивает трекер, какие карточки открыть
(решение — ``base.listing_changes.listing_decision``). Трекер хранит отпечатки
строк в ``SourceListingRow`` и снимает с продажи товары, которые источник
пометил пассивными или убрал (404). Сами карточки сохраняются обычным путём
парсера — правила цен, AI-текстов и «изменился исходник» те же, что у полного
обхода.
"""

import logging
from collections import Counter
from typing import Dict, Iterable, List
from urllib.parse import urlparse

from django.utils import timezone

from .base.listing_changes import GONE, OPEN, KnownProduct, ListingRow, listing_decision
from .models import SourceListingRow

logger = logging.getLogger(__name__)


def url_key(url: str) -> str:
    """Путь товара без хоста: www/без www и http/https — один и тот же товар."""
    return urlparse(url or "").path.rstrip("/")


def mark_products_gone(product_ids: Iterable[int], *, parser_key: str, reason: str) -> int:
    """Снимает товары с продажи так же, как проверка карточки при 404.

    Товар и его доменная запись — «нет в наличии», предложения источника —
    OUT_OF_STOCK с кодом причины. Ничего не удаляется: следующий успешный разбор
    карточки вернёт наличие.
    """
    from apps.catalog.models import Product, ProductSourceOffer

    now = timezone.now()
    products = list(Product.objects.filter(pk__in=list(product_ids), is_available=True))
    for product in products:
        domain = product.domain_item
        if domain is not None and domain is not product:
            domain.__class__.objects.filter(pk=domain.pk).update(is_available=False)
    ids = [product.pk for product in products]
    Product.objects.filter(pk__in=ids).update(is_available=False, last_synced_at=now)
    ProductSourceOffer.objects.filter(
        product_id__in=ids, parser_key=parser_key, is_active=True,
    ).update(
        availability_status=ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK,
        last_checked_at=now,
        last_error_code=reason,
        last_error_message="Источник убрал товар или пометил его пассивным",
        updated_at=now,
    )
    if ids:
        logger.info("%s: сняты с продажи (%s): %s", parser_key, reason, ids)
    return len(ids)


class ListingChangeTracker:
    def __init__(self, parser_key: str, run_token, *, dry_run: bool = False):
        self.parser_key = parser_key
        self.run_token = run_token or None
        self.dry_run = dry_run
        # url → отпечаток строки; пишется только после успешного сохранения карточки.
        self.pending: Dict[str, str] = {}
        self.counts: Counter = Counter()
        # «Только посмотреть» ничего не пишет: увиденное в проходе помним здесь.
        self.seen_local: set = set()

    def _products(self, urls: Iterable[str]) -> Dict[str, dict]:
        """Товары этого источника по пути ссылки (поиск по индексу external_id)."""
        from apps.catalog.models import Product

        keys = {url_key(url) for url in urls}
        slugs = {key.rsplit("/", 1)[-1] for key in keys}
        found: Dict[str, dict] = {}
        rows = (
            Product.objects.filter(external_data__source=self.parser_key, external_id__in=slugs)
            .order_by("pk")
            .values(
                "pk", "name", "price", "is_available", "external_url",
                "external_data__source_name", "external_data__is_stub",
            )
        )
        for row in rows:
            key = url_key(row["external_url"])
            if key in keys:
                found.setdefault(key, row)  # дубли: самая ранняя запись, как в сервисе
        return found

    @staticmethod
    def _known(row: dict) -> KnownProduct:
        return KnownProduct(
            name=str(row["external_data__source_name"] or row["name"] or ""),
            price=row["price"],
            is_available=bool(row["is_available"]),
            is_stub=row["external_data__is_stub"] is True,
        )

    def decide(self, rows: List[ListingRow]) -> Dict[str, str]:
        """Решения по строкам одной страницы; запоминает, что проход их видел."""
        fingerprints = dict(
            SourceListingRow.objects.filter(
                parser_key=self.parser_key, url__in=[row.url for row in rows],
            ).values_list("url", "fingerprint")
        )
        products = self._products(row.url for row in rows)
        decisions: Dict[str, str] = {}
        gone_ids = []
        self.seen_local.update(url_key(row.url) for row in rows)
        for row in rows:
            product = products.get(url_key(row.url))
            decision = listing_decision(
                row,
                known_fingerprint=fingerprints.get(row.url, ""),
                product=self._known(product) if product else None,
            )
            decisions[row.url] = decision
            self.counts[decision] += 1
            if decision == OPEN:
                self.pending[row.url] = row.fingerprint
                self.counts["new"] += product is None
            elif decision == GONE:
                gone_ids.append(product["pk"])
        if not self.dry_run:
            # Отпечаток OPEN-строки ждёт сохранения карточки (remember_saved):
            # упавшая карточка будет открыта и в следующем проходе.
            self._upsert(
                [row for row in rows if decisions[row.url] != OPEN], with_fingerprint=True,
            )
            self._upsert([row for row in rows if decisions[row.url] == OPEN])
            mark_products_gone(gone_ids, parser_key=self.parser_key, reason="inactive")
        return decisions

    def _upsert(self, rows: List[ListingRow], *, with_fingerprint: bool = False) -> None:
        if not rows:
            return
        update_fields = ["source_status", "run_token", "seen_at"]
        if with_fingerprint:
            update_fields.append("fingerprint")
        SourceListingRow.objects.bulk_create(
            [
                SourceListingRow(
                    parser_key=self.parser_key,
                    url=row.url,
                    fingerprint=row.fingerprint if with_fingerprint else "",
                    source_status=row.status,
                    run_token=self.run_token,
                )
                for row in rows
            ],
            update_conflicts=True,
            unique_fields=["parser_key", "url"],
            update_fields=update_fields,
        )

    def remember_saved(self, url: str) -> None:
        fingerprint = self.pending.pop(url, None)
        if fingerprint is None or self.dry_run:
            return
        SourceListingRow.objects.filter(parser_key=self.parser_key, url=url).update(
            fingerprint=fingerprint
        )

    def mark_seen(self, urls: Iterable[str], *, status: str = "") -> None:
        """Отмечает ссылки проверенными в этом проходе (sitemap-этап), не трогая отпечаток."""
        urls = list(urls)
        self.seen_local.update(url_key(url) for url in urls)
        if self.dry_run:
            return
        rows = [
            SourceListingRow(
                parser_key=self.parser_key, url=url, source_status=status, run_token=self.run_token,
            )
            for url in urls
        ]
        if rows:
            SourceListingRow.objects.bulk_create(
                rows,
                update_conflicts=True,
                unique_fields=["parser_key", "url"],
                update_fields=["source_status", "run_token", "seen_at"],
            )

    def _seen_keys(self) -> set:
        if self.dry_run or self.run_token is None:
            return set(self.seen_local)
        return {
            url_key(url)
            for url in SourceListingRow.objects.filter(
                parser_key=self.parser_key, run_token=self.run_token,
            ).values_list("url", flat=True)
        }

    def sitemap_work(
        self, sitemap_urls: Iterable[str], is_product_url, canonical_url=lambda url: url,
    ) -> tuple:
        """Что осталось проверить после листинга: (открыть карточку, проверить пропажу).

        Открыть — ссылки sitemap, которых листинг в этом проходе не показал: новые
        товары и те, до кого листинг не достаёт. Проверить — наши товары в
        продаже, которых нет ни в sitemap, ни в листинге этого прохода.
        """
        from apps.catalog.models import Product

        seen = self._seen_keys()
        sitemap_keys = {}
        for url in sitemap_urls:
            sitemap_keys.setdefault(url_key(url), url)
        to_open = sorted(url for key, url in sitemap_keys.items() if key not in seen)
        to_check = []
        rows = Product.objects.filter(
            external_data__source=self.parser_key, is_available=True,
        ).values_list("external_url", "external_data__is_stub")
        for external_url, is_stub in rows:
            key = url_key(canonical_url(external_url))
            if (
                is_stub is not True
                and is_product_url(external_url)
                and key not in sitemap_keys
                and key not in seen
            ):
                to_check.append(external_url)
        return to_open, sorted(set(to_check))

    def mark_url_gone(self, url: str, *, reason: str) -> int:
        """Снимает с продажи товар по ссылке (sitemap-этап: 404 или «İlaç Durumu: Pasif»)."""
        self.counts[GONE] += 1
        if self.dry_run:
            return 0
        product = self._products([url]).get(url_key(url))
        if product is None:
            return 0
        return mark_products_gone([product["pk"]], parser_key=self.parser_key, reason=reason)
