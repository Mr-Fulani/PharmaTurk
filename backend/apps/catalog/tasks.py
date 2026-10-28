"""Celery tasks for catalog refresh, source checks, pricing and media."""
from __future__ import annotations

from array import array
from celery import shared_task
from django.core.management import call_command
import hashlib
import logging

from apps.catalog.services import MedicineMediaEnricher

logger = logging.getLogger(__name__)


@shared_task(
    name="catalog.refresh_medicine_market_check",
    soft_time_limit=100,
    time_limit=120,
    acks_late=True,
)
def refresh_medicine_market_check_task(check_id: int) -> dict:
    """Refresh one user-requested medicine reference price and its equivalents."""

    from apps.catalog.services.medicine_market_check import MedicineMarketCheckService

    return MedicineMarketCheckService().run(check_id)


@shared_task(
    name="catalog.refresh_supplement_market_check",
    soft_time_limit=100,
    time_limit=120,
    acks_late=True,
)
def refresh_supplement_market_check_task(check_id: int) -> dict:
    """Refresh one user-requested supplement reference price."""

    from apps.catalog.services.supplement_market_check import (
        SupplementMarketCheckService,
    )

    return SupplementMarketCheckService().run(check_id)


@shared_task(
    bind=True,
    name="catalog.discover_supplement_stock_offer",
    soft_time_limit=55,
    time_limit=60,
    acks_late=True,
    max_retries=2,
    default_retry_delay=60,
)
def discover_supplement_stock_offer_task(self, supplement_id: int) -> dict:
    """Discover one supplement seller identity independently of reference price."""

    from apps.catalog.models import SupplementProduct
    from apps.catalog.services.supplement_stock_discovery import (
        SupplementStockDiscoveryError,
        SupplementStockDiscoveryService,
    )

    supplement = (
        SupplementProduct.objects.select_related("base_product")
        .filter(pk=supplement_id, is_active=True)
        .first()
    )
    if supplement is None:
        return {"status": "missing", "supplement_id": supplement_id}

    try:
        result = SupplementStockDiscoveryService().discover(supplement)
    except SupplementStockDiscoveryError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        logger.warning(
            "supplement_stock_discovery_task_failed",
            extra={
                "supplement_id": supplement_id,
                "product_id": supplement.base_product_id,
                "error_code": exc.code,
                "retryable": exc.retryable,
            },
        )
        return {
            "status": "error",
            "supplement_id": supplement_id,
            "error_code": exc.code,
            "retryable": exc.retryable,
        }

    return {
        "status": result.status,
        "supplement_id": supplement_id,
        "offer_id": result.offer.pk if result.offer is not None else None,
    }


@shared_task(
    name="catalog.refresh_product_card_source",
    soft_time_limit=100,
    time_limit=120,
    acks_late=True,
)
def refresh_product_card_source_task(product_id: int, lock_token: str) -> dict:
    """Refresh one parsed card without invoking the content-import pipeline."""

    from apps.catalog.services.product_card_source_refresh import (
        ProductCardSourceRefreshService,
    )

    service = ProductCardSourceRefreshService()
    try:
        return service.run(product_id)
    finally:
        service.release_lock(product_id, lock_token)


@shared_task(
    name="catalog.nightly_stock_check",
    soft_time_limit=60 * 11,
    time_limit=60 * 12,
    expires=60 * 9,
)
def nightly_stock_check_task() -> dict:
    """Пачка ночной сверки наличия (docs/NIGHTLY_STOCK_CHECK.md); Beat — раз в 10 минут ночью."""
    from apps.catalog.services.nightly_stock_check import run_nightly_batch

    return run_nightly_batch()


@shared_task(name="catalog.nightly_stock_check_report", soft_time_limit=120, time_limit=180)
def nightly_stock_check_report_task() -> dict:
    """Итог ночной сверки владельцу в Telegram."""
    from apps.catalog.services.nightly_stock_check import send_night_report

    return send_night_report()


