"""Неактуальные товары: скрыть с сайта и удалить вместе с файлами — только по решению владельца.

Кандидатов находит ночная сверка (``nightly_stock_check``). Здесь ничего не
запускается само: каждое действие начинает человек в админке «Неактуальные товары».
Устройство и предохранители — docs/STALE_PRODUCTS.md.

Порядок удаления одного товара: повторная проверка у продавца → копия каждого его
файла в бакет бэкапов → в одной транзакции копия строк БД в журнал и удаление строк
(сигналы файлы не трогают) → после всех товаров одна проверка ссылок по всей БД,
закрытая при сбое → удаляются только файлы, на которые больше никто не ссылается.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
import zlib
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable, Iterable, Iterator
from urllib.parse import unquote

from django.conf import settings
from django.core import serializers
from django.core.cache import cache
from django.db import models, router, transaction
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.deletion import Collector
from django.utils import timezone

from apps.catalog.models import Product, ProductSourceOffer
from apps.catalog.models_stock import SOURCE_TITLES, ProductDeletionLog, StaleProductCandidate
from apps.catalog.utils.media_references import MediaReferenceCheckError, media_reference_fields

logger = logging.getLogger(__name__)

# Общая блокировка с cleanup_orphaned_media: два удаления файлов одновременно не идут.
MEDIA_DELETE_LOCK_KEY = "catalog:media-delete:v1"
# Ключ хранилища товара в любом месте значения: в имени файла, URL CDN, ?path= proxy-media.
_PRODUCT_KEY = re.compile(r"products/[^?#&\s\"'<>]*")
# Символы, на которых регулярка обрывает ключ: такие ключи ищутся точным вхождением.
_KEY_STOP = re.compile(r"[?#&\s\"'<>]")
# Как у cleanup_orphaned_media: эти префиксы не удаляются никогда.
_PROTECTED_PREFIXES = ("products/original/", "products/processed/", "products/thumbs/")
_GONE_CHECK_MAX_AGE = timedelta(days=3)


class StaleProductsRefused(Exception):
    """Предохранитель запретил действие; текст — для владельца."""


def _setting_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def min_gone_days() -> int:
    return _setting_int("STALE_PRODUCT_MIN_DAYS", 7, minimum=1, maximum=365)


def delete_after_hidden_days() -> int:
    return _setting_int("STALE_PRODUCT_DELETE_AFTER_HIDDEN_DAYS", 14, minimum=1, maximum=365)


@contextmanager
def media_delete_lock(timeout: int) -> Iterator[bool]:
    """Одно удаление файлов за раз (с cleanup_orphaned_media). False — уже идёт другое."""
    token = uuid.uuid4().hex
    acquired = bool(cache.add(MEDIA_DELETE_LOCK_KEY, token, timeout=timeout))
    try:
        yield acquired
    finally:
        if acquired and cache.get(MEDIA_DELETE_LOCK_KEY) == token:
            cache.delete(MEDIA_DELETE_LOCK_KEY)


# --- защита ------------------------------------------------------------------------------


def domain_records(product: Product) -> list[models.Model]:
    """Все доменные записи товара — и текущего типа, и снятые после смены типа.

    Их все удаляет сигнал pre_delete товара (``signals.delete_domain_before_generic_product``).
    """
    from apps.catalog.signals import _PRODUCT_DOMAIN_ONE_TO_ONE_RELS

    records = []
    for name in _PRODUCT_DOMAIN_ONE_TO_ONE_RELS:
        try:
            record = getattr(product, name)
        except ObjectDoesNotExist:
            continue
        if record is not None:
            records.append(record)
    return records


def protection_reasons(products: Iterable[Product]) -> dict[int, list[str]]:
    """Почему товар можно только скрыть, но не удалять: заявки, Список заявки, избранное, ручные правки."""
    from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
    from django.contrib.contenttypes.models import ContentType

    from apps.catalog.models import Favorite
    from apps.feedback.models import ProductQuestion, ProductReview
    from apps.orders.models import CartItem, OrderItem

    products = list(products)
    ids = [product.pk for product in products]
    reasons: dict[int, list[str]] = defaultdict(list)
    for product_id in OrderItem.objects.filter(product_id__in=ids).values_list("product_id", flat=True).distinct():
        reasons[product_id].append("есть в заявках")
    for product_id in CartItem.objects.filter(product_id__in=ids).values_list("product_id", flat=True).distinct():
        reasons[product_id].append("в Списке заявки покупателя")

    # Избранное, журнал админки, отзывы ссылаются и на Product, и на доменные карточки.
    targets = {(ContentType.objects.get_for_model(Product).pk, pk): pk for pk in ids}
    slugs = {product.slug: product.pk for product in products if product.slug}
    for product in products:
        for record in domain_records(product):
            targets[(ContentType.objects.get_for_model(type(record)).pk, record.pk)] = product.pk
            if getattr(record, "slug", ""):
                slugs.setdefault(record.slug, product.pk)
    for model, reason in ((ProductReview, "есть отзывы"), (ProductQuestion, "есть вопросы покупателей")):
        for slug in model.objects.filter(product_slug__in=list(slugs)).values_list("product_slug", flat=True).distinct():
            reasons[slugs[slug]].append(reason)
    by_type: dict[int, list[int]] = defaultdict(list)
    for content_type_id, object_id in targets:
        by_type[content_type_id].append(object_id)
    for content_type_id, object_ids in by_type.items():
        for object_id in Favorite.objects.filter(
            content_type_id=content_type_id, object_id__in=object_ids
        ).values_list("object_id", flat=True).distinct():
            reasons[targets[(content_type_id, object_id)]].append("в избранном у покупателя")
        for object_id in LogEntry.objects.filter(
            content_type_id=content_type_id,
            object_id__in=[str(pk) for pk in object_ids],
            action_flag__in=(ADDITION, CHANGE),
        ).values_list("object_id", flat=True).distinct():
            reason = "создавали или правили вручную в админке"
            product_id = targets[(content_type_id, int(object_id))]
            if reason not in reasons[product_id]:
                reasons[product_id].append(reason)
    return dict(reasons)


# --- план действия -----------------------------------------------------------------------


@dataclass
class Plan:
    action: str
    eligible: list[StaleProductCandidate] = field(default_factory=list)
    excluded: list[tuple[StaleProductCandidate, str]] = field(default_factory=list)
    protected: dict[int, list[str]] = field(default_factory=dict)
    refusal: str = ""

    @property
    def files_to_free(self) -> int:
        return sum(candidate.files_to_free or 0 for candidate in self.eligible)

    @property
    def bytes_to_free(self) -> int:
        return sum(candidate.bytes_to_free or 0 for candidate in self.eligible)

    @property
    def without_stats(self) -> int:
        return sum(1 for candidate in self.eligible if candidate.media_stats_at is None)


def _source_catalog_size(parser_key: str) -> int:
    return Product.objects.filter(source_offers__parser_key=parser_key).distinct().count()


def plan_action(candidates: Iterable[StaleProductCandidate], action: str, *, now=None) -> Plan:
    """Кого действие затронет, кого нет и почему; ``refusal`` — действие запрещено целиком."""
    now = now or timezone.now()
    candidates = list(candidates)
    plan = Plan(action=action)
    if action == "delete":
        plan.protected = protection_reasons(candidate.product for candidate in candidates)
    gone_days, hidden_days = min_gone_days(), delete_after_hidden_days()
    for candidate in candidates:
        reason = ""
        if action == "hide":
            if candidate.status != StaleProductCandidate.Status.CANDIDATE:
                reason = f"статус «{candidate.get_status_display()}»"
            elif candidate.first_seen_at > now - timedelta(days=gone_days):
                ready = candidate.first_seen_at + timedelta(days=gone_days)
                reason = f"нет у продавца меньше {gone_days} дней — можно с {timezone.localtime(ready):%d.%m}"
            elif candidate.last_gone_at < now - _GONE_CHECK_MAX_AGE:
                reason = "давно не проверялся у продавца — дождитесь ночной сверки"
        elif action == "delete":
            if candidate.status != StaleProductCandidate.Status.HIDDEN:
                reason = "сначала скройте с сайта"
            elif plan.protected.get(candidate.product_id):
                reason = "только скрыть: " + ", ".join(plan.protected[candidate.product_id])
            elif candidate.hidden_at is None or candidate.hidden_at > now - timedelta(days=hidden_days):
                ready = (candidate.hidden_at or now) + timedelta(days=hidden_days)
                reason = f"скрыт меньше {hidden_days} дней — удалить можно с {timezone.localtime(ready):%d.%m}"
        else:
            raise ValueError(action)
        if reason:
            plan.excluded.append((candidate, reason))
        else:
            plan.eligible.append(candidate)
    if plan.eligible:
        plan.refusal = _limits_refusal(plan.eligible, action)
    return plan


def _limits_refusal(eligible: list[StaleProductCandidate], action: str = "hide") -> str:
    total = Product.objects.count()
    minimum = _setting_int("STALE_PRODUCT_MIN_CATALOG_PRODUCTS", 1000, minimum=0, maximum=10_000_000)
    if total < minimum:
        # Урок 14.06.2026: пустая или чужая база делает «лишним» всё.
        return f"В базе всего {total} товаров — похоже на пустую или чужую базу. Действие запрещено."
    per_action = _setting_int("STALE_PRODUCT_MAX_PER_ACTION", 200, minimum=1, maximum=10_000)
    if len(eligible) > per_action:
        return f"Выбрано {len(eligible)} товаров — за одно действие можно не больше {per_action}. Снимите часть галочек."
    if action == "delete":
        per_day = _setting_int("STALE_PRODUCT_MAX_PER_DAY", 400, minimum=1, maximum=100_000)
        today = ProductDeletionLog.objects.filter(created_at__gte=timezone.now() - timedelta(days=1)).count()
        if today + len(eligible) > per_day:
            return (
                f"За сутки уже удалено {today}, с этими будет {today + len(eligible)} — больше {per_day} "
                "в сутки нельзя. Продолжите завтра."
            )
    percent = _setting_int("STALE_PRODUCT_MAX_SOURCE_PERCENT", 10, minimum=1, maximum=100)
    for parser_key, count in Counter(candidate.parser_key for candidate in eligible).items():
        catalog = _source_catalog_size(parser_key)
        if count * 100 > catalog * percent:
            title = SOURCE_TITLES.get(parser_key, parser_key)
            return (
                f"{title}: {count} из {catalog} товаров — больше {percent} % каталога источника за одно "
                "действие. Так много пропаж сразу похоже на ошибку; выберите меньше."
            )
    return ""


# --- скрыть / вернуть / оставить ---------------------------------------------------------


def _set_active(product: Product, active: bool) -> None:
    # QuerySet.update: save() доменной карточки синхронизировал бы её в Product (DEVELOPMENT_RULES §3.13).
    Product.objects.filter(pk=product.pk).update(is_active=active, updated_at=timezone.now())
    domain = product.domain_item
    if domain is not product:
        domain.__class__.objects.filter(pk=domain.pk).update(is_active=active)


def hide_candidates(candidate_ids: Iterable[int], user=None, *, now=None) -> Plan:
    """Шаг 1: убрать с сайта (обратимо). Повторно проверяет срок и лимиты."""
    now = now or timezone.now()
    with transaction.atomic():
        candidates = list(
            StaleProductCandidate.objects.select_for_update()
            .filter(pk__in=list(candidate_ids))
            .select_related("product")
        )
        plan = plan_action(candidates, "hide", now=now)
        if plan.refusal:
            raise StaleProductsRefused(plan.refusal)
        for candidate in plan.eligible:
            _set_active(candidate.product, False)
            candidate.status = StaleProductCandidate.Status.HIDDEN
            candidate.hidden_at = now
            candidate.status_changed_by = user
            candidate.save(update_fields=["status", "hidden_at", "status_changed_by", "updated_at"])
    return plan


def keep_candidates(candidate_ids: Iterable[int], user=None) -> int:
    """«Оставить, не удалять»: скрытый товар возвращается на сайт, пометка больше не предлагает удаление."""
    kept = 0
    with transaction.atomic():
        for candidate in (
            StaleProductCandidate.objects.select_for_update()
            .filter(pk__in=list(candidate_ids))
            .select_related("product")
        ):
            if candidate.hidden_at is not None:
                _set_active(candidate.product, True)
                candidate.hidden_at = None
            candidate.status = StaleProductCandidate.Status.DISMISSED
            candidate.status_changed_by = user
            candidate.save(update_fields=["status", "hidden_at", "status_changed_by", "updated_at"])
            kept += 1
    return kept


# --- файлы товара и ссылки на них --------------------------------------------------------


def collect_objects(product: Product) -> list[models.Model]:
    """Все строки, которые удалит ``product.delete()``, в порядке восстановления (родители раньше).

    Доменные записи (все, не только текущего типа) удаляет сигнал pre_delete товара —
    их деревья собираются отдельно.
    """
    roots = [product, *domain_records(product)]
    ordered: list[models.Model] = []
    for root in roots:
        collector = Collector(using=router.db_for_write(type(root)))
        collector.collect([root])
        collector.sort()
        # Collector удаляет так: сначала fast_deletes (дети), затем data (дети → родители).
        chain: list[models.Model] = []
        for queryset in collector.fast_deletes:
            if not queryset.model._meta.auto_created:  # строки M2M — в полях самих объектов
                chain.extend(queryset)
        for instances in collector.data.values():
            chain.extend(instances)
        ordered.extend(reversed(chain))
    return ordered


def shadow_products(objects: Iterable[models.Model], product_id: int) -> list[int]:
    """Другие товары, которые удалит каскад: теневые товары вариантов одежды/обуви.

    Удаление ``ClothingVariant``/``ShoeVariant`` удаляет Product с
    ``external_data.source_variant_id/slug`` этого варианта (``models._cleanup_variant_products``).
    """
    from apps.catalog.models import ClothingVariant, ShoeVariant

    query = Q()
    for obj in objects:
        if isinstance(obj, (ClothingVariant, ShoeVariant)):
            query |= Q(external_data__source_variant_id=obj.pk) | Q(external_data__source_variant_slug=obj.slug)
    if not query:
        return []
    return list(Product.objects.filter(query).exclude(pk=product_id).values_list("pk", flat=True)[:20])


def _value_text(value: Any) -> str:
    return str(getattr(value, "name", value) or "")


def _value_keys(text: str, odd_keys: Iterable[str] = ()) -> list[str]:
    """Все ключи ``products/…`` в значении поля, включая URL и ?path=.

    ``odd_keys`` — ключи с пробелом, ``&``, ``#``…: регулярка их обрезала бы, ищем точным вхождением.
    """
    if "products/" not in text:
        return []
    decoded = unquote(text)
    found = _PRODUCT_KEY.findall(text) + _PRODUCT_KEY.findall(decoded)
    for key in odd_keys:
        found += [key] * (text.count(key) + decoded.count(key))
    return found


def _own_key(model_field: models.Field, value: Any) -> str:
    """Ключ нашего хранилища, если поле указывает на наш файл товара; иначе ''."""
    from apps.catalog.signals import _get_path_from_storage_url, is_internal_storage_url

    text = _value_text(value).strip()
    if not text:
        return ""
    if isinstance(model_field, models.FileField):
        key = text.lstrip("/")
    elif text.startswith(("http://", "https://")):
        key = _get_path_from_storage_url(text) if is_internal_storage_url(text) else ""
    else:
        key = text.lstrip("/")
        if key.startswith("media/"):
            key = key[len("media/"):]
    key = key or ""
    if not key.startswith("products/") or key.startswith(_PROTECTED_PREFIXES):
        return ""
    return key


def _media_fields_by_model() -> dict[type, list[models.Field]]:
    fields: dict[type, list[models.Field]] = defaultdict(list)
    for model, name in media_reference_fields():
        fields[model].append(model._meta.get_field(name))
    return fields


def product_media(objects: Iterable[models.Model]) -> tuple[set[str], Counter]:
    """Файлы товара (наш R2, ``products/…``) и сколько раз сами строки товара на них ссылаются."""
    fields = _media_fields_by_model()
    objects = list(objects)
    values = [
        (model_field, getattr(obj, model_field.attname, None))
        for obj in objects
        for model_field in fields.get(type(obj)._meta.concrete_model, [])
    ]
    own = {key for key in (_own_key(model_field, value) for model_field, value in values) if key}
    odd = [key for key in own if _KEY_STOP.search(key)]
    counts: Counter = Counter()
    for _model_field, value in values:
        counts.update(key for key in _value_keys(_value_text(value), odd) if key in own)
    return own, counts


def reference_counts(keys: set[str]) -> Counter:
    """Сколько значений во всей БД ссылается на каждый из ``keys``. Сбой чтения — исключение."""
    counts: Counter = Counter()
    if not keys:
        return counts
    odd = [key for key in keys if _KEY_STOP.search(key)]
    for model, name in media_reference_fields():
        try:
            values = (
                model._base_manager.filter(**{f"{name}__contains": "products/"})
                .values_list(name, flat=True)
                .iterator(chunk_size=2000)
            )
            for value in values:
                for key in _value_keys(_value_text(value), odd):
                    if key in keys:
                        counts[key] += 1
        except Exception as exc:  # noqa: BLE001 — не знаем, кто ссылается, — не удаляем
            raise MediaReferenceCheckError(f"{model._meta.label}.{name}: {exc}") from exc
    return counts


# --- хранилище и копия -------------------------------------------------------------------


class MediaGateway:
    """Файлы в R2 и их копия в бакете бэкапов (``media/<ключ>``, как у ночной копии медиа)."""

    def __init__(self, source=None, target=None):
        self._source = source
        self._target = target

    @property
    def source(self):
        if self._source is None:
            from apps.monitoring.media_backup import media_client

            self._source = media_client()
        return self._source

    @property
    def target(self):
        if self._target is None:
            from apps.monitoring import db_backup

            self._target = db_backup.s3_client()
        return self._target

    def check_ready(self) -> None:
        if not (
            getattr(settings, "USE_R2", False)
            and getattr(settings, "MEDIA_BACKUP_ENABLED", False)
            and getattr(settings, "DB_BACKUP_S3_BUCKET", "")
        ):
            raise StaleProductsRefused(
                "Нет резервной копии медиа (MEDIA_BACKUP_ENABLED, DB_BACKUP_S3_BUCKET) — удалять файлы без копии нельзя."
            )

    @staticmethod
    def _key(path: str) -> str:
        location = (getattr(settings, "R2_CONFIG", {}).get("prefix", "") or "").strip("/")
        return f"{location}/{path}" if location else path

    @staticmethod
    def _head_size(client, bucket: str, key: str) -> int | None:
        from botocore.exceptions import ClientError

        try:
            return int(client.head_object(Bucket=bucket, Key=key)["ContentLength"])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def size(self, path: str) -> int | None:
        return self._head_size(self.source, settings.R2_BUCKET_NAME, self._key(path))

    def backup(self, path: str) -> int | None:
        """Копия файла в бакет бэкапов; размер файла или None, если его уже нет в R2."""
        from apps.monitoring.db_backup import BackupError
        from apps.monitoring.media_backup import KEY_PREFIX, _stream

        size = self.size(path)
        if size is None:
            return None
        key = self._key(path)
        target_key = KEY_PREFIX + key
        if self._head_size(self.target, settings.DB_BACKUP_S3_BUCKET, target_key) != size:
            _stream(self.source, settings.R2_BUCKET_NAME, key, self.target,
                    settings.DB_BACKUP_S3_BUCKET, target_key, {"stale-product-delete": "1"})
            stored = self._head_size(self.target, settings.DB_BACKUP_S3_BUCKET, target_key)
            if stored != size:
                raise BackupError(f"в копии {stored} байт вместо {size}: {path}")
        return size

    def delete(self, path: str) -> None:
        self.source.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=self._key(path))

    def restore(self, path: str) -> bool:
        """Вернуть файл из копии. False — файл уже на месте; исключение — копии нет."""
        from apps.monitoring.media_backup import KEY_PREFIX, _stream

        if self.size(path) is not None:
            return False
        key = self._key(path)
        _stream(self.target, settings.DB_BACKUP_S3_BUCKET, KEY_PREFIX + key,
                self.source, settings.R2_BUCKET_NAME, key, {})
        return True


# --- оценка для страницы удаления ----------------------------------------------------------


def refresh_media_stats(*, limit: int = 300, gateway: MediaGateway | None = None, now=None) -> dict[str, int]:
    """Сколько файлов и МБ освободит удаление каждого кандидата (общие с другими товарами — не в счёт)."""
    now = now or timezone.now()
    gateway = gateway or MediaGateway()
    candidates = list(
        StaleProductCandidate.objects.filter(
            status__in=[StaleProductCandidate.Status.CANDIDATE, StaleProductCandidate.Status.HIDDEN]
        )
        .filter(Q(media_stats_at__isnull=True) | Q(media_stats_at__lt=now - timedelta(hours=20)))
        .select_related("product")
        .order_by("media_stats_at", "pk")[:limit]
    )
    own: dict[int, tuple[set[str], Counter]] = {}
    for candidate in candidates:
        own[candidate.pk] = product_media(collect_objects(candidate.product))
    everywhere = reference_counts(set().union(*(keys for keys, _ in own.values())) if own else set())
    for candidate in candidates:
        keys, own_counts = own[candidate.pk]
        free = [key for key in keys if everywhere[key] <= own_counts[key]]
        candidate.files_total = len(keys)
        candidate.files_to_free = len(free)
        candidate.bytes_to_free = sum(gateway.size(key) or 0 for key in free)
        candidate.media_stats_at = now
        candidate.save(update_fields=["files_total", "files_to_free", "bytes_to_free", "media_stats_at", "updated_at"])
    return {"candidates": len(candidates)}


# --- окончательное удаление --------------------------------------------------------------


def recheck_at_source(candidate: StaleProductCandidate) -> str:
    """Проверка всех ссылок товара прямо перед удалением: ``gone``, только если пропали все."""
    urls: dict[str, ProductSourceOffer] = {}
    for offer in candidate.product.source_offers.filter(
        is_active=True, parser_key=candidate.parser_key
    ).order_by("priority", "pk"):
        urls.setdefault(offer.canonical_url, offer)
    if not urls:
        return "error"
    for offer in urls.values():
        verdict = _recheck_url(candidate.product, offer)
        if verdict != "gone":
            return verdict
    return "gone"


def _recheck_url(product: Product, offer: ProductSourceOffer) -> str:
    """Одна ссылка товара у продавца: ``gone``, ``present`` или ``error``."""
    from apps.catalog.services.nightly_stock_check import NightlyStockCheckService, source_rate_per_minute
    from apps.catalog.services.product_card_source_refresh import ProductCardRefreshError, RefreshTarget
    from apps.catalog.services.source_offer_verification import SourceOfferVerificationService

    verifier = SourceOfferVerificationService()
    parser_class = verifier._trusted_parser_class(offer)
    if parser_class is None:
        return "error"
    service = NightlyStockCheckService()
    target = RefreshTarget(product=product, offer=offer, parser_class=parser_class)
    with verifier._source_slot(target.parser_key, 120) as acquired:
        if not acquired:
            return "error"
        try:
            service._fetch_product(target)
        except ProductCardRefreshError as exc:
            return "gone" if exc.code == "source_not_found" else "error"
        except Exception:  # noqa: BLE001 — сеть, вёрстка: не уверены — не удаляем
            logger.warning("stale_product_recheck_failed", exc_info=True, extra={"product_id": product.pk})
            return "error"
        finally:
            time.sleep(60.0 / source_rate_per_minute(target.parser_key))
    return "present"


class _Skip(Exception):
    """Товар не удаляется; текст — причина для отчёта."""


def _deletion_blocker(candidate: StaleProductCandidate, product: Product, objects, *, now=None) -> str:
    """Почему товар нельзя удалить прямо сейчас ('' — можно). Проверяется заново под блокировкой строк."""
    now = now or timezone.now()
    if candidate.status != StaleProductCandidate.Status.HIDDEN:
        return f"статус изменился: «{candidate.get_status_display()}»"
    if product.is_active:
        return "товар снова на сайте"
    if candidate.hidden_at is None or candidate.hidden_at > now - timedelta(days=delete_after_hidden_days()):
        return "скрыт недавно"
    protected = protection_reasons([product]).get(product.pk)
    if protected:
        return "только скрыть: " + ", ".join(protected)
    shadows = shadow_products(objects, product.pk)
    if shadows:
        return f"удаление задело бы другие товары (теневые варианты: {', '.join(map(str, shadows[:5]))})"
    return ""


def _delete_one(candidate: StaleProductCandidate, user, gateway: MediaGateway) -> ProductDeletionLog:
    from apps.catalog.signals import storage_deletes_suppressed

    objects = collect_objects(candidate.product)
    reason = _deletion_blocker(candidate, candidate.product, objects)
    if reason:
        raise _Skip(reason)
    keys, _ = product_media(objects)
    files = []
    for key in sorted(keys):
        size = gateway.backup(key)  # исключение — товар не удаляется
        files.append({"path": key, "size": size, "state": "backed_up" if size is not None else "missing"})
    with transaction.atomic():
        # Перепроверка у продавца и копия заняли время: за это товар могли «Оставить»,
        # вернуть на сайт или поправить. Решение — по строкам под блокировкой.
        candidate = (
            StaleProductCandidate.objects.select_for_update().filter(pk=candidate.pk).first()
        )
        if candidate is None:
            raise _Skip("пометка уже снята")
        product = Product.objects.select_for_update().get(pk=candidate.product_id)
        objects = collect_objects(product)
        reason = _deletion_blocker(candidate, product, objects)
        if reason:
            raise _Skip(reason)
        if not product_media(objects)[0] <= keys:
            raise _Skip("у товара появились новые файлы — запустите удаление ещё раз")
        log = ProductDeletionLog.objects.create(
            deleted_by=user,
            product_id=product.pk,
            product_name=product.name[:500],
            product_type=product.product_type or "",
            parser_key=candidate.parser_key,
            source_url=candidate.source_url,
            first_seen_at=candidate.first_seen_at,
            hidden_at=candidate.hidden_at,
            rows_backup=zlib.compress(serializers.serialize("json", objects).encode(), 6),
            objects_count=len(objects),
            files=files,
        )
        with storage_deletes_suppressed():
            product.delete()
    return log


def _delete_unreferenced_files(logs: list[ProductDeletionLog], gateway: MediaGateway) -> str:
    """Удаляет файлы удалённых товаров, на которые больше никто не ссылается. Возвращает ошибку или ''."""
    keys = {item["path"] for log in logs for item in log.files if item["state"] == "backed_up"}
    try:
        still_used = reference_counts(keys)
    except MediaReferenceCheckError as exc:
        # Файлы остаются (их копия есть); удалит позже cleanup_orphaned_media.
        logger.error("stale_products_reference_check_failed: %s", exc)
        return f"Проверка ссылок не прошла ({exc}) — файлы не удалялись."
    for log in logs:
        for item in log.files:
            if item["state"] != "backed_up":
                continue
            if still_used[item["path"]]:
                item["state"] = "shared"
                continue
            try:
                gateway.delete(item["path"])
            except Exception as exc:  # noqa: BLE001 — файл останется, его удалит cleanup_orphaned_media
                item["state"] = "delete_failed"
                logger.warning("stale_product_file_delete_failed %s: %s", item["path"], exc)
                continue
            item["state"] = "deleted"
            log.files_deleted += 1
            log.bytes_freed += item["size"] or 0
        log.save(update_fields=["files", "files_deleted", "bytes_freed"])
    return ""


def delete_candidates(
    candidate_ids: Iterable[int],
    user=None,
    *,
    gateway: MediaGateway | None = None,
    recheck: Callable[[StaleProductCandidate], str] = recheck_at_source,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Шаг 2: удалить скрытых давно кандидатов вместе с файлами. Запускает Celery-задача из админки."""
    gateway = gateway or MediaGateway()
    # Задача: soft/hard limit 100/110 минут. Перепроверки и удаление строк — не дольше
    # бюджета, остаток времени — на одну проверку ссылок и удаление файлов.
    budget = _setting_int("STALE_PRODUCT_DELETE_BUDGET_SECONDS", 75 * 60, minimum=60, maximum=95 * 60)
    with media_delete_lock(2 * 3600) as acquired:
        if not acquired:
            return {"status": "busy"}
        candidates = list(StaleProductCandidate.objects.filter(pk__in=list(candidate_ids)).select_related("product"))
        plan = plan_action(candidates, "delete")
        if plan.refusal:
            raise StaleProductsRefused(plan.refusal)
        gateway.check_ready()
        result: dict[str, Any] = {"status": "completed", "deleted": [], "returned": [], "skipped": []}
        logs: list[ProductDeletionLog] = []
        deadline = clock() + budget
        try:
            for index, candidate in enumerate(plan.eligible):
                if clock() >= deadline:
                    left = len(plan.eligible) - index
                    result["skipped"].append((f"ещё {left} товаров", "не успели за один запуск — запустите удаление ещё раз"))
                    break
                verdict = recheck(candidate)
                if verdict == "present":
                    StaleProductCandidate.objects.filter(
                        pk=candidate.pk, status=StaleProductCandidate.Status.HIDDEN
                    ).update(status=StaleProductCandidate.Status.RETURNED, updated_at=timezone.now())
                    result["returned"].append(candidate.product.name)
                    continue
                if verdict != "gone":
                    result["skipped"].append((candidate.product.name, "не удалось проверить у продавца"))
                    continue
                try:
                    logs.append(_delete_one(candidate, user, gateway))
                except _Skip as skip:
                    result["skipped"].append((candidate.product.name, str(skip)))
                    continue
                except Exception as exc:  # noqa: BLE001 — один товар не останавливает остальные
                    logger.exception("stale_product_delete_failed", extra={"product_id": candidate.product_id})
                    result["skipped"].append((candidate.product.name, f"ошибка: {type(exc).__name__}"))
                    continue
                result["deleted"].append(candidate.product.name)
        finally:
            # Строки уже удалены — файлы удаляются и при обрыве цикла.
            result["files_error"] = _delete_unreferenced_files(logs, gateway) if logs else ""
        result["files_deleted"] = sum(log.files_deleted for log in logs)
        result["bytes_freed"] = sum(log.bytes_freed for log in logs)
        result["shared_kept"] = sum(1 for log in logs for item in log.files if item["state"] == "shared")
        result["excluded"] = len(plan.excluded)
        return result


