"""AI-прогоны из админки: запуск, партии, автоостановка, стоп/продолжение, защиты."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.urls import reverse

from apps.ai.models import AIModerationQueue, AIProcessingLog, AIProcessingStatus, AIRun
from apps.ai.services import ai_runs
from apps.catalog.models import Product

pytestmark = pytest.mark.django_db


def _product(index, product_type="supplements", **extra):
    return Product.objects.create(
        name=f"Run product {index}",
        slug=f"run-product-{product_type}-{index}",
        product_type=product_type,
        price=10,
        currency="TRY",
        external_id=f"run-{product_type}-{index}",
        external_data={},
        **extra,
    )


@pytest.fixture
def celery(monkeypatch):
    """Перехват постановки задач: ничего не уходит в брокер."""
    calls = SimpleNamespace(process=[], ticks=[], maintenance=[])
    monkeypatch.setattr(
        "apps.ai.tasks.process_product_ai_task.apply_async", lambda **kw: calls.process.append(kw)
    )
    monkeypatch.setattr(
        "apps.ai.tasks.advance_ai_run.apply_async", lambda args, **kw: calls.ticks.append(args)
    )
    monkeypatch.setattr(
        "apps.ai.tasks.run_ai_maintenance.apply_async", lambda args, **kw: calls.maintenance.append(args)
    )
    monkeypatch.setattr(ai_runs, "BATCH_SIZE", 2)
    return calls


@pytest.fixture
def plain_static(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_superuser("runner", "runner@example.com", "x")


def _start(user, django_capture_on_commit_callbacks, **kwargs):
    params = {"product_type": "supplements", "limit": 10, **kwargs}
    with django_capture_on_commit_callbacks(execute=True):
        return ai_runs.start_products_run(user=user, **params)


def _tick(run, django_capture_on_commit_callbacks):
    run.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        result = ai_runs.advance_run(run.pk, run.tick_token)
    run.refresh_from_db()
    return result


def _finish_batch(run, status=AIProcessingStatus.COMPLETED, cost="0.001"):
    AIProcessingLog.objects.filter(id__in=run.current_batch_log_ids).update(
        status=status, cost_usd=Decimal(cost)
    )


def test_preview_counts_unprocessed_and_estimates_cost():
    products = [_product(i) for i in range(3)]
    _product(10, product_type="medicines")
    AIProcessingLog.objects.create(
        product=products[0], processing_type="full", status=AIProcessingStatus.APPROVED, input_data={}
    )

    preview = ai_runs.preview_products_run(product_type="supplements", limit=10)

    assert preview["product_ids"] == [products[1].id, products[2].id]
    assert preview["estimate"] == Decimal("0.004")
    assert len(preview["sample"]) == 2


def test_run_enqueues_batches_counts_and_finishes(celery, user, django_capture_on_commit_callbacks):
    products = [_product(i) for i in range(3)]
    run = _start(user, django_capture_on_commit_callbacks)
    assert run.status == AIRun.Status.RUNNING
    assert run.selected_count == 3
    assert celery.ticks == [[run.pk, run.tick_token]]

    assert _tick(run, django_capture_on_commit_callbacks) == "enqueued"
    assert len(run.current_batch_log_ids) == 2
    assert run.pending_product_ids == [products[2].id]
    assert run.queued_count == 2
    assert all(call["kwargs"]["index_vectors"] is False for call in celery.process)

    # Партия ещё в работе — следующий шаг только ждёт.
    assert _tick(run, django_capture_on_commit_callbacks) == "waiting"

    _finish_batch(run)
    assert _tick(run, django_capture_on_commit_callbacks) == "enqueued"
    assert run.done_count == 2
    _finish_batch(run, status=AIProcessingStatus.MODERATION)
    assert _tick(run, django_capture_on_commit_callbacks) == "finished"

    assert run.status == AIRun.Status.FINISHED
    assert (run.done_count, run.moderation_count, run.failed_count) == (2, 1, 0)
    assert run.cost_usd == Decimal("0.003")
    assert run.logs.count() == 3


def test_run_stops_automatically_on_error_share(celery, user, django_capture_on_commit_callbacks):
    for i in range(4):
        _product(i)
    run = _start(user, django_capture_on_commit_callbacks)
    _tick(run, django_capture_on_commit_callbacks)
    _finish_batch(run, status=AIProcessingStatus.FAILED)

    assert _tick(run, django_capture_on_commit_callbacks) == "auto_stopped"
    assert run.status == AIRun.Status.STOPPED
    assert "автоматически" in run.message
    assert run.failed_count == 2
    assert len(run.pending_product_ids) == 2


def test_stop_cancels_pending_and_resume_requeues_them(celery, user, django_capture_on_commit_callbacks):
    products = [_product(i) for i in range(3)]
    run = _start(user, django_capture_on_commit_callbacks)
    _tick(run, django_capture_on_commit_callbacks)
    first, second = run.current_batch_log_ids
    AIProcessingLog.objects.filter(pk=first).update(status=AIProcessingStatus.PROCESSING)

    ai_runs.stop_run(run)
    run.refresh_from_db()

    assert run.status == AIRun.Status.STOPPED
    cancelled = AIProcessingLog.objects.get(pk=second)
    assert cancelled.status == AIProcessingStatus.FAILED
    assert cancelled.error_message.startswith(ai_runs.CANCEL_PREFIX)
    assert run.cancelled_count == 1 and run.failed_count == 0
    # Отменённый товар вернулся в начало очереди, обрабатываемый — остался в партии.
    assert run.pending_product_ids == [cancelled.product_id, products[2].id]
    assert run.current_batch_log_ids == [first]
    # Шаг со старым токеном ничего не делает.
    assert ai_runs.advance_run(run.pk, "old-token") == "skipped"
    # Следующий прогон подхватит отменённый товар.
    assert cancelled.product_id in ai_runs.preview_products_run(product_type="supplements", limit=10)[
        "product_ids"
    ]

    with django_capture_on_commit_callbacks(execute=True):
        ai_runs.resume_run(run)
    run.refresh_from_db()
    assert run.status == AIRun.Status.RUNNING
    AIProcessingLog.objects.filter(pk=first).update(status=AIProcessingStatus.COMPLETED)
    assert _tick(run, django_capture_on_commit_callbacks) == "enqueued"
    requeued = AIProcessingLog.objects.filter(product_id=cancelled.product_id).exclude(pk=second).get()
    assert requeued.status == AIProcessingStatus.PENDING
    assert requeued.id in run.current_batch_log_ids


def test_second_run_of_same_type_is_refused(celery, user, django_capture_on_commit_callbacks):
    _product(1)
    _product(2, product_type="medicines")
    _start(user, django_capture_on_commit_callbacks)

    with pytest.raises(ai_runs.RunError, match="уже идёт"):
        _start(user, django_capture_on_commit_callbacks)
    other = _start(user, django_capture_on_commit_callbacks, product_type="medicines")
    assert other.status == AIRun.Status.RUNNING


def test_cost_over_threshold_needs_confirmation(celery, user, django_capture_on_commit_callbacks, monkeypatch):
    _product(1)
    monkeypatch.setattr(ai_runs, "COST_WARNING_USD", Decimal("0.001"))

    with pytest.raises(ai_runs.RunError, match="галочку"):
        _start(user, django_capture_on_commit_callbacks)
    assert not AIRun.objects.exists()
    assert _start(user, django_capture_on_commit_callbacks, cost_confirmed=True).status == AIRun.Status.RUNNING


def test_limit_per_run_is_enforced(celery, user, django_capture_on_commit_callbacks):
    _product(1)
    with pytest.raises(ai_runs.RunError, match="не больше"):
        _start(user, django_capture_on_commit_callbacks, limit=ai_runs.MAX_PRODUCTS_PER_RUN + 1)


def test_batch_timeout_stops_run(celery, user, django_capture_on_commit_callbacks):
    _product(1)
    run = _start(user, django_capture_on_commit_callbacks)
    _tick(run, django_capture_on_commit_callbacks)
    AIRun.objects.filter(pk=run.pk).update(
        batch_started_at=run.batch_started_at - ai_runs.BATCH_TIMEOUT * 2
    )

    assert _tick(run, django_capture_on_commit_callbacks) == "timeout"
    assert run.status == AIRun.Status.STOPPED
    assert run.pending_product_ids  # отменённый товар можно продолжить


def _moderated_log(index):
    log = AIProcessingLog.objects.create(
        product=_product(index),
        processing_type="full",
        status=AIProcessingStatus.MODERATION,
        input_data={},
        generated_title=f"Title {index}",
    )
    AIModerationQueue.objects.create(log_entry=log, reason="low_confidence")
    return log


def test_close_moderation_preview_then_confirm(
    client, celery, user, plain_static, django_capture_on_commit_callbacks, monkeypatch
):
    resolved, kept = _moderated_log(1), _moderated_log(2)
    monkeypatch.setattr(
        "apps.ai.services.bulk_ops.get_moderation_reasons",
        lambda log: [] if log.pk == resolved.pk else ["low_confidence"],
    )

    def apply(log):
        AIProcessingLog.objects.filter(pk=log.pk).update(status=AIProcessingStatus.APPROVED)

    monkeypatch.setattr(
        "apps.ai.services.bulk_ops.ContentGenerator", lambda: SimpleNamespace(apply_log_to_product=apply)
    )

    with django_capture_on_commit_callbacks(execute=True):
        run = ai_runs.create_maintenance_preview(
            kind=AIRun.Kind.CLOSE_MODERATION, user=user, limit=50
        )
    assert celery.maintenance == [[run.pk, True]]
    with pytest.raises(ai_runs.RunError, match="считается"):
        ai_runs.confirm_maintenance(run)

    assert ai_runs.execute_maintenance(run.pk, True) == "previewed"
    run.refresh_from_db()
    assert run.status == AIRun.Status.DRAFT
    assert run.selected_count == 1
    assert "Будет закрыто записей: 1" in run.report["preview"]["summary"]
    resolved.refresh_from_db()
    assert resolved.status == AIProcessingStatus.MODERATION  # предпросмотр ничего не меняет
    client.force_login(user)
    page = client.get(reverse("admin:ai_airun_change", args=[run.pk])).content.decode()
    assert f"закрыть: лог {resolved.id}" in page and "Да, выполнить" in page

    with django_capture_on_commit_callbacks(execute=True):
        ai_runs.confirm_maintenance(run)
    assert ai_runs.execute_maintenance(run.pk, False) == "finished"
    run.refresh_from_db()
    resolved.refresh_from_db()
    kept.refresh_from_db()
    assert run.status == AIRun.Status.FINISHED
    assert resolved.status == AIProcessingStatus.APPROVED
    assert kept.status == AIProcessingStatus.MODERATION
    with pytest.raises(ai_runs.RunError):
        ai_runs.confirm_maintenance(run)


def test_admin_launch_page_estimate_start_and_stop(
    client, celery, user, plain_static, django_capture_on_commit_callbacks
):
    for i in range(3):
        _product(i)
    client.force_login(user)
    add_url = reverse("admin:ai_airun_add")

    assert client.get(reverse("admin:ai_airun_changelist")).status_code == 200
    page = client.get(add_url)
    assert page.status_code == 200 and "Посчитать" in page.content.decode()

    form = {"product_type": "supplements", "limit": "2"}
    estimate = client.post(add_url, {**form, "action": "estimate"})
    body = estimate.content.decode()
    assert "Войдёт товаров: <b>2</b>" in body and "Запустить" in body
    assert not AIRun.objects.exists()

    with django_capture_on_commit_callbacks(execute=True):
        started = client.post(add_url, {**form, "action": "start"})
    run = AIRun.objects.get()
    assert started.status_code == 302 and started.url == reverse("admin:ai_airun_change", args=[run.pk])
    assert run.created_by == user

    detail = client.get(started.url)
    assert detail.status_code == 200 and "Остановить" in detail.content.decode()
    status = client.get(reverse("admin:ai_airun_status", args=[run.pk])).json()
    assert status["status"] == "running" and status["selected"] == 2

    _tick(run, django_capture_on_commit_callbacks)
    client.post(reverse("admin:ai_airun_stop", args=[run.pk]))
    run.refresh_from_db()
    assert run.status == AIRun.Status.STOPPED
    assert "Продолжить" in client.get(started.url).content.decode()

    logs = client.get(reverse("admin:ai_aiprocessinglog_changelist"), {"ai_run": run.pk})
    assert logs.status_code == 200


def test_admin_maintenance_page_creates_draft(
    client, celery, user, plain_static, django_capture_on_commit_callbacks
):
    client.force_login(user)
    url = reverse("admin:ai_airun_maintenance", args=["retry_titles"])

    assert "Показать, что будет сделано" in client.get(url).content.decode()
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(url, {"limit": "20"})
    run = AIRun.objects.get()
    assert response.status_code == 302
    assert (run.kind, run.status, run.product_type, run.limit) == ("retry_titles", "draft", "supplements", 20)
    assert "Считаем" in client.get(response.url).content.decode()
    assert client.get(reverse("admin:ai_airun_maintenance", args=["unknown"])).status_code == 404