@shared_task(
    bind=True,
    name="catalog.delete_stale_products",
    soft_time_limit=100 * 60,
    time_limit=110 * 60,
    max_retries=8,
)
def delete_stale_products_task(self, candidate_ids: list[int], user_id: int | None = None) -> dict:
    """Окончательное удаление неактуальных товаров по решению в админке (docs/STALE_PRODUCTS.md)."""
    from django.contrib.auth import get_user_model

    from apps.catalog.services.stale_products import (
        StaleProductsRefused,
        delete_candidates,
        deletion_report,
    )
    from apps.monitoring.watchdog import send_admin_telegram_notification

    user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    try:
        result = delete_candidates(candidate_ids, user)
    except StaleProductsRefused as exc:
        send_admin_telegram_notification(f"🗑 Удаление неактуальных товаров отменено: {exc}")
        return {"status": "refused", "reason": str(exc)}
    if result["status"] == "busy":
        # Идёт cleanup_orphaned_media или другое удаление — повтор через 15 минут.
        raise self.retry(countdown=15 * 60)
    send_admin_telegram_notification(deletion_report(result))
    return result


@shared_task(name="catalog.stale_products_media_stats", soft_time_limit=20 * 60, time_limit=25 * 60)
def stale_products_media_stats_task() -> dict:
    """Сколько файлов и МБ освободит удаление кандидатов — для страницы «Неактуальные товары»."""
    from django.conf import settings

    from apps.catalog.models_stock import StaleProductCandidate
    from apps.catalog.services.stale_products import refresh_media_stats

    if not getattr(settings, "USE_R2", False):
        return {"status": "skipped", "reason": "no_r2"}
    if not StaleProductCandidate.objects.exists():
        return {"status": "skipped", "reason": "no_candidates"}
    return refresh_media_stats()


