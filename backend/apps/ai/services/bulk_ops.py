"""Общая логика массовых AI-операций.

Выборка товаров и оценка стоимости, повтор отклонённых названий БАДов и
закрытие решённой модерации. Используется командами ai_enqueue,
retry_ai_titles, close_resolved_ai_moderation и разделом админки
«AI-прогоны» (services/ai_runs.py), чтобы консоль и админка работали
одинаково.

``report(message, warning=False)`` — необязательный колбэк для построчного
вывода: команда печатает строки в консоль, прогон сохраняет их в отчёт.
"""

from decimal import Decimal

from django.db.models import Avg, Exists, OuterRef, Q

from apps.ai.models import AIModerationQueue, AIProcessingLog, AIProcessingStatus
from apps.ai.services.content_generator import SUPPLEMENT_TITLE_RETRY_REASONS, ContentGenerator
from apps.ai.services.ownership import SOURCE_CHANGED_KEY
from apps.ai.services.quality_checker import get_moderation_reasons
from apps.ai.tasks import ACTIVE_AI_LOG_STATUSES
from apps.catalog.models import Category, Product

# Оценка стоимости, если по типу товара ещё нет завершённых логов (USD, p90 аудита).
FALLBACK_COST_USD = {"medicines": Decimal("0.008")}
DEFAULT_COST_USD = Decimal("0.002")
# Один короткий запрос за RU/EN-названием БАДа.
TITLE_RETRY_COST_USD = Decimal("0.0002")
DONE_STATUSES = (
    AIProcessingStatus.COMPLETED,
    AIProcessingStatus.APPROVED,
    AIProcessingStatus.MODERATION,
    *ACTIVE_AI_LOG_STATUSES,
)


def _silent(message, warning=False):
    return None


def category_tree_ids(category):
    """id категории и всех её подкатегорий."""
    ids, frontier = {category.id}, [category.id]
    while frontier:
        frontier = list(
            Category.objects.filter(parent_id__in=frontier).exclude(id__in=ids).values_list("id", flat=True)
        )
        ids.update(frontier)
    return ids


def select_products_for_ai(
    *,
    product_types=(),
    category=None,
    ids=None,
    missing_description=False,
    source_changed=False,
    include_processed=False,
    processing_type="full",
):
    """Товары-кандидаты на AI-обработку в порядке id.

    Без ``include_processed`` пропускает товары с готовым, активным или
    ожидающим модерации логом; товары с ошибкой (в том числе отменённые
    при остановке прогона) остаются в выборке.
    """
    qs = Product.objects.all()
    if ids is not None:
        qs = qs.filter(id__in=ids)
    if product_types:
        qs = qs.filter(product_type__in=product_types)
    if category is not None:
        qs = qs.filter(category_id__in=category_tree_ids(category))
    if missing_description:
        qs = qs.filter(Q(description__isnull=True) | Q(description=""))
    if source_changed:
        qs = qs.filter(external_data__has_key=SOURCE_CHANGED_KEY)
    if not include_processed:
        done = AIProcessingLog.objects.filter(
            product_id=OuterRef("pk"),
            processing_type=processing_type,
            status__in=DONE_STATUSES,
        )
        qs = qs.exclude(Exists(done))
    return qs.order_by("id")


def estimate_ai_cost(product_ids):
    """Оценка в USD по средней стоимости прошлых логов того же типа товара."""
    total = Decimal("0")
    types = Product.objects.filter(id__in=product_ids).values_list("product_type", flat=True)
    averages = {}
    for product_type in types:
        if product_type not in averages:
            avg = AIProcessingLog.objects.filter(
                product__product_type=product_type, cost_usd__gt=0
            ).aggregate(value=Avg("cost_usd"))["value"]
            averages[product_type] = (
                Decimal(str(avg)) if avg else FALLBACK_COST_USD.get(product_type, DEFAULT_COST_USD)
            )
        total += averages[product_type]
    return total


def _open_moderation(product_types=()):
    queue = (
        AIModerationQueue.objects.filter(
            resolved_at__isnull=True,
            log_entry__status=AIProcessingStatus.MODERATION,
        )
        .select_related("log_entry__product")
        .order_by("id")
    )
    if product_types:
        queue = queue.filter(log_entry__product__product_type__in=product_types)
    return queue


