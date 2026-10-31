"""
Синхронизация каталога ВК с фидом сайта через API (TD-039, docs/VK_YML_FEED.md).

Источник правды — те же офферы, что идут в YML-фид (``iter_feed_offers``): только
товары в наличии, цена с наценкой как на сайте, без лекарств и «ввоз ограничен».
Сопоставление только по артикулу: ``sku`` в ВК = ``vendorCode`` оффера («538», «538v1»).

Запуск читает каталог ВК и фид, строит план и сверяет его с предохранителями. Состояние
нигде не хранится: после сбоя следующий запуск заново сравнивает ВК с фидом, поэтому
сделанное не повторяется, а остальное продолжается.
"""
from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable, Iterator

from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.cache import cache

from ..models_vk import VKCategoryMapping
from .vk_market_sync import VKAPIError, VKMarketSync, VKPhotoError
from .yml_feed import html_to_text, iter_feed_offers

logger = logging.getLogger(__name__)

LOCK_KEY = "catalog:vk-catalog-sync:lock"
# Чуть дольше hard limit задачи: зависший запуск не заблокирует следующие дни.
LOCK_TIMEOUT = 60 * 160

# Наш артикул — id оффера фида. Всё остальное завёл не сайт, такие товары не трогаем.
OUR_SKU_RE = re.compile(r"\d+(?:v\d+)?")

NAME_MIN_CHARS = 4  # market.add: name от 4 до 100 символов (в фиде до 150)
NAME_MAX_CHARS = 100
DESCRIPTION_MIN_CHARS = 10
VK_AVAILABLE = 0
VK_REMOVED = 1

EXAMPLES_LIMIT = 5
TELEGRAM_LIMIT = 3900
MAX_CONSECUTIVE_ERRORS = 20
# Продолжать бессмысленно: ключ не работает, нет прав, капча, лимиты ВК исчерпаны
# (6 и 9 сюда попадают уже после повторов) или магазин выключен.
STOP_CODES = frozenset({5, 6, 7, 9, 14, 15, 29, 205, 1405, 1438})

SKIP_NO_CATEGORY = "нет ID категории ВК в «Маппингах категорий ВК»"
SKIP_NO_PHOTO = "нет фото"
SKIP_NO_PRICE = "нет цены"
SKIP_BAD_NAME = "название короче 4 знаков"


def _text_key(text: str) -> str:
    """Короткий отпечаток текста без оформления: сравниваем, не держа все описания в памяти."""
    normalized = " ".join(html_to_text(text).split())
    return hashlib.blake2b(normalized.encode("utf-8"), digest_size=8).hexdigest()


@dataclass(frozen=True)
class FeedOffer:
    sku: str
    name: str
    description: str
    price: Decimal
    category_path: str
    picture: str

    @classmethod
    def from_element(cls, offer: ET.Element) -> FeedOffer:
        return cls(
            sku=offer.findtext("vendorCode") or "",
            name=(offer.findtext("name") or "").strip()[:NAME_MAX_CHARS].rstrip(" ,"),
            description=offer.findtext("description") or "",
            price=Decimal(offer.findtext("price") or "0"),
            category_path=offer.findtext("market_category") or "",
            picture=offer.findtext("picture") or "",
        )


@dataclass(frozen=True)
class VKItem:
    id: int
    sku: str
    title: str
    title_key: str
    description_key: str
    price: Decimal | None
    availability: int

    @classmethod
    def from_api(cls, item: dict) -> VKItem:
        title = item.get("title") or ""
        return cls(
            id=item["id"],
            sku=str(item.get("sku") or "").strip(),
            title=title[:60],
            title_key=_text_key(title),
            description_key=_text_key(item.get("description") or ""),
            price=_vk_price(item.get("price")),
            availability=item.get("availability", VK_AVAILABLE),
        )

    @property
    def removed(self) -> bool:
        return self.availability == VK_REMOVED


def _vk_price(price: dict | None) -> Decimal | None:
    """Цена из market.get: amount — строка в сотых долях валюты."""
    try:
        return Decimal(str((price or {}).get("amount"))) / 100
    except InvalidOperation:
        return None


