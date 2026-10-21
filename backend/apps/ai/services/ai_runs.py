"""Оркестрация AI-прогонов из админки (AI → AI-прогоны).

Прогон товаров не работает в HTTP-запросе: кнопка «Запустить» только
создаёт ``AIRun`` и ставит короткую задачу ``advance_ai_run``. Каждый её
шаг (раз в ``TICK_SECONDS``) проверяет текущую партию, при необходимости
останавливает прогон по доле ошибок и ставит следующую партию через
``enqueue_or_apply_product_ai`` — тот же путь, что у команды ai_enqueue.

``tick_token`` защищает от двух параллельных цепочек шагов (например,
после «Продолжить»): шаг со старым токеном ничего не делает.

Перевод абзацев инструкций (Batch API) устроен так же: шаг
``advance_medicine_paragraph_run`` раз в 5 минут проверяет часть в OpenAI,
забирает готовую и отправляет следующую (services/medicine_paragraph_batch.py).
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.ai.models import AIProcessingLog, AIProcessingStatus, AIRun
from apps.ai.services import medicine_paragraph_batch as batch_api
from apps.ai.services.bulk_ops import estimate_ai_cost, select_products_for_ai
from apps.ai.services.llm_client import LLMClient
from apps.ai.services.medicine_memory import PARAGRAPH_NAMESPACE
from apps.ai.tasks import ACTIVE_AI_LOG_STATUSES

# Защиты прогона
MAX_PRODUCTS_PER_RUN = 1000
COST_WARNING_USD = Decimal("5")
MAINTENANCE_MAX_LIMIT = 500
# Партия и автоостановка
BATCH_SIZE = 20
MAX_ERROR_SHARE = 0.3
BATCH_TIMEOUT = timedelta(minutes=30)
TICK_SECONDS = 15
# Нет шагов дольше этого — фоновая цепочка, вероятно, потерялась (перезапуск).
STALLED_AFTER = timedelta(minutes=5)

CANCEL_PREFIX = "Отменено"
SAMPLE_SIZE = 10
REPORT_MAX_LINES = 300


class RunError(Exception):
    """Понятная пользователю причина, по которой действие не выполнено."""


# ---------------------------------------------------------------- прогон товаров


def preview_products_run(*, product_type, category=None, limit, missing_description=False):
    """Что сделает прогон: id товаров, оценка стоимости и примеры названий."""
    if limit > MAX_PRODUCTS_PER_RUN:
        raise RunError(f"За один запуск можно обработать не больше {MAX_PRODUCTS_PER_RUN} товаров.")
    queryset = select_products_for_ai(
        product_types=[product_type],
        category=category,
        missing_description=missing_description,
    )
    product_ids = list(queryset.values_list("id", flat=True)[:limit])
    return {
        "product_ids": product_ids,
        "count": len(product_ids),
        "total_available": queryset.count(),
        "estimate": estimate_ai_cost(product_ids),
        "sample": list(queryset.filter(id__in=product_ids[:SAMPLE_SIZE]).values_list("name", flat=True)),
    }


def running_run_exists(kind, product_type=""):
    runs = AIRun.objects.filter(kind=kind, status=AIRun.Status.RUNNING)
    if kind == AIRun.Kind.PRODUCTS:
        runs = runs.filter(product_type=product_type)
    return runs.exists()


def start_products_run(
    *, user, product_type, category=None, limit, missing_description=False, auto_apply=False,
    cost_confirmed=False,
):
    if running_run_exists(AIRun.Kind.PRODUCTS, product_type):
        raise RunError("Прогон этого типа товаров уже идёт. Дождитесь его окончания или остановите его.")
    preview = preview_products_run(
        product_type=product_type, category=category, limit=limit, missing_description=missing_description
    )
    if not preview["product_ids"]:
        raise RunError("Под эти условия не подходит ни один необработанный товар.")
    if preview["estimate"] > COST_WARNING_USD and not cost_confirmed:
        raise RunError(
            f"Оценка стоимости ≈ ${preview['estimate']:.2f} — больше ${COST_WARNING_USD}. "
            "Поставьте галочку подтверждения стоимости и нажмите «Запустить» ещё раз."
        )
    now = timezone.now()
    try:
        with transaction.atomic():
            run = AIRun.objects.create(
                kind=AIRun.Kind.PRODUCTS,
                status=AIRun.Status.RUNNING,
                created_by=user,
                product_type=product_type,
                category=category,
                limit=limit,
                missing_description=missing_description,
                auto_apply=auto_apply,
                pending_product_ids=preview["product_ids"],
                selected_count=preview["count"],
                estimated_cost_usd=preview["estimate"],
                tick_token=str(uuid.uuid4()),
                started_at=now,
                heartbeat_at=now,
            )
            _schedule_tick(run, countdown=0)
    except IntegrityError:
        raise RunError("Прогон этого типа товаров уже идёт. Дождитесь его окончания или остановите его.")
    return run


def is_stalled(run):
    stalled_after = PARAGRAPH_STALLED_AFTER if run.kind == AIRun.Kind.MEDICINE_PARAGRAPHS else STALLED_AFTER
    return (
        run.status == AIRun.Status.RUNNING
        and run.heartbeat_at is not None
        and timezone.now() - run.heartbeat_at > stalled_after
    )


def stop_run(run, reason="Остановлен вручную. Чтобы обработать оставшиеся товары, нажмите «Продолжить»."):
    """Остановить прогон товаров; ожидающие задачи партии отменяются.

    Отменённые логи получают статус «Ошибка» с текстом «Отменено…» — воркер
    такие задачи пропускает, а товары возвращаются в начало очереди прогона
    (для «Продолжить») и попадают в выборку следующих прогонов.
    """
    with transaction.atomic():
        run = AIRun.objects.select_for_update().get(pk=run.pk)
        if run.status != AIRun.Status.RUNNING:
            raise RunError("Прогон уже не идёт.")
        _stop(run, reason)
    return run


def resume_run(run):
    """Продолжить остановленный, упавший или зависший прогон с того же места."""
    if run.kind == AIRun.Kind.MEDICINE_PARAGRAPHS:
        return _resume_paragraphs(run)
    with transaction.atomic():
        run = AIRun.objects.select_for_update().get(pk=run.pk)
        if run.kind != AIRun.Kind.PRODUCTS:
            raise RunError("Эту операцию нельзя продолжить — запустите её заново.")
        if run.status == AIRun.Status.RUNNING and not is_stalled(run):
            raise RunError("Прогон и так идёт.")
        if run.status not in (AIRun.Status.STOPPED, AIRun.Status.FAILED, AIRun.Status.RUNNING):
            raise RunError("Продолжить можно только остановленный прогон.")
        if not run.pending_product_ids and not run.current_batch_log_ids:
            raise RunError("В этом прогоне не осталось товаров.")
        now = timezone.now()
        run.status = AIRun.Status.RUNNING
        run.tick_token = str(uuid.uuid4())
        run.heartbeat_at = now
        run.batch_started_at = now if run.current_batch_log_ids else None
        run.finished_at = None
        run.message = ""
        try:
            with transaction.atomic():
                run.save()
        except IntegrityError:
            raise RunError("Сейчас идёт другой прогон этого типа товаров. Дождитесь его окончания.")
        _schedule_tick(run, countdown=0)
    return run


def advance_run(run_id, token):
    """Один шаг прогона. Вызывается задачей ``advance_ai_run``."""
    with transaction.atomic():
        run = AIRun.objects.select_for_update().filter(pk=run_id).first()
        if run is None or run.status != AIRun.Status.RUNNING or run.tick_token != token:
            return "skipped"
        run.heartbeat_at = timezone.now()

        batch = list(run.current_batch_log_ids)
        if batch:
            batch_logs = AIProcessingLog.objects.filter(id__in=batch)
            if batch_logs.filter(status__in=ACTIVE_AI_LOG_STATUSES).exists():
                if run.batch_started_at and timezone.now() - run.batch_started_at > BATCH_TIMEOUT:
                    _stop(
                        run,
                        "Партия товаров не обработалась за 30 минут. Вероятно, не работает "
                        "AI-обработчик (celery_ai). Проверьте его и нажмите «Продолжить».",
                    )
                    return "timeout"
                refresh_counters(run)
                run.save()
                _schedule_tick(run)
                return "waiting"
            failed = batch_logs.filter(status=AIProcessingStatus.FAILED).exclude(
                error_message__startswith=CANCEL_PREFIX
            ).count()
            if failed and failed / len(batch) > MAX_ERROR_SHARE:
                _stop(
                    run,
                    f"Остановлен автоматически: в последней партии ошибок {failed} из {len(batch)}. "
                    "Откройте логи прогона и посмотрите текст ошибки. Когда причина устранена, "
                    "нажмите «Продолжить».",
                )
                return "auto_stopped"
            run.current_batch_log_ids = []

        if not run.pending_product_ids:
            _finish(run)
            return "finished"

        _enqueue_next_batch(run)
        refresh_counters(run)
        run.save()
        # Если вся партия оказалась пропущенной, следующий шаг — сразу.
        _schedule_tick(run, countdown=None if run.current_batch_log_ids else 1)
        return "enqueued"


def fail_run(run_id, exc):
    run = AIRun.objects.filter(pk=run_id).only("kind", "status").first()
    hint = (
        "Можно нажать «Продолжить»."
        if run is not None and (
            run.kind == AIRun.Kind.PRODUCTS
            or (run.kind == AIRun.Kind.MEDICINE_PARAGRAPHS and run.status == AIRun.Status.RUNNING)
        )
        else "Можно запустить операцию заново."
    )
    AIRun.objects.filter(pk=run_id, status__in=[AIRun.Status.RUNNING, AIRun.Status.DRAFT]).update(
        status=AIRun.Status.FAILED,
        message=f"Сбой фоновой задачи: {exc}. {hint}",
        finished_at=timezone.now(),
    )


def refresh_counters(run, save=False):
    """Пересчитать счётчики и фактическую стоимость по логам прогона."""
    if run.kind != AIRun.Kind.PRODUCTS or run.pk is None:
        return run
    cancelled = Q(status=AIProcessingStatus.FAILED, error_message__startswith=CANCEL_PREFIX)
    stats = run.logs.aggregate(
        queued=Count("id"),
        done=Count("id", filter=Q(status__in=[AIProcessingStatus.COMPLETED, AIProcessingStatus.APPROVED])),
        moderation=Count("id", filter=Q(status=AIProcessingStatus.MODERATION)),
        failed=Count("id", filter=Q(status=AIProcessingStatus.FAILED) & ~cancelled),
        cancelled=Count("id", filter=cancelled),
        cost=Sum("cost_usd"),
    )
    run.queued_count = stats["queued"]
    run.done_count = stats["done"]
    run.moderation_count = stats["moderation"]
    run.failed_count = stats["failed"]
    run.cancelled_count = stats["cancelled"]
    run.cost_usd = stats["cost"] or Decimal("0")
    if save:
        AIRun.objects.filter(pk=run.pk).update(
            queued_count=run.queued_count,
            done_count=run.done_count,
            moderation_count=run.moderation_count,
            failed_count=run.failed_count,
            cancelled_count=run.cancelled_count,
            cost_usd=run.cost_usd,
        )
    return run


def in_progress_count(run):
    if run.kind != AIRun.Kind.PRODUCTS or run.pk is None:
        return 0
    return run.logs.filter(status__in=ACTIVE_AI_LOG_STATUSES).count()


def _enqueue_next_batch(run):
    from apps.ai.tasks import enqueue_or_apply_product_ai
    from apps.catalog.models import Product

    batch, rest = run.pending_product_ids[:BATCH_SIZE], run.pending_product_ids[BATCH_SIZE:]
    queued_logs = []
    for product_id in batch:
        try:
            log, action = enqueue_or_apply_product_ai(
                product_id=product_id,
                auto_apply=run.auto_apply,
                index_vectors=False,
            )
        except Product.DoesNotExist:
            run.skipped_count += 1
            continue
        if action == "queued":
            queued_logs.append(log)
        else:
            # Товар уже обработан или стоит в очереди с другого запуска.
            run.skipped_count += 1
    run.logs.add(*queued_logs)
    run.pending_product_ids = rest
    run.current_batch_log_ids = [log.id for log in queued_logs]
    run.batch_started_at = timezone.now() if queued_logs else None


def _stop(run, reason):
    pending = AIProcessingLog.objects.filter(
        id__in=run.current_batch_log_ids, status=AIProcessingStatus.PENDING
    )
    cancelled = list(pending.values_list("id", "product_id"))
    pending.update(
        status=AIProcessingStatus.FAILED,
        error_message=f"{CANCEL_PREFIX}: прогон #{run.pk} остановлен до начала обработки",
        completed_at=timezone.now(),
    )
    cancelled_ids = {log_id for log_id, _ in cancelled}
    run.pending_product_ids = [product_id for _, product_id in cancelled] + list(run.pending_product_ids)
    # Обрабатываемые сейчас задачи доработают; отменённые не считаются ошибками партии.
    run.current_batch_log_ids = [i for i in run.current_batch_log_ids if i not in cancelled_ids]
    run.status = AIRun.Status.STOPPED
    run.message = reason
    run.finished_at = timezone.now()
    run.tick_token = ""
    refresh_counters(run)
    run.save()


def _finish(run):
    run.status = AIRun.Status.FINISHED
    run.finished_at = timezone.now()
    run.tick_token = ""
    refresh_counters(run)
    run.message = (
        f"Готово: обработано {run.done_count}, на модерации {run.moderation_count}, "
        f"ошибок {run.failed_count}, пропущено {run.skipped_count}."
    )
    run.save()
    if run.auto_apply:
        # Прогон ставит задачи без переиндексации рекомендаций; без аргументов
        # задача сама выберет товары, изменённые после последней индексации.
        from apps.recommendations.tasks import index_product_vectors

        transaction.on_commit(lambda: index_product_vectors.delay())


def _schedule_tick(run, countdown=None):
    from apps.ai.tasks import advance_ai_run

    run_id, token = run.pk, run.tick_token
    delay = TICK_SECONDS if countdown is None else countdown
    # priority=0 — раньше обычных AI-задач (priority=9) в той же очереди.
    # robust: если брокер недоступен, прогон не падает, а через STALLED_AFTER
    # показывается как зависший с кнопкой «Продолжить».
    transaction.on_commit(
        lambda: advance_ai_run.apply_async(args=[run_id, token], countdown=delay, priority=0),
        robust=True,
    )


# --------------------------------------------------------- обслуживающие операции


MAINTENANCE_KINDS = (AIRun.Kind.RETRY_TITLES, AIRun.Kind.CLOSE_MODERATION)


def create_maintenance_preview(*, kind, user, product_type="", limit):
    """Черновик операции: фоновая задача посчитает, что будет сделано."""
    if kind not in MAINTENANCE_KINDS:
        raise RunError("Неизвестная операция.")
    if not 1 <= limit <= MAINTENANCE_MAX_LIMIT:
        raise RunError(f"Лимит — от 1 до {MAINTENANCE_MAX_LIMIT}.")
    if kind == AIRun.Kind.RETRY_TITLES:
        product_type = "supplements"
    run = AIRun.objects.create(
        kind=kind, status=AIRun.Status.DRAFT, created_by=user, product_type=product_type, limit=limit
    )
    from apps.ai.tasks import run_ai_maintenance

    transaction.on_commit(
        lambda: run_ai_maintenance.apply_async(args=[run.pk, True], priority=0), robust=True
    )
    return run


def confirm_maintenance(run):
    with transaction.atomic():
        run = AIRun.objects.select_for_update().get(pk=run.pk)
        if run.kind not in MAINTENANCE_KINDS or run.status != AIRun.Status.DRAFT:
            raise RunError("Эта операция уже запускалась.")
        if not run.report.get("preview"):
            raise RunError("Предпросмотр ещё считается — подождите несколько секунд.")
        if running_run_exists(run.kind):
            raise RunError("Такая операция уже выполняется. Дождитесь её окончания.")
        run.status = AIRun.Status.RUNNING
        run.started_at = timezone.now()
        try:
            with transaction.atomic():
                run.save()
        except IntegrityError:
            raise RunError("Такая операция уже выполняется. Дождитесь её окончания.")
        from apps.ai.tasks import run_ai_maintenance

        run_id = run.pk
        transaction.on_commit(
            lambda: run_ai_maintenance.apply_async(args=[run_id, False], priority=0), robust=True
        )
    return run


def execute_maintenance(run_id, dry_run):
    """Предпросмотр (dry_run) или выполнение операции; пишет итог в отчёт прогона."""
    from apps.ai.services.bulk_ops import close_resolved_moderation, retry_supplement_titles

    run = AIRun.objects.get(pk=run_id)
    expected = AIRun.Status.DRAFT if dry_run else AIRun.Status.RUNNING
    if run.status != expected:
        return "skipped"
    lines = []

    def report(message, warning=False):
        if len(lines) < REPORT_MAX_LINES:
            lines.append(("⚠ " if warning else "") + message)

    if run.kind == AIRun.Kind.RETRY_TITLES:
        result = retry_supplement_titles(limit=run.limit, dry_run=dry_run, report=report)
        summary = (
            f"Будет перегенерировано названий: {result['selected']}. Оценка ≈ ${result['cost_usd']:.4f}."
            if dry_run
            else f"Исправлено названий: {result['fixed']}, не удалось: {result['failed']}. "
            f"Потрачено ${result['cost_usd']:.4f}. Дальше нажмите «Закрыть решённые записи модерации», "
            "чтобы применить новые названия к товарам."
        )
        count = result["selected"]
    else:
        result = close_resolved_moderation(
            product_types=[run.product_type] if run.product_type else [],
            limit=run.limit,
            dry_run=dry_run,
            report=report,
        )
        summary = (
            f"Будет закрыто записей: {result['closed']}. Останутся на модерации (есть причины): {result['kept']}."
            if dry_run
            else f"Закрыто записей: {result['closed']}, осталось на модерации: {result['kept']}, "
            f"ошибок: {result['failed']}."
        )
        count = result["closed"]

    run.report = {**run.report, ("preview" if dry_run else "result"): {"summary": summary, "lines": lines}}
    if dry_run:
        run.selected_count = count
        run.estimated_cost_usd = result.get("cost_usd", Decimal("0"))
        run.save(update_fields=["report", "selected_count", "estimated_cost_usd", "updated_at"])
        return "previewed"
    run.status = AIRun.Status.FINISHED
    run.finished_at = timezone.now()
    run.message = summary
    run.done_count = result.get("fixed", result.get("closed", 0))
    run.failed_count = result["failed"]
    run.cost_usd = result.get("cost_usd", Decimal("0"))
    run.save()
    return "finished"


# ------------------------------------------ перевод абзацев инструкций (Batch API)


# Часть готовится в OpenAI от минут до 24 ч — её состояние проверяется раз в 5 минут.
PARAGRAPH_TICK_SECONDS = 300
PARAGRAPH_STALLED_AFTER = timedelta(minutes=20)
PARAGRAPH_MIN_PART = 10
PARAGRAPH_MAX_PART = 20000
# Часть в этих состояниях больше не ждёт OpenAI.
PART_DONE_STATES = ("collected", "failed")
PART_STATES = {
    "validating": "OpenAI проверяет файл",
    "in_progress": "переводится в OpenAI",
    "finalizing": "OpenAI собирает ответ",
    "cancelling": "отменяется в OpenAI",
    "completed": "готова, забираем",
    "collected": "забрана",
    "failed": "не выполнена",
    "expired": "не успела за 24 ч",
    "cancelled": "отменена в OpenAI",
}
REASON_LABELS = {
    "shifted": "сдвиг ответа",
    "missing": "нет перевода",
    "fact_mismatch": "дозировки",
    "number_mismatch": "числа",
    "heading_mismatch": "номер заголовка",
    "length_mismatch": "длина",
    "ru_en_mismatch": "RU и EN расходятся",
    "concept_mismatch": "смысл",
    "frequency_mismatch": "частота побочного действия",
    "ru_not_russian": "RU не по-русски",
    "en_has_cyrillic": "кириллица в EN",
    "too_short": "слишком коротко",
    "brand_token_missing": "потеряна метка {BRAND}",
}


def create_paragraph_preview(*, user, part_size, max_defect, wait_each_part):
    """Черновик прогона: фоновая задача посчитает абзацы, части и цену (dry-run)."""
    if not PARAGRAPH_MIN_PART <= part_size <= PARAGRAPH_MAX_PART:
        raise RunError(f"Размер части — от {PARAGRAPH_MIN_PART} до {PARAGRAPH_MAX_PART} абзацев.")
    if not 0 < max_defect <= 1:
        raise RunError("Порог брака — от 1 до 100 %.")
    run = AIRun.objects.create(
        kind=AIRun.Kind.MEDICINE_PARAGRAPHS,
        status=AIRun.Status.DRAFT,
        created_by=user,
        report={
            "settings": {"part_size": part_size, "max_defect": max_defect, "wait_each_part": wait_each_part},
            "parts": [],
        },
    )
    from apps.ai.tasks import preview_medicine_paragraph_run

    transaction.on_commit(
        lambda: preview_medicine_paragraph_run.apply_async(args=[run.pk], priority=0), robust=True
    )
    return run


def preview_paragraph_run(run_id):
    """Dry-run: сколько абзацев не в памяти, сколько частей и запросов, оценка цены."""
    run = AIRun.objects.get(pk=run_id)
    if run.status != AIRun.Status.DRAFT:
        return "skipped"
    part_size = run.report["settings"]["part_size"]
    totals = {"parts": 0, "paragraphs": 0, "chars": 0, "requests": 0, "cost_usd": 0.0, "regular_cost_usd": 0.0}
    for paragraphs, _ in batch_api.iter_parts(0, part_size):
        totals["parts"] += 1
        for key, value in batch_api.estimate(paragraphs).items():
            totals[key] += value
    if totals["paragraphs"]:
        summary = (
            f"Не в памяти переводов {_num(totals['paragraphs'])} абзацев ({_num(totals['chars'])} симв.): "
            f"{totals['parts']} частей по ≈ {_num(part_size)} абзацев, {_num(totals['requests'])} запросов. "
            f"Оценка ≈ ${totals['cost_usd']:.2f} в Batch API (обычной обработкой ≈ "
            f"${totals['regular_cost_usd']:.2f}). Каждая часть готовится в OpenAI до 24 часов."
        )
    else:
        summary = "Все абзацы инструкций уже в памяти переводов — переводить нечего."
    AIRun.objects.filter(pk=run.pk, status=AIRun.Status.DRAFT).update(
        report={**run.report, "preview": {**totals, "summary": summary}},
        selected_count=totals["paragraphs"],
        estimated_cost_usd=Decimal(str(round(totals["cost_usd"], 4))),
        updated_at=timezone.now(),
    )
    return "previewed"


def start_paragraph_run(run):
    """«Запустить»: первая часть уйдёт в OpenAI в первом же шаге."""
    with transaction.atomic():
        run = _lock(run)
        if run.kind != AIRun.Kind.MEDICINE_PARAGRAPHS or run.status != AIRun.Status.DRAFT:
            raise RunError("Этот прогон уже запускался.")
        if not run.report.get("preview"):
            raise RunError("Оценка ещё считается — подождите и обновите страницу.")
        if not run.selected_count:
            raise RunError("Переводить нечего: все абзацы уже в памяти переводов.")
        _run_paragraphs(run)
    return run


def stop_paragraph_run(run):
    """«Стоп»: новые части не отправляются; часть, уже отправленную в OpenAI, заберём и остановимся."""
    with transaction.atomic():
        run = _lock(run)
        if run.status != AIRun.Status.RUNNING:
            raise RunError("Прогон уже не идёт.")
        part = part_in_flight(run)
        if part is None:
            _stop_paragraphs(run, "Остановлен вручную. Чтобы идти дальше с того же места, нажмите «Следующая часть».")
        elif run.report.get("stop_requested"):
            raise RunError("Остановка уже запрошена — ждём, когда OpenAI закончит текущую часть.")
        else:
            run.report["stop_requested"] = True
            run.message = (
                f"Остановка: новые части отправляться не будут. Часть №{part['number']} уже в OpenAI — "
                "её заберём, как только она будет готова (до 24 часов), и прогон остановится."
            )
            run.save(update_fields=["report", "message", "updated_at"])
    return run


def next_paragraph_part(run):
    """«Следующая часть»: продолжить остановленный прогон, даже если брак был выше порога."""
    with transaction.atomic():
        run = _lock(run)
        if not paragraph_state(run)["can_next"]:
            raise RunError("Следующую часть можно отправить, когда прогон остановлен и прошлая часть забрана.")
        _run_paragraphs(run, "next")
    return run


def retry_paragraph_part(run):
    """«Повторить отклонённые»: заново отправить абзацы последней части, которых нет в памяти."""
    with transaction.atomic():
        run = _lock(run)
        if not paragraph_state(run)["can_retry"]:
            raise RunError("Повторять нечего: у последней забранной части нет отклонённых абзацев.")
        _run_paragraphs(run, "retry")
    return run


def _resume_paragraphs(run):
    with transaction.atomic():
        run = _lock(run)
        if not paragraph_state(run)["can_resume"]:
            raise RunError("Прогон и так идёт." if run.status == AIRun.Status.RUNNING else "Продолжать нечего.")
        _run_paragraphs(run)
    return run


def part_in_flight(run):
    """Последняя часть, если OpenAI её ещё не вернул или она не забрана."""
    parts = (run.report or {}).get("parts") or []
    if parts and parts[-1]["state"] not in PART_DONE_STATES:
        return parts[-1]
    return None


def paragraph_state(run):
    """Кнопки и сводка прогона абзацев для страницы и автообновления."""
    parts = run.report.get("parts") or []
    in_flight = part_in_flight(run)
    retry = _retry_source(run)
    stopped = run.status == AIRun.Status.STOPPED
    covered = sum(p["paragraphs"] for p in parts if not p.get("retry_of") and p["state"] != "failed")
    collected = sum(p["paragraphs"] for p in parts if p["state"] == "collected")
    return {
        "in_flight": in_flight is not None,
        "stop_requested": bool(run.report.get("stop_requested")),
        "can_stop": run.status == AIRun.Status.RUNNING and not run.report.get("stop_requested"),
        "can_resume": run.started_at is not None and (
            is_stalled(run) or run.status == AIRun.Status.FAILED or (stopped and in_flight is not None)
        ),
        "can_next": stopped and in_flight is None,
        "can_retry": run.status in (AIRun.Status.STOPPED, AIRun.Status.FINISHED)
        and in_flight is None and retry is not None,
        "retry_part": retry["number"] if retry else None,
        "retry_count": retry["defect_count"] if retry else 0,
        "covered": covered,
        "percent": min(100, round(covered * 100 / run.selected_count)) if run.selected_count else 0,
        "per_1000": f"{float(run.cost_usd) / collected * 1000:.4f}" if collected else "",
        "parts_key": "|".join(f"{p['number']}:{p['state']}:{p.get('requests_done', 0)}" for p in parts),
    }


def advance_paragraph_run(run_id, token):
    """Один шаг прогона абзацев. Вызывается задачей ``advance_medicine_paragraph_run``.

    Строка прогона заблокирована на весь шаг (кнопки в это время отвечают
    «повторите через минуту»), поэтому сбор части пишет память одной
    транзакцией: при сбое шаг повторится целиком, записанное не задвоится.
    """
    with transaction.atomic():
        run = AIRun.objects.select_for_update().filter(pk=run_id).first()
        if run is None or run.status != AIRun.Status.RUNNING or run.tick_token != token:
            return "skipped"
        run.heartbeat_at = timezone.now()
        client = LLMClient()
        part = part_in_flight(run)
        if part is not None:
            batch = client.client.batches.retrieve(part["batch_id"])
            counts = getattr(batch, "request_counts", None)
            part["state"] = batch.status
            part["requests_done"] = getattr(counts, "completed", 0) or 0
            part["requests_failed"] = getattr(counts, "failed", 0) or 0
            if batch.status in batch_api.RUNNING_STATUSES:
                run.save()
                _schedule_paragraph_tick(run)
                return "waiting"
            if not batch.output_file_id:
                part["state"] = "failed"
                _stop_paragraphs(run, _failed_part_message(part, batch))
                return "part_failed"
            try:
                stats = batch_api.collect_part(client, batch)
            except batch_api.PartError as exc:
                _stop_paragraphs(
                    run,
                    f"Готовую часть №{part['number']} не удалось забрать: {exc}. "
                    "Когда причина устранена, нажмите «Продолжить».",
                )
                return "collect_failed"
            _record_part(run, part, batch, stats)
            reason = _pause_reason(run, part)
            if reason:
                _stop_paragraphs(run, reason)
                return "stopped"
        return _send_part(run, client)


def _send_part(run, client):
    """Отправить следующую часть каталога или повтор отклонённых абзацев последней части."""
    action = run.report.pop("next_action", "next")
    running = batch_api.running_parts(client)
    if running:
        _stop_paragraphs(
            run,
            f"В OpenAI ещё идёт часть, отправленная не этим прогоном: "
            f"{', '.join(batch_api.describe(batch) for batch in running)}. Чтобы абзацы не оплатились "
            "дважды, дождитесь её и заберите (консоль: medicine_paragraph_batch collect), потом нажмите "
            "кнопку ещё раз.",
        )
        return "busy"
    retry_of = None
    if action == "retry":
        retry_of = _retry_source(run)
        if retry_of is None:
            _stop_paragraphs(run, "Повторять нечего: у последней забранной части нет отклонённых абзацев.")
            return "nothing_to_retry"
        try:
            paragraphs, _ = batch_api.rejected_paragraphs(client, client.client.batches.retrieve(retry_of["batch_id"]))
        except batch_api.PartError as exc:
            _stop_paragraphs(run, f"Не удалось подготовить повтор: {exc}.")
            return "retry_failed"
        last_product = retry_of["last_product"]
        if not paragraphs:
            _stop_paragraphs(
                run,
                f"Отклонённые абзацы части №{retry_of['number']} уже в памяти (переведены при обработке "
                "лекарств) — повторять нечего. Нажмите «Следующая часть».",
            )
            return "nothing_to_retry"
    else:
        found = next(batch_api.iter_parts(_cursor(run), run.report["settings"]["part_size"]), None)
        if found is None:
            _finish_paragraphs(run)
            return "finished"
        paragraphs, last_product = found
    number = len(run.report["parts"]) + 1
    cost = batch_api.estimate(paragraphs)
    batch = batch_api.submit_part(client, paragraphs, metadata={
        "kind": PARAGRAPH_NAMESPACE,
        "part": str(number),
        "paragraphs": str(len(paragraphs)),
        "last_product": "" if retry_of else str(last_product),
        "retry_of": retry_of["batch_id"] if retry_of else "",
        "run": str(run.pk),
    })
    run.report["parts"].append({
        "number": number,
        "batch_id": batch.id,
        "retry_of": retry_of["number"] if retry_of else None,
        "paragraphs": len(paragraphs),
        "last_product": last_product,
        "requests": cost["requests"],
        "estimate_usd": round(cost["cost_usd"], 4),
        "state": batch.status,
        "sent_at": timezone.now().isoformat(),
    })
    _refresh_paragraph_counters(run)
    run.message = ""
    run.save()
    _schedule_paragraph_tick(run)
    return "submitted"


def _record_part(run, part, batch, stats):
    summary = batch_api.part_summary(stats, part["paragraphs"])
    part.update({
        "state": "collected",
        "openai_status": batch.status,
        "accepted": summary["accepted"],
        "rejected": summary["rejected"],
        "no_answer": summary["no_answer"],
        "defect_count": summary["defect_count"],
        "defect": round(summary["defect"], 4),
        "shifted_requests": summary["shifted_requests"],
        "reasons": summary["reasons"],
        "cost_usd": round(summary["cost_usd"], 6),
        "per_1000": round(summary["per_1000"], 4),
        "collected_at": timezone.now().isoformat(),
    })
    _refresh_paragraph_counters(run)


def _pause_reason(run, part):
    """Почему не отправлять следующую часть сразу; None — можно дальше."""
    settings = run.report["settings"]
    line = (
        f"Часть №{part['number']}: принято {_num(part['accepted'])} из {_num(part['paragraphs'])} абзацев, "
        f"брак {_num(part['defect_count'])} ({part['defect']:.1%}, порог {settings['max_defect']:.0%}), "
        f"сдвиг в {part['shifted_requests']} запросах, потрачено ${part['cost_usd']:.4f}."
    )
    if part["openai_status"] != "completed":
        return (
            f"{line} OpenAI не выполнил часть целиком ({PART_STATES.get(part['openai_status'], part['openai_status'])}) "
            "— забрано то, что готово. «Повторить отклонённые» отправит остальные абзацы этой части, "
            "«Следующая часть» — пойдёт дальше без них."
        )
    if part["defect"] > settings["max_defect"]:
        return (
            f"Остановлен автоматически: брак выше порога. {line} Причины: {reason_text(part['reasons'])}. "
            "«Повторить отклонённые» отправит заново только отклонённые абзацы этой части; если брак снова "
            "высокий — сообщите разработчику. «Следующая часть» — идти дальше без повтора."
        )
    if run.report.pop("stop_requested", False):
        return f"Остановлен вручную. {line} Чтобы идти дальше, нажмите «Следующая часть»."
    if settings["wait_each_part"]:
        return f"{line} Проверьте переводы в «Памяти переводов» и нажмите «Следующая часть»."
    return None


def reason_text(reasons):
    """{"shifted": 10, …} → «сдвиг ответа 10, числа 3» (у абзаца бывает несколько причин)."""
    return ", ".join(f"{REASON_LABELS.get(code, code)} {count}" for code, count in reasons.items()) or "—"


def _failed_part_message(part, batch):
    errors = getattr(getattr(batch, "errors", None), "data", None) or []
    detail = f" Ответ OpenAI: {getattr(errors[0], 'message', errors[0])}." if errors else ""
    return (
        f"OpenAI не вернул ни одного перевода части №{part['number']} "
        f"({PART_STATES.get(batch.status, batch.status)}).{detail} Абзацы этой части не в памяти: "
        "«Следующая часть» отправит их заново. Если повторится — сообщите разработчику."
    )


def _retry_source(run):
    """Последняя забранная часть, если у неё есть отклонённые абзацы."""
    collected = [p for p in run.report.get("parts") or [] if p["state"] == "collected"]
    if collected and collected[-1]["defect_count"]:
        return collected[-1]
    return None


def _cursor(run):
    """Лекарство, после которого начинается следующая часть: конец последней забранной части."""
    for part in reversed(run.report.get("parts") or []):
        if not part.get("retry_of") and part["state"] == "collected":
            return part["last_product"]
    return 0


def _refresh_paragraph_counters(run):
    """Отправлено, принято, брак (без принятых повтором) и потрачено — по частям прогона."""
    parts = run.report.get("parts") or []
    collected = [p for p in parts if p["state"] == "collected"]
    run.queued_count = sum(p["paragraphs"] for p in parts if p["state"] != "failed")
    run.done_count = sum(p["accepted"] for p in collected)
    run.failed_count = max(
        0,
        sum(p["defect_count"] for p in collected if not p.get("retry_of"))
        - sum(p["accepted"] for p in collected if p.get("retry_of")),
    )
    run.cost_usd = Decimal(str(round(sum(p["cost_usd"] for p in collected), 6)))


def _run_paragraphs(run, action=None):
    """Перевести прогон в «Идёт» и запустить цепочку шагов (строка уже заблокирована)."""
    now = timezone.now()
    run.status = AIRun.Status.RUNNING
    run.started_at = run.started_at or now
    run.tick_token = str(uuid.uuid4())
    run.heartbeat_at = now
    run.finished_at = None
    run.message = ""
    run.report.pop("stop_requested", None)
    if action:
        run.report["next_action"] = action
    try:
        with transaction.atomic():
            run.save()
    except IntegrityError:
        raise RunError("Уже идёт другой перевод абзацев. Дождитесь его окончания или остановите его.")
    _schedule_paragraph_tick(run, countdown=0)


def _stop_paragraphs(run, reason):
    run.status = AIRun.Status.STOPPED
    run.message = reason
    run.finished_at = timezone.now()
    run.tick_token = ""
    run.report.pop("stop_requested", None)
    _refresh_paragraph_counters(run)
    run.save()


def _finish_paragraphs(run):
    run.status = AIRun.Status.FINISHED
    run.finished_at = timezone.now()
    run.tick_token = ""
    run.message = (
        f"Проход по каталогу закончен: частей {len(run.report['parts'])}, принято в память "
        f"{_num(run.done_count)} абзацев, не попали в память {_num(run.failed_count)}, потрачено "
        f"${run.cost_usd:.4f}. Не попавшие в память абзацы переведутся при обработке лекарств; "
        "или запустите перевод абзацев ещё раз — он возьмёт только их."
    )
    run.save()


def _lock(run):
    try:
        return AIRun.objects.select_for_update(nowait=True).get(pk=run.pk)
    except DatabaseError:
        raise RunError("Сейчас идёт шаг прогона (например, забираем готовую часть) — повторите через минуту.")


def _schedule_paragraph_tick(run, countdown=None):
    from apps.ai.tasks import advance_medicine_paragraph_run

    run_id, token = run.pk, run.tick_token
    delay = PARAGRAPH_TICK_SECONDS if countdown is None else countdown
    transaction.on_commit(
        lambda: advance_medicine_paragraph_run.apply_async(args=[run_id, token], countdown=delay, priority=0),
        robust=True,
    )


def _num(value):
    """12345 → «12 345»."""
    return f"{value:,}".replace(",", " ")
