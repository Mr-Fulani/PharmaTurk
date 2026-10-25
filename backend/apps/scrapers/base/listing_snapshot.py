"""Точечный обход каталога: карточка открывается, только если строка списка изменилась.

Строка списка категории (название, цена, наличие, цвета…) сворачивается в
отпечаток. После успешного сохранения товара отпечаток его строки
запоминается в ListingSnapshot. В следующем обходе та же строка с тем же
отпечатком карточку не открывает: товар в базе уже такой. Карточка
открывается, если товара нет в базе, строка изменилась или карточку не
открывали дольше окна полного обновления (то, что видно только в карточке:
описание, состав, остатки по размерам).
"""

import hashlib
import json
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Окно «редкого полного обхода»: каждая карточка открывается не реже, чем раз
# в столько дней. Срок у строки свой (75–125 % окна), чтобы такие открытия
# размазывались по обходам, а не приходились на один.
FULL_REFRESH_DAYS = 30


def listing_fingerprint(data) -> str:
    """Отпечаток данных строки списка (порядок ключей словаря не важен)."""
    payload = json.dumps(
        data, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ListingGuard:
    """Решает по строке списка, открывать ли карточку, и запоминает отпечатки.

    Живёт в пределах одного чанка обхода категории. ``open_all`` — режим
    «Открыть все карточки»: решение всегда «открыть», отпечатки обновляются.
    """

    def __init__(self, parser_key, *, open_all=False, refresh_days=FULL_REFRESH_DAYS):
        self.parser_key = parser_key
        self.open_all = bool(open_all)
        self.refresh_days = refresh_days
        self.unchanged = 0
        self._snapshots = {}
        # Строки цветов, загруженных вместе с группой в этом проходе: identity → product_id.
        self._covered = {}

    def prefetch(self, identities):
        """Один запрос на страницу списка вместо запроса на строку."""
        from ..models import ListingSnapshot

        missing = [i for i in dict.fromkeys(identities) if i and i not in self._snapshots]
        if not missing:
            return
        for identity in missing:
            self._snapshots[identity] = None
        rows = ListingSnapshot.objects.filter(
            parser_key=self.parser_key, identity__in=missing,
        ).values_list("identity", "fingerprint", "card_checked_at")
        for identity, fingerprint, checked_at in rows:
            self._snapshots[identity] = (fingerprint, checked_at)

    def _refresh_due(self, identity, checked_at):
        spread = int(hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
        window = timedelta(days=self.refresh_days * (0.75 + 0.5 * spread))
        return timezone.now() - checked_at > window

    def should_open(self, identity, fingerprint) -> bool:
        if self.open_all or not identity:
            return True
        if identity not in self._snapshots:
            self.prefetch([identity])
        snapshot = self._snapshots.get(identity)
        if (
            snapshot is None
            or snapshot[0] != fingerprint
            or self._refresh_due(identity, snapshot[1])
        ):
            return True
        self.unchanged += 1
        return False

    def attach(self, product, identity, fingerprint, *, covers=()):
        """Помечает товар строкой списка, из которой открыта карточка.

        ``covers`` — строки других цветов, загруженных в той же карточке.
        Отпечаток запишется после сохранения товара (record_listing_snapshot).
        """
        product._listing_row = (self, identity, fingerprint, tuple(c for c in covers if c))

    def record_saved(self, identity, fingerprint, covers, product) -> None:
        self._save(identity, fingerprint, product.pk)
        for covered in covers:
            self._covered[covered] = product.pk

    def remember_covered(self, identity, fingerprint) -> bool:
        """Строка цвета, уже загруженного вместе с группой в этом проходе.

        Её данные свежие, поэтому отпечаток записывается без открытия карточки
        — иначе следующий обход открыл бы всю группу ради этой строки.
        """
        product_id = self._covered.get(identity)
        if not product_id or not fingerprint:
            return False
        self._save(identity, fingerprint, product_id)
        return True

    def _save(self, identity, fingerprint, product_id) -> None:
        from ..models import ListingSnapshot

        now = timezone.now()
        values = {"fingerprint": fingerprint, "product_id": product_id, "card_checked_at": now}
        try:
            try:
                with transaction.atomic():
                    ListingSnapshot.objects.update_or_create(
                        parser_key=self.parser_key, identity=identity, defaults=values,
                    )
            except IntegrityError:
                # Параллельный чанк успел вставить ту же строку.
                ListingSnapshot.objects.filter(
                    parser_key=self.parser_key, identity=identity,
                ).update(**values)
        except Exception:
            # Отпечаток — оптимизация: без него карточка просто откроется снова.
            logger.exception("ListingSnapshot %s:%s не сохранён", self.parser_key, identity)
            return
        self._snapshots[identity] = (fingerprint, now)


def record_listing_snapshot(scraped_product, product) -> None:
    """После успешного сохранения товара запоминает отпечаток его строки списка."""
    row = getattr(scraped_product, "_listing_row", None)
    if not row or product is None or not getattr(product, "pk", None):
        return
    guard, identity, fingerprint, covers = row
    guard.record_saved(identity, fingerprint, covers, product)