def deletion_report(result: dict[str, Any]) -> str:
    lines = [
        f"🗑 Удаление неактуальных товаров: удалено {len(result['deleted'])}, "
        f"файлов {result['files_deleted']} ({result['bytes_freed'] / 1024 / 1024:.1f} МБ)."
    ]
    if result.get("shared_kept"):
        lines.append(f"Общие с другими товарами файлы оставлены: {result['shared_kept']}.")
    if result.get("returned"):
        lines.append(f"Снова есть у продавца, не удалены: {len(result['returned'])}.")
    if result.get("skipped"):
        lines.append(
            f"Пропущены: {len(result['skipped'])} — "
            + "; ".join(f"{name[:40]}: {why}" for name, why in result["skipped"][:5])
        )
    if result.get("files_error"):
        lines.append(result["files_error"])
    keep = getattr(settings, "MEDIA_BACKUP_KEEP_DELETED_DAYS", 30)
    lines.append(f"Вернуть можно в админке «Журнал удалений товаров»: файлы хранятся в копии {keep} дней.")
    return "\n".join(lines)


# --- восстановление ----------------------------------------------------------------------


def restore_deletion(log: ProductDeletionLog, user=None, *, gateway: MediaGateway | None = None) -> list[str]:
    """Вернуть строки БД из журнала и файлы из копии. Возвращает файлы, которые вернуть не удалось."""
    if log.status != ProductDeletionLog.Status.DELETED:
        raise StaleProductsRefused("Этот товар уже восстановлен.")
    if Product.objects.filter(pk=log.product_id).exists():
        raise StaleProductsRefused(f"Товар с ID {log.product_id} уже есть в базе.")
    gateway = gateway or MediaGateway()
    rows = zlib.decompress(bytes(log.rows_backup)).decode()
    with media_delete_lock(30 * 60) as acquired:
        if not acquired:
            # Иначе cleanup_orphaned_media мог бы удалить только что возвращённые файлы.
            raise StaleProductsRefused("Сейчас идёт удаление файлов — повторите через час.")
        # Сначала файлы: сигналы картинок, не найдя файла, скачали бы его заново по ссылке продавца.
        # Все, у кого есть копия: и не удалённые (общие, сбой удаления) могла уже убрать
        # cleanup_orphaned_media. Файл на месте — restore его не трогает.
        failed = []
        for item in log.files:
            if item.get("state") == "missing":
                continue
            try:
                gateway.restore(item["path"])
            except Exception:  # noqa: BLE001 — копия могла истечь
                failed.append(item["path"])
        with transaction.atomic():
            for deserialized in serializers.deserialize("json", rows):
                deserialized.save()
    log.status = ProductDeletionLog.Status.RESTORED
    log.restored_at = timezone.now()
    log.restored_by = user
    if failed:
        log.note = f"Не вернулись файлы ({len(failed)}): " + ", ".join(failed[:20])
    log.save(update_fields=["status", "restored_at", "restored_by", "note"])
    return failed