@dataclass
class SyncReport:
    apply: bool = False
    feed_count: int = 0
    vk_count: int = 0  # товары ВК без уже удалённых: от них считается доля
    add: list[str] = field(default_factory=list)
    update_stock: list[str] = field(default_factory=list)  # цена или наличие — важнее текстов
    update_text: list[str] = field(default_factory=list)
    delete: list[VKItem] = field(default_factory=list)
    foreign: list[VKItem] = field(default_factory=list)  # без нашего артикула
    duplicates: list[VKItem] = field(default_factory=list)  # второй товар с тем же артикулом
    skipped: dict[str, list[str]] = field(default_factory=dict)
    examples: dict[str, list[str]] = field(default_factory=dict)
    added: int = 0
    updated: int = 0
    deleted: int = 0
    errors: int = 0
    error_examples: list[str] = field(default_factory=list)
    stop_reason: str = ""

    def example(self, kind: str, text: str) -> None:
        items = self.examples.setdefault(kind, [])
        if len(items) < EXAMPLES_LIMIT:
            items.append(text)

    def summary(self) -> str:
        if self.apply:
            result = (
                f"добавлено {self.added} из {len(self.add)}, "
                f"обновлено {self.updated} из {len(self.update_stock) + len(self.update_text)}, "
                f"удалено {self.deleted} из {len(self.delete)}, ошибок {self.errors}"
            )
        else:
            result = (
                f"добавит {len(self.add)}, "
                f"обновит {len(self.update_stock) + len(self.update_text)} "
                f"(цена или наличие {len(self.update_stock)}, тексты {len(self.update_text)}), "
                f"удалит {len(self.delete)}"
            )
        return f"{self.feed_count} в фиде, {self.vk_count} в ВК: {result}"

    def text(self) -> str:
        mode = "настоящий запуск" if self.apply else "только отчёт, в ВК ничего не менялось"
        lines = [f"🛍 Каталог ВК ({mode})", self.summary()]
        if self.stop_reason:
            label = "Остановлено" if self.apply else "Настоящий запуск не пройдёт"
            lines.append(f"⛔ {label}: {self.stop_reason}")
        if self.foreign:
            lines.append(f"Без нашего артикула: {len(self.foreign)}. Не трогаем, решает владелец.")
            lines += [f"  ВК {item.id}: {item.title}" for item in self.foreign[:EXAMPLES_LIMIT]]
        if self.duplicates:
            lines.append(f"Дубли артикула: {len(self.duplicates)}. Не удаляем, решает владелец.")
            lines += [f"  ВК {item.id}, артикул {item.sku}: {item.title}" for item in self.duplicates[:EXAMPLES_LIMIT]]
        for reason, skus in self.skipped.items():
            lines.append(f"Не добавляем, {reason}: {len(skus)} (артикулы {', '.join(skus[:EXAMPLES_LIMIT])})")
        titles = {"add": "Примеры добавления:", "update": "Примеры обновления:"}
        for kind, title in titles.items():
            if self.examples.get(kind):
                lines.append(title)
                lines += [f"  {text}" for text in self.examples[kind]]
        if self.delete:
            lines.append("Примеры удаления:")
            lines += [f"  {item.sku}: {item.title}" for item in self.delete[:EXAMPLES_LIMIT]]
        if self.error_examples:
            lines.append("Примеры ошибок:")
            lines += [f"  {text}" for text in self.error_examples]
        return "\n".join(lines)


class _StopRun(Exception):
    """Запуск прерван: продолжать нельзя, часть работы может быть уже сделана."""


def _category_ids() -> dict[str, int]:
    """Путь категории ВК из фида → ID для market.add."""
    return dict(
        VKCategoryMapping.objects.filter(vk_category_id__isnull=False)
        .values_list("vk_category_path", "vk_category_id")
    )


def _iter_offers(skus: set[str] | None = None) -> Iterator[FeedOffer]:
    """Офферы фида. С skus — только эти: фид читается потоком, план держит только артикулы."""
    remaining = None if skus is None else set(skus)
    for element in iter_feed_offers():
        offer = FeedOffer.from_element(element)
        if remaining is None:
            yield offer
        elif offer.sku in remaining:
            remaining.discard(offer.sku)
            yield offer
            if not remaining:
                return


def _edit_fields(offer: FeedOffer, item: VKItem) -> dict:
    """Только то, что расходится с фидом. Пусто — товар в ВК актуален."""
    fields: dict = {}
    if offer.price > 0 and offer.price != item.price:
        fields["price"] = str(offer.price)
    if item.availability != VK_AVAILABLE:
        fields["deleted"] = 0
    if len(offer.name) >= NAME_MIN_CHARS and _text_key(offer.name) != item.title_key:
        fields["name"] = offer.name
    if len(offer.description) >= DESCRIPTION_MIN_CHARS and _text_key(offer.description) != item.description_key:
        fields["description"] = offer.description
    return fields