# Задачи для системы ценообразования
@shared_task(name='currency.update_rates')
def update_currency_rates():
    """Периодическое обновление курсов валют."""
    try:
        logger.info("Starting currency rates update...")
        
        from .utils.currency_service import CurrencyRateService
        service = CurrencyRateService()
        success, message = service.update_rates()
        
        if success:
            logger.info(f"Currency rates updated successfully: {message}")
            return {'status': 'success', 'message': message}
        else:
            logger.error(f"Currency rates update failed: {message}")
            return {'status': 'error', 'message': message}
            
    except Exception as e:
        logger.error(f"Exception in currency rates update: {str(e)}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='currency.update_product_prices')
def update_product_prices_batch(product_type=None, batch_size=100):
    """Периодическое обновление цен товаров."""
    try:
        logger.info(f"Starting product prices update for type: {product_type}")
        
        # Вызываем management команду
        call_command(
            'update_product_prices',
            product_type=product_type,
            batch_size=batch_size,
            force_update_rates=False  # Не обновляем курсы каждый раз
        )
        
        logger.info("Product prices update completed successfully")
        return {'status': 'success', 'message': 'Product prices updated'}
        
    except Exception as e:
        logger.error(f"Exception in product prices update: {str(e)}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='currency.refresh_margin_snapshots')
def refresh_currency_margin_snapshots_task():
    """Применяет актуальные маржи валютных пар к сохранённым конвертированным ценам."""
    from .currency_price_snapshots import refresh_currency_margin_snapshots

    return refresh_currency_margin_snapshots()


@shared_task(name='currency.refresh_usdt_price_snapshots')
def refresh_usdt_price_snapshots_task():
    """Пересчитывает сохранённые цены после изменения глобальной USDT-наценки."""
    from .currency_price_snapshots import refresh_usdt_price_snapshots

    return refresh_usdt_price_snapshots()


@shared_task(name='currency.cleanup_old_logs')
def cleanup_old_currency_logs(days_to_keep=30):
    """Очистка старых логов обновления курсов."""
    try:
        from django.utils import timezone
        from datetime import timedelta
        from .currency_models import CurrencyUpdateLog
        
        cutoff_date = timezone.now() - timedelta(days=days_to_keep)
        
        deleted_count = CurrencyUpdateLog.objects.filter(
            created_at__lt=cutoff_date
        ).delete()[0]
        
        logger.info(f"Cleaned up {deleted_count} old currency update logs")
        return {
            'status': 'success', 
            'deleted_count': deleted_count,
            'message': f'Cleaned up {deleted_count} old logs'
        }
        
    except Exception as e:
        logger.error(f"Exception in currency logs cleanup: {str(e)}")
        return {'status': 'error', 'message': str(e)}


def _normalize_media_path(path: str) -> str:
    """Нормализация пути для сравнения: убрать лишние слэши, префиксы dev/prod, привести к единому виду."""
    if not path or not isinstance(path, str):
        return ""
    
    # Убираем /media/ если есть (из URL)
    if path.startswith("/media/"):
        path = path[len("/media/"):]
        
    p = path.strip("/").replace("//", "/")
    
    # Убираем префикс R2 если он там есть
    from django.conf import settings
    prefix = (getattr(settings, "R2_CONFIG", {}).get("prefix", "") or "").strip("/")
    if prefix and p.startswith(prefix + "/"):
        p = p[len(prefix) + 1:]
    elif prefix and p == prefix:
        return ""
        
    return p


def _iter_db_media_paths(unreadable_fields: list):
    """
    Пути медиа из БД по одному, без загрузки всего списка в память.
    Обходит все FileField/ImageField/URLField всех моделей, чтобы новые модели
    и поля не пропускались. Поле, которое не удалось прочитать, попадает в
    unreadable_fields: без его путей файлы выглядели бы осиротевшими.
    """
    from django.apps import apps
    from django.db.models import FileField, URLField
    from urllib.parse import urlparse

    for model in apps.get_models():
        if model._meta.proxy:
            continue  # та же таблица, что у конкретной модели
        for field in model._meta.local_concrete_fields:
            if not isinstance(field, (FileField, URLField)):
                continue
            try:
                values = (
                    model._base_manager.exclude(**{f"{field.name}__isnull": True})
                    .exclude(**{field.name: ""})
                    .values_list(field.name, flat=True)
                    .iterator(chunk_size=2000)
                )
                for value in values:
                    path = urlparse(value).path if isinstance(field, URLField) else value
                    normalized = _normalize_media_path(path)
                    if normalized:
                        yield normalized
            except Exception as e:
                unreadable_fields.append(f"{model._meta.label}.{field.name}")
                logger.warning("cleanup_orphaned_media: skip %s.%s: %s", model._meta.label, field.name, e)


def _media_fingerprint(path: str) -> int:
    """8-байтовый отпечаток пути. Совпадение отпечатков только сохраняет файл."""
    return int.from_bytes(hashlib.blake2b(path.encode(), digest_size=8).digest(), "big")


def _iter_storage_paths(storage):
    """Ключи хранилища по одному, без построения полного списка."""
    bucket = getattr(storage, "bucket", None)
    if bucket is not None:
        # S3/R2: плоский постраничный листинг (по 1000 ключей за запрос).
        location = (getattr(storage, "location", "") or "").strip("/")
        prefix = f"{location}/" if location else ""
        for obj in bucket.objects.filter(Prefix=prefix):
            yield _normalize_media_path(obj.key[len(prefix):])
        return
    yield from _walk_storage(storage)


def _walk_storage(storage, path=""):
    dirs, files = storage.listdir(path)
    for f in files:
        yield _normalize_media_path(f"{path}/{f}" if path else f)
    for d in dirs:
        yield from _walk_storage(storage, f"{path}/{d}" if path else d)


# Префиксы путей, которые НИКОГДА не удалять (AI-обработка, кэш, временные файлы, аватарки).
# Файлы здесь не привязаны к моделям Django или привязаны, но могут не попасть в _collect_db_media_paths.
_PROTECTED_STORAGE_PREFIXES = (
    "products/original/",
    "products/processed/",
    "products/thumbs/",
    "temp/",
    "avatars/",  # аватарки пользователей (users.User.avatar)
    "testimonials/",  # аватарки авторов отзывов (feedback.Testimonial.author_avatar)
    "feeds/",  # готовые YML-фиды (YMLFeedSnapshot); старые файлы удаляет сама сборка
)

# Известные корневые директории медиа
_KNOWN_ROOT_DIRS = (
    "products/", "temp/", "avatars/", "testimonials/", "marketing/", "services/"
)

# Префиксы других окружений — не удалять при очистке.
# На проде (R2_PREFIX="") listdir возвращает весь бакет, включая dev/.
# Без этой защиты prod-задача удаляла бы медиа из dev/.
_OTHER_ENV_PREFIXES = ("dev/", "staging/", "test/", "local/")


def _is_protected_path(path: str) -> bool:
    """Проверить, что путь защищён от удаления."""
    if not path:
        return True
    
    # Если путь начинается с папки, которая не является известной (например, префикс разработчика `misha/`),
    # мы всегда защищаем этот путь, чтобы продакшен скрипт не удалял локальные файлы.
    has_known_root = any(path.startswith(r) for r in _KNOWN_ROOT_DIRS)
    if not has_known_root and "/" in path:
        return True

    normalized = _normalize_media_path(path)
    
    for prefix in _PROTECTED_STORAGE_PREFIXES:
        if normalized.startswith(prefix) or path.startswith(prefix):
            return True
            
    # Не удалять файлы из других окружений (dev/, staging/ и т.д.)
    for prefix in _OTHER_ENV_PREFIXES:
        if normalized.startswith(prefix) or path.startswith(prefix):
            return True
            
    return False


_CLEANUP_MIN_DB_PATHS = 100


def _report_cleanup_abort(result: dict, sample: list) -> None:
    from apps.monitoring.watchdog import send_admin_telegram_notification

    lines = [
        f"⚠️ cleanup_orphaned_media: удаление отменено ({result['reason']})",
        f"Путей в БД: {result['db_paths']}, файлов в хранилище: {result['storage']}, "
        f"к удалению: {result['orphaned']} (лимит {result['max_delete']} / {result['max_delete_percent']}%)",
    ]
    if result.get("unreadable_fields"):
        lines.append("Не прочитаны поля: " + ", ".join(result["unreadable_fields"][:10]))
    if sample:
        lines.append("Примеры: " + ", ".join(sample[:10]))
    lines.append("Ручной запуск с другим лимитом: CELERY_TASKS.md, «Очистка orphaned media»")
    send_admin_telegram_notification("\n".join(lines))


@shared_task(name="catalog.cleanup_orphaned_media", soft_time_limit=60 * 55, time_limit=60 * 60)
def cleanup_orphaned_media(dry_run=False, max_delete=None, max_delete_percent=None):
    """
    Удаление файлов из R2/локального хранилища, которых нет в БД.
    Не удаляет: защищённые префиксы (AI, temp), пути других окружений (dev/, staging/).
    На проде (R2_PREFIX="") листинг возвращает весь бакет — без защиты dev/ файлы удалялись бы.

    Память: из БД держим только 8-байтовые отпечатки путей, хранилище читаем
    потоково. Если к удалению больше max_delete файлов или max_delete_percent
    процентов хранилища — ничего не удаляем, только отчёт админу в Telegram.
    """
    from django.conf import settings
    if getattr(settings, 'DEBUG', False):
        logger.info("cleanup_orphaned_media skipped: DEBUG=True. (Prevents local celery from wiping shared media across developers using the same R2 prefix)")
        return {"status": "skipped", "message": "Disabled in DEBUG mode"}

    # Одно удаление файлов за раз: удаление неактуальных товаров и их восстановление
    # держат ту же блокировку (services/stale_products.py).
    from apps.catalog.services.stale_products import media_delete_lock

    with media_delete_lock(60 * 60) as acquired:
        if not acquired:
            logger.warning("cleanup_orphaned_media skipped: идёт удаление или восстановление товаров")
            return {"status": "skipped", "reason": "media_delete_busy", "deleted": 0}
        return _cleanup_orphaned_media(dry_run, max_delete, max_delete_percent)


def _cleanup_orphaned_media(dry_run, max_delete, max_delete_percent):
    from django.conf import settings
    import numpy as np
    from django.core.files.storage import default_storage

    if max_delete is None:
        max_delete = settings.ORPHANED_MEDIA_MAX_DELETE
    if max_delete_percent is None:
        max_delete_percent = settings.ORPHANED_MEDIA_MAX_DELETE_PERCENT

    try:
        unreadable_fields = []
        fingerprints = array("Q", (_media_fingerprint(p) for p in _iter_db_media_paths(unreadable_fields)))
        db_index = np.unique(np.frombuffer(fingerprints, dtype=np.uint64))  # отсортирован
        del fingerprints

        def referenced(path):
            fp = np.uint64(_media_fingerprint(path))
            i = np.searchsorted(db_index, fp)
            return i < len(db_index) and db_index[i] == fp

        storage_total = 0
        protected = 0
        candidates = []  # не больше max_delete: при превышении удаления не будет
        orphaned = 0
        for path in _iter_storage_paths(default_storage):
            storage_total += 1
            if referenced(path):
                continue
            if _is_protected_path(path):
                protected += 1
                continue
            orphaned += 1
            if len(candidates) < max_delete:
                candidates.append(path)

        result = {
            "db_paths": len(db_index),
            "storage": storage_total,
            "protected_excluded": protected,
            "orphaned": orphaned,
            "max_delete": max_delete,
            "max_delete_percent": max_delete_percent,
            "deleted": 0,
        }
        logger.info("cleanup_orphaned_media: %s", result)
        if candidates:
            logger.info("cleanup_orphaned_media: first paths to delete: %s", candidates[:20])

        # Предохранители (инцидент 2026-06-14: стек с ПУСТОЙ БД + общий R2-бакет
        # стёр весь каталог, т.к. "осиротевшим" оказалось всё).
        reason = None
        if unreadable_fields:
            reason = "db_fields_unreadable"
            result["unreadable_fields"] = unreadable_fields
        elif len(db_index) < _CLEANUP_MIN_DB_PATHS:
            reason = "db_paths_too_low"
        elif orphaned > max_delete:
            reason = "max_delete_exceeded"
        elif orphaned * 100 > storage_total * max_delete_percent:
            reason = "max_delete_percent_exceeded"
        if reason:
            result.update(status="aborted", reason=reason)
            logger.error("cleanup_orphaned_media ABORTED: %s", result)
            if not dry_run:
                _report_cleanup_abort(result, candidates)
            return result
        if dry_run:
            result.update(status="dry_run", sample=candidates[:20])
            return result

        deleted = 0
        for path in candidates:
            try:
                # default_storage уже настроен на R2_PREFIX через location
                # поэтому удаление path удалит именно то, что нужно.
                default_storage.delete(path)
                deleted += 1
            except Exception as e:
                logger.warning("Failed to delete orphaned file %s: %s", path, e)
        logger.info("cleanup_orphaned_media: deleted %s orphaned files", deleted)
        result.update(status="success", deleted=deleted)
        return result
    except Exception as e:
        logger.exception("cleanup_orphaned_media failed: %s", e)
        from apps.monitoring.watchdog import send_admin_telegram_notification
        send_admin_telegram_notification(f"⚠️ cleanup_orphaned_media упала: {type(e).__name__}: {str(e)[:200]}")
        return {"status": "error", "message": str(e), "deleted": 0}


@shared_task(name='currency.health_check')
def currency_system_health_check():
    """Проверка здоровья системы валют."""
    try:
        from .models import Product
        from .currency_models import CurrencyRate
        
        # Проверяем наличие активных курсов
        active_rates = CurrencyRate.objects.filter(is_active=True).count()
        
        # Проверяем товары без цен
        products_without_prices = Product.objects.filter(
            price__isnull=True
        ).count()
        
        # Проверяем товары без конвертированных цен
        products_without_converted = Product.objects.filter(
            price__isnull=False,
            converted_price_rub__isnull=True
        ).count()
        
        health_data = {
            'active_rates': active_rates,
            'products_without_prices': products_without_prices,
            'products_without_converted': products_without_converted,
            'status': 'healthy'
        }
        
        # Если есть проблемы, меняем статус
        if active_rates == 0 or products_without_prices > 1000:
            health_data['status'] = 'warning'
        
        logger.info(f"Currency system health check: {health_data}")
        return health_data
        
    except Exception as e:
        logger.error(f"Exception in currency health check: {str(e)}")
        return {'status': 'error', 'message': str(e)}


@shared_task(
    name="catalog.enrich_medicine_media",
    bind=True, max_retries=2, default_retry_delay=300,
)
def enrich_medicine_media(
    self,
    product_ids: list[int] | None = None,
    max_images_per_product: int = 3,
    ignore_cache: bool = False,
    model_name: str = 'MedicineProduct',
    requested_by_user_id: int | None = None,
) -> dict:
    """
    Ручной поиск кандидатов медиа для MedicineProduct и SupplementProduct.

    Без явно переданных ``product_ids`` задача является безопасным no-op. Найденные
    файлы попадают только в очередь модерации и не изменяют товарную галерею.
    """
    try:
        from django.apps import apps
        from apps.catalog.models import MediaEnrichmentStatus

        if not product_ids or not requested_by_user_id:
            logger.warning(
                "Rejected media enrichment without an explicit manual product selection "
                "and staff initiator."
            )
            return {
                "status": "manual_selection_required",
                "products_processed": 0,
                "candidates_staged": 0,
                "images_added": 0,
                "errors": 0,
                "skipped": 0,
                "no_results": 0,
            }

        from django.contrib.auth import get_user_model

        requested_by = get_user_model().objects.filter(
            pk=requested_by_user_id,
            is_active=True,
            is_staff=True,
        ).first()
        if requested_by is None:
            logger.warning(
                "Rejected media enrichment with invalid staff initiator id=%s.",
                requested_by_user_id,
            )
            return {
                "status": "manual_selection_required",
                "products_processed": 0,
                "candidates_staged": 0,
                "images_added": 0,
                "errors": 0,
                "skipped": 0,
                "no_results": 0,
            }

        allowed_models = {"MedicineProduct", "SupplementProduct"}
        if model_name not in allowed_models:
            return {
                "status": "error",
                "message": "unsupported_model",
                "products_processed": 0,
                "candidates_staged": 0,
                "images_added": 0,
                "errors": 0,
                "skipped": 0,
                "no_results": 0,
            }

        ProductModel = apps.get_model('catalog', model_name)
        queryset = ProductModel.objects.filter(id__in=product_ids)
        queryset.update(
            media_enrichment_status=MediaEnrichmentStatus.PROCESSING,
            media_enrichment_error=None,
        )

        enricher = MedicineMediaEnricher()

        products_processed = 0
        candidates_staged = 0
        errors = 0
        skipped = 0
        no_results = 0

        for product in queryset:
            products_processed += 1
            try:
                staged = enricher.enrich(
                    product,
                    max_images_per_product,
                    ignore_cache=ignore_cache,
                    requested_by=requested_by,
                )
                candidates_staged += staged
                if product.media_enrichment_status == MediaEnrichmentStatus.FAILED:
                    errors += 1
                elif staged == 0:
                    from apps.catalog.services.medicine_media_enricher import (
                        MEDIA_ENRICHMENT_MAX_IMAGES,
                        MEDIA_ENRICHMENT_RECENT_NO_RESULT,
                    )

                    if product.media_enrichment_error in {
                        MEDIA_ENRICHMENT_MAX_IMAGES,
                        MEDIA_ENRICHMENT_RECENT_NO_RESULT,
                    }:
                        skipped += 1
                    else:
                        no_results += 1
            except Exception as e:
                logger.error("Failed to enrich media for product %s (%s): %s", product.id, model_name, e)
                product.media_enrichment_status = MediaEnrichmentStatus.FAILED
                product.media_enrichment_error = str(e)
                product.save(update_fields=['media_enrichment_status', 'media_enrichment_error'])
                errors += 1

        if errors == products_processed and products_processed:
            result_status = "error"
        elif errors:
            result_status = "partial"
        elif candidates_staged == 0:
            result_status = "no_changes"
        else:
            result_status = "success"

        return {
            "status": result_status,
            "products_processed": products_processed,
            "candidates_staged": candidates_staged,
            "images_added": 0,
            "errors": errors,
            "skipped": skipped,
            "no_results": no_results,
        }
    except Exception as e:
        logger.exception("enrich_medicine_media failed: %s", e)
        # Only retry if it's not a direct caller issue
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        return {"status": "error", "message": str(e)}


@shared_task(
    name="catalog.sync_ikea_products",
    bind=True, max_retries=3, default_retry_delay=300,
)
def sync_ikea_product_task(self, item_codes: list[str]) -> dict:
    """Задача: получение данных о товарах IKEA по артикулам."""
    from apps.catalog.services import IkeaService
    
    service = IkeaService()
    items = service.fetch_items(item_codes)
    
    processed = 0
    errors = 0
    
    for item in items:
        try:
            service.upsert_furniture_product(item)
            processed += 1
        except Exception as e:
            logger.error(f"Error upserting IKEA product: {str(e)}")
            errors += 1
            
    return {
        "status": "success",
        "processed": processed,
        "errors": errors,
        "total": len(item_codes)
    }


@shared_task(
    name="catalog.refresh_brand_product_counts",
    soft_time_limit=30,
    time_limit=45,
    expires=60,
)
def refresh_brand_product_counts_task():
    """Refresh display counts separately from requests; coalesce beat overlap."""
    from django.core.cache import cache
    from apps.catalog.brand_counts import refresh_brand_product_counts

    lock_key = "catalog:brand-product-counts:v1:refresh-lock"
    if not cache.add(lock_key, True, timeout=60):
        return {"status": "already_running"}
    try:
        counts = refresh_brand_product_counts()
        return {"status": "refreshed", "brands": len(counts)}
    finally:
        cache.delete(lock_key)


@shared_task(name="catalog.expire_new_badges")
def expire_new_badges() -> int:
    """Снимает «Новинку» с товаров старше NEW_BADGE_DAYS (парсер ставил её всем подряд)."""
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from apps.catalog.models import Product

    days = int(getattr(settings, "NEW_BADGE_DAYS", 30))
    cutoff = timezone.now() - timedelta(days=days)
    cleared = Product.objects.filter(is_new=True, created_at__lt=cutoff).update(is_new=False)
    logger.info("expire_new_badges: cleared %s products older than %s days", cleared, days)
    return cleared


@shared_task(name="catalog.recompute_sort_ranks")
def recompute_sort_ranks() -> dict:
    """Пересчитывает ранг медикаментов и БАДов для сортировки «Популярные»."""
    from apps.catalog.services.catalog_sort_rank import ranked_models, recompute_sort_ranks as recompute

    updated = {model._domain_product_type: recompute(model) for model in ranked_models()}
    logger.info("recompute_sort_ranks: updated %s", updated)
    return updated


@shared_task(name="catalog.generate_yml_feeds", soft_time_limit=60 * 50, time_limit=60 * 55)
def generate_yml_feeds() -> dict:
    """Собирает готовые YML-фиды частями: корневые категории, затем полный каталог (docs/VK_YML_FEED.md)."""
    from celery.exceptions import SoftTimeLimitExceeded
    from django.core.cache import cache

    from apps.catalog.services.yml_feed import generate_feed_files, prepared_feed_keys, remove_unlisted_feeds

    lock_key = "catalog:yml-feeds:generate-lock"
    if not cache.add(lock_key, True, timeout=60 * 55):
        return {"status": "already_running"}
    results = {}
    try:
        keys = prepared_feed_keys()
        # Разделы, которые выключили или заблокировали (лекарства), больше не отдаём.
        removed = remove_unlisted_feeds(keys)
        if removed:
            results["removed_parts"] = removed
        for key in keys:
            try:
                results[key or "catalog"] = [part.offers_count for part in generate_feed_files(key)]
            except SoftTimeLimitExceeded:
                raise
            except Exception:
                # Прежний файл остаётся в силе, остальные разделы собираем.
                logger.exception("generate_yml_feeds: фид %s не собран", key or "catalog")
                results[key or "catalog"] = "error"
    finally:
        cache.delete(lock_key)
    logger.info("generate_yml_feeds: %s", results)
    return results


@shared_task(name="catalog.sync_vk_photos", soft_time_limit=60 * 50, time_limit=60 * 55)
def sync_vk_photos_task(category_slug: str | None = None) -> str:
    """Фото и видео товаров в ВК Маркет (команда sync_vk_photos); итог — в Telegram админу."""
    import io

    from django.core.management.base import CommandError

    from apps.monitoring.watchdog import send_admin_telegram_notification

    label = f"раздел «{category_slug}»" if category_slug else "все разделы"
    out = io.StringIO()
    try:
        call_command("sync_vk_photos", category=category_slug, stdout=out)
        lines = [line for line in out.getvalue().splitlines() if line.strip()]
        summary = lines[-1].strip() if lines else "нет вывода"
    except CommandError as e:
        summary = f"ошибка: {e}"
    send_admin_telegram_notification(f"📸 Фото в ВК Маркет, {label}: {summary}")
    return summary
