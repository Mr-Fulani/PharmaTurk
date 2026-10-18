"""Оркестрация AI-прогонов из админки (AI → AI-прогоны).

Прогон товаров не работает в HTTP-запросе: кнопка «Запустить» только
создаёт ``AIRun`` и ставит короткую задачу ``advance_ai_run``. Каждый её
шаг (раз в ``TICK_SECONDS``) проверяет текущую партию, при необходимости
останавливает прогон по доле ошибок и ставит следующую партию через
``enqueue_or_apply_product_ai`` — тот же путь, что у команды ai_enqueue.

``tick_token`` защищает от двух параллельных цепочек шагов (например,
после «Продолжить»): шаг со старым токеном ничего не делает.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.ai.models import AIProcessingLog, AIProcessingStatus, AIRun
from apps.ai.services.bulk_ops import estimate_ai_cost, select_products_for_ai
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
    return (
        run.status == AIRun.Status.RUNNING
        and run.heartbeat_at is not None
        and timezone.now() - run.heartbeat_at > STALLED_AFTER
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
    run = AIRun.objects.filter(pk=run_id).only("kind").first()
    hint = (
        "Можно нажать «Продолжить»."
        if run is not None and run.kind == AIRun.Kind.PRODUCTS
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