def _add_problem(offer: FeedOffer, categories: dict[str, int]) -> str:
    if offer.category_path not in categories:
        return SKIP_NO_CATEGORY
    if not offer.picture:
        return SKIP_NO_PHOTO
    if offer.price <= 0:
        return SKIP_NO_PRICE
    if len(offer.name) < NAME_MIN_CHARS:
        return SKIP_BAD_NAME
    return ""


def _read_vk_catalog(sync: VKMarketSync, report: SyncReport) -> dict[str, VKItem]:
    """Каталог ВК: артикул → товар. Чужие и дубли — в отчёт. Уже удалённые не считаются."""
    by_sku: dict[str, VKItem] = {}
    for raw in sync.iter_market_items(include_hidden=True):
        item = VKItem.from_api(raw)
        report.vk_count += 0 if item.removed else 1
        if not OUR_SKU_RE.fullmatch(item.sku):
            if not item.removed:
                report.foreign.append(item)
            continue
        kept = by_sku.get(item.sku)
        if kept is None or kept.removed:
            by_sku[item.sku] = item
            item = kept
        if item is not None and not item.removed:
            report.duplicates.append(item)
    return by_sku


def _build_plan(sync: VKMarketSync, report: SyncReport) -> dict[str, VKItem]:
    by_sku = _read_vk_catalog(sync, report)
    categories = _category_ids()
    in_feed: set[str] = set()

    for offer in _iter_offers():
        report.feed_count += 1
        in_feed.add(offer.sku)
        item = by_sku.get(offer.sku)
        if item is None:
            problem = _add_problem(offer, categories)
            if problem:
                report.skipped.setdefault(problem, []).append(offer.sku)
            else:
                report.add.append(offer.sku)
                report.example("add", f"{offer.sku}: {offer.name}, {offer.price} ₽")
            continue
        fields = _edit_fields(offer, item)
        if not fields:
            continue
        if "price" in fields or "deleted" in fields:
            report.update_stock.append(offer.sku)
        else:
            report.update_text.append(offer.sku)
        report.example("update", f"{offer.sku}: {_describe_changes(fields, item)}")

    report.delete = [item for sku, item in by_sku.items() if sku not in in_feed and not item.removed]
    # Дубль товара, которого нет в фиде, удаляется вместе с ним.
    report.delete += [item for item in report.duplicates if item.sku not in in_feed]
    report.duplicates = [item for item in report.duplicates if item.sku in in_feed]
    return by_sku


def _describe_changes(fields: dict, item: VKItem) -> str:
    changes = []
    if "price" in fields:
        changes.append(f"цена {item.price} → {fields['price']}")
    if "deleted" in fields:
        changes.append("снова в наличии")
    if "name" in fields:
        changes.append("название")
    if "description" in fields:
        changes.append("описание")
    return ", ".join(changes)


def _guard_reason(report: SyncReport, max_delete_share: float) -> str:
    """Почему план нельзя выполнять. Пустая строка — можно."""
    if not report.feed_count:
        return "фид пустой, ничего не меняем"
    if not report.vk_count:
        return ""
    delete_share = len(report.delete) / report.vk_count
    if delete_share > max_delete_share:
        return (
            f"на удаление попало {len(report.delete)} из {report.vk_count} товаров ВК "
            f"({delete_share:.0%}), порог {max_delete_share:.0%}. Проверьте примеры; если всё верно — "
            "разовый запуск с --max-delete-share"
        )
    # Если ВК не отдаёт артикул, весь каталог выглядел бы новым и получил бы дубли.
    foreign_share = len(report.foreign) / report.vk_count
    if foreign_share > max_delete_share:
        return (
            f"без нашего артикула {len(report.foreign)} из {report.vk_count} товаров ВК "
            f"({foreign_share:.0%}), порог {max_delete_share:.0%}. Запуск дал бы дубли: сначала "
            "разберитесь с этими товарами в ВК"
        )
    return ""