def retry_supplement_titles(*, limit, dry_run=False, report=_silent):
    """Повторить отклонённые названия БАДов (см. команду retry_ai_titles).

    Возвращает ``{"selected", "fixed", "failed", "cost_usd"}``; при dry_run
    ``cost_usd`` — оценка, OpenAI не вызывается.
    """
    generator = None if dry_run else ContentGenerator()
    selected = fixed = failed = 0
    cost = Decimal("0")
    for task in _open_moderation(["supplements"]).iterator():
        if selected >= limit:
            break
        log = task.log_entry
        reasons = [r for r in get_moderation_reasons(log) if r in SUPPLEMENT_TITLE_RETRY_REASONS]
        if not reasons:
            continue
        selected += 1
        if dry_run:
            report(f"лог {log.id}, товар {log.product_id}: {', '.join(reasons)} — «{log.generated_title}»")
            continue

        attrs = dict(log.extracted_attributes or {})
        seo = dict(attrs.get("seo_translations") or {})
        ru_seo = dict(seo.get("ru") or {})
        en_seo = dict(seo.get("en") or {})
        content = {
            "ru": {"generated_title": ru_seo.get("generated_title") or log.generated_title},
            "en": {"generated_title": en_seo.get("generated_title") or ""},
        }
        content, retry = generator._retry_supplement_title(log.product, content)
        if not retry:
            failed += 1
            report(f"лог {log.id}: запрос не выполнен", warning=True)
            continue
        retry_cost = Decimal(str(retry.get("cost_usd") or 0))
        cost += retry_cost
        log.cost_usd = (log.cost_usd or Decimal("0")) + retry_cost
        raw = log.raw_llm_response if isinstance(log.raw_llm_response, dict) else {}
        log.raw_llm_response = {
            **raw,
            "title_retry": {
                "tokens": retry.get("tokens"),
                "cost_usd": retry.get("cost_usd"),
                "repaired_fields": retry.get("repaired_fields", []),
                "failed_fields": retry.get("failed_fields", []),
            },
        }
        update_fields = ["cost_usd", "raw_llm_response", "updated_at"]
        if retry.get("repaired_fields"):
            new_ru = content["ru"]["generated_title"]
            new_en = content["en"]["generated_title"]
            log.generated_title = generator._normalize_product_name(new_ru, "supplements")
            ru_seo["generated_title"] = new_ru
            seo["ru"] = ru_seo
            if new_en:
                en_seo["generated_title"] = new_en
                seo["en"] = en_seo
            attrs["seo_translations"] = seo
            log.extracted_attributes = attrs
            update_fields += ["generated_title", "extracted_attributes"]
            fixed += 1
            report(f"лог {log.id}: «{log.generated_title}» / «{new_en}»")
        else:
            failed += 1
            report(f"лог {log.id}: новое название не прошло проверку", warning=True)
        log.save(update_fields=update_fields)

    if dry_run:
        cost = selected * TITLE_RETRY_COST_USD
    return {"selected": selected, "fixed": fixed, "failed": failed, "cost_usd": cost}


def close_resolved_moderation(*, product_types=(), limit=0, dry_run=False, report=_silent):
    """Закрыть записи модерации без оставшихся причин (см. close_resolved_ai_moderation).

    Возвращает ``{"closed", "kept", "failed"}``; при dry_run ``closed`` —
    сколько будет закрыто.
    """
    generator = None if dry_run else ContentGenerator()
    closed = kept = failed = 0
    for task in _open_moderation(product_types).iterator():
        if limit and closed >= limit:
            break
        log = task.log_entry
        if get_moderation_reasons(log):
            kept += 1
            continue
        if dry_run:
            closed += 1
            report(f"закрыть: лог {log.id}, товар {log.product_id}, причина в очереди «{task.reason}»")
            continue
        try:
            generator.apply_log_to_product(log)
        except ValueError as exc:
            failed += 1
            report(f"лог {log.id}: {exc}", warning=True)
            continue
        log.refresh_from_db()
        if log.status == AIProcessingStatus.APPROVED:
            closed += 1
            report(f"закрыт: лог {log.id}, товар {log.product_id}")
        else:
            kept += 1
    return {"closed": closed, "kept": kept, "failed": failed}