class _Executor:
    """Выполняет план: сбой одного товара не останавливает запуск, сбой API — останавливает."""

    def __init__(self, sync: VKMarketSync, report: SyncReport, by_sku: dict[str, VKItem]):
        self.sync = sync
        self.report = report
        self.by_sku = by_sku
        self.categories = _category_ids()
        self.consecutive_errors = 0

    def run(self) -> None:
        # Сначала то, что вводит покупателя в заблуждение: лишние карточки и старые цены.
        # Тексты — последними: если ВК хранит текст иначе и он всегда «отличается»,
        # такие правки не должны съедать время остальных.
        for item in self.report.delete:
            if self._attempt(item.sku, lambda it=item: self.sync.delete_item(it.id)):
                self.report.deleted += 1
        self._update(self.report.update_stock)
        for offer in _iter_offers(set(self.report.add)):
            if self._attempt(offer.sku, lambda o=offer: self._add(o)):
                self.report.added += 1
        self._update(self.report.update_text)

    def _update(self, skus: list[str]) -> None:
        for offer in _iter_offers(set(skus)):
            item = self.by_sku[offer.sku]
            fields = _edit_fields(offer, item)
            if fields and self._attempt(offer.sku, lambda: self.sync.edit_item(item.id, fields)):
                self.report.updated += 1

    def _add(self, offer: FeedOffer) -> None:
        photo_id = self.sync.upload_main_photo(offer.picture)
        self.sync.add_item(
            name=offer.name,
            description=offer.description,
            category_id=self.categories[offer.category_path],
            price=str(offer.price),
            main_photo_id=photo_id,
            sku=offer.sku,
        )

    def _attempt(self, sku: str, action: Callable[[], None]) -> bool:
        try:
            action()
        except VKPhotoError as e:
            self._record_error(sku, e)  # битая картинка у одного товара — не повод останавливаться
            return False
        except VKAPIError as e:
            self._record_error(sku, e)
            self.consecutive_errors += 1
            if e.code in STOP_CODES:
                raise _StopRun(str(e)) from None
            if self.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                raise _StopRun(f"{MAX_CONSECUTIVE_ERRORS} ошибок API подряд, последняя: {e}") from None
            return False
        self.consecutive_errors = 0
        return True

    def _record_error(self, sku: str, error: Exception) -> None:
        self.report.errors += 1
        logger.warning("Каталог ВК, артикул %s: %s", sku, error)
        if len(self.report.error_examples) < EXAMPLES_LIMIT:
            self.report.error_examples.append(f"{sku}: {error}")


def _plan_and_apply(sync: VKMarketSync, report: SyncReport, max_delete_share: float) -> None:
    try:
        by_sku = _build_plan(sync, report)
    except VKAPIError as e:
        report.stop_reason = f"каталог ВК не прочитан, ничего не меняем: {e}"
        return
    except SoftTimeLimitExceeded:
        raise
    except Exception:
        logger.exception("Каталог ВК: фид не собрался")
        report.stop_reason = "фид не собрался, ничего не меняем"
        return

    report.stop_reason = _guard_reason(report, max_delete_share)
    if report.stop_reason or not report.apply:
        return
    try:
        _Executor(sync, report, by_sku).run()
    except _StopRun as e:
        report.stop_reason = f"{e}. Сделанное сохранено, следующий запуск продолжит"


def run_catalog_sync(*, apply: bool = False, max_delete_share: float | None = None) -> SyncReport:
    """
    Сверяет каталог ВК с фидом. Без apply только отчёт: к ВК идут одни запросы market.get.
    Все причины остановки — в report.stop_reason; итог отдаёт вызывающий.
    """
    report = SyncReport(apply=apply)
    token = getattr(settings, "VK_USER_TOKEN", "")
    group_id = getattr(settings, "VK_GROUP_ID", 0)
    if not token or not group_id:
        report.stop_reason = "не заданы VK_USER_TOKEN или VK_GROUP_ID"
        return report

    if max_delete_share is None:
        max_delete_share = settings.VK_SYNC_MAX_DELETE_SHARE
    if apply and not cache.add(LOCK_KEY, True, timeout=LOCK_TIMEOUT):
        report.stop_reason = "предыдущий запуск ещё идёт"
        return report

    try:
        _plan_and_apply(VKMarketSync(token=token, group_id=group_id), report, max_delete_share)
    except SoftTimeLimitExceeded:
        report.stop_reason = "закончилось время задачи. Сделанное сохранено, следующий запуск продолжит"
    finally:
        if apply:
            cache.delete(LOCK_KEY)
    logger.info("Каталог ВК: %s; %s", report.summary(), report.stop_reason or "без остановки")
    return report
