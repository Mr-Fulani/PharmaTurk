from datetime import timedelta

import httpx
import openai
import pytest
from celery.exceptions import Retry
from django.utils import timezone

from apps.ai.models import AIProcessingLog, AIProcessingStatus
from apps.ai.tasks import enqueue_product_ai_task, process_product_ai_task
from apps.catalog.models import Product


@pytest.fixture
def product():
    return Product.objects.create(
        name="Queued AI product",
        slug="queued-ai-product",
        product_type="accessories",
        price=10,
        currency="TRY",
        external_id="queued-ai-product-1",
        external_data={},
    )


@pytest.mark.django_db
def test_enqueue_creates_visible_pending_log_before_worker_starts(
    monkeypatch, product, django_capture_on_commit_callbacks
):
    submitted = []
    monkeypatch.setattr(
        "apps.ai.tasks.process_product_ai_task.apply_async",
        lambda **kwargs: submitted.append(kwargs),
    )

    with django_capture_on_commit_callbacks(execute=True):
        log, task_id, was_submitted = enqueue_product_ai_task(product_id=product.id)

    log.refresh_from_db()
    assert was_submitted is True
    assert log.status == AIProcessingStatus.PENDING
    assert log.input_data["celery_task_id"] == task_id
    assert submitted[0]["task_id"] == task_id
    assert submitted[0]["kwargs"]["log_entry_id"] == log.id


@pytest.mark.django_db
def test_enqueue_is_idempotent_while_product_is_pending(
    monkeypatch, product, django_capture_on_commit_callbacks
):
    submitted = []
    monkeypatch.setattr(
        "apps.ai.tasks.process_product_ai_task.apply_async",
        lambda **kwargs: submitted.append(kwargs),
    )

    with django_capture_on_commit_callbacks(execute=True):
        first, first_task_id, first_submitted = enqueue_product_ai_task(product_id=product.id)
        second, second_task_id, second_submitted = enqueue_product_ai_task(product_id=product.id)

    assert first_submitted is True
    assert second_submitted is False
    assert second.id == first.id
    assert second_task_id == first_task_id
    assert AIProcessingLog.objects.filter(product=product).count() == 1
    assert len(submitted) == 1


@pytest.mark.django_db
def test_forced_rerun_does_not_duplicate_an_active_task(
    monkeypatch, product, django_capture_on_commit_callbacks
):
    submitted = []
    monkeypatch.setattr(
        "apps.ai.tasks.process_product_ai_task.apply_async",
        lambda **kwargs: submitted.append(kwargs),
    )

    with django_capture_on_commit_callbacks(execute=True):
        first, first_task_id, first_submitted = enqueue_product_ai_task(
            product_id=product.id,
            force=True,
        )
        second, second_task_id, second_submitted = enqueue_product_ai_task(
            product_id=product.id,
            force=True,
        )

    assert first_submitted is True
    assert second_submitted is False
    assert second.id == first.id
    assert second_task_id == first_task_id
    assert AIProcessingLog.objects.filter(product=product).count() == 1
    assert len(submitted) == 1


@pytest.mark.django_db
def test_enqueue_marks_log_failed_when_broker_publish_fails(
    monkeypatch, product, django_capture_on_commit_callbacks
):
    def fail_publish(**kwargs):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr("apps.ai.tasks.process_product_ai_task.apply_async", fail_publish)

    with pytest.raises(RuntimeError, match="broker unavailable"):
        with django_capture_on_commit_callbacks(execute=True):
            enqueue_product_ai_task(product_id=product.id)

    log = AIProcessingLog.objects.get(product=product)
    assert log.status == AIProcessingStatus.FAILED
    assert "broker unavailable" in log.error_message


def test_ai_task_survives_worker_restart():
    assert process_product_ai_task.acks_late is True
    assert process_product_ai_task.reject_on_worker_lost is True


@pytest.mark.django_db
@pytest.mark.parametrize("status", [AIProcessingStatus.PENDING, AIProcessingStatus.PROCESSING])
def test_stale_active_log_does_not_block_rerun(
    monkeypatch, product, django_capture_on_commit_callbacks, status
):
    submitted = []
    monkeypatch.setattr(
        "apps.ai.tasks.process_product_ai_task.apply_async",
        lambda **kwargs: submitted.append(kwargs),
    )
    stale = AIProcessingLog.objects.create(
        product=product, processing_type="full", status=status, input_data={}
    )
    AIProcessingLog.objects.filter(pk=stale.pk).update(
        updated_at=timezone.now() - timedelta(minutes=61)
    )

    with django_capture_on_commit_callbacks(execute=True):
        log, _, was_submitted = enqueue_product_ai_task(product_id=product.id, force=True)

    stale.refresh_from_db()
    assert was_submitted is True
    assert log.id != stale.id
    assert stale.status == AIProcessingStatus.FAILED
    assert len(submitted) == 1


def _broken_generator(monkeypatch, exc):
    class BrokenGenerator:
        def process_product(self, **kwargs):
            AIProcessingLog.objects.filter(pk=kwargs["log_entry_id"]).update(
                status=AIProcessingStatus.FAILED
            )
            raise exc

    monkeypatch.setattr("apps.ai.tasks.ContentGenerator", BrokenGenerator)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "exc",
    [
        openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com")),
        openai.RateLimitError(
            "rate limit",
            response=httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com")),
            body=None,
        ),
        openai.InternalServerError(
            "bad gateway",
            response=httpx.Response(502, request=httpx.Request("POST", "https://api.openai.com")),
            body=None,
        ),
    ],
)
def test_retry_reuses_the_same_log_for_transient_errors(monkeypatch, product, exc):
    log = AIProcessingLog.objects.create(
        product=product, processing_type="full", status=AIProcessingStatus.PENDING, input_data={}
    )
    _broken_generator(monkeypatch, exc)
    retries = []

    def fake_retry(*, exc, countdown):
        retries.append(exc)
        raise Retry("scheduled")

    monkeypatch.setattr(process_product_ai_task, "retry", fake_retry)

    with pytest.raises(Retry):
        process_product_ai_task.run(product_id=product.id, log_entry_id=log.id)

    log.refresh_from_db()
    assert len(retries) == 1
    assert log.status == AIProcessingStatus.PENDING
    assert AIProcessingLog.objects.filter(product=product).count() == 1


@pytest.mark.django_db
def test_value_error_is_not_retried(monkeypatch, product):
    log = AIProcessingLog.objects.create(
        product=product, processing_type="full", status=AIProcessingStatus.PENDING, input_data={}
    )
    _broken_generator(monkeypatch, ValueError("AI вернул пустой или невалидный JSON"))
    monkeypatch.setattr(
        process_product_ai_task,
        "retry",
        lambda **kwargs: pytest.fail("ValueError must not be retried"),
    )

    with pytest.raises(ValueError):
        process_product_ai_task.run(product_id=product.id, log_entry_id=log.id)

    log.refresh_from_db()
    assert log.status == AIProcessingStatus.FAILED


@pytest.mark.django_db
def test_task_for_superseded_log_is_skipped(monkeypatch, product):
    log = AIProcessingLog.objects.create(
        product=product, processing_type="full", status=AIProcessingStatus.FAILED, input_data={}
    )
    monkeypatch.setattr(
        "apps.ai.tasks.ContentGenerator",
        lambda: pytest.fail("superseded task must not call the generator"),
    )

    result = process_product_ai_task.run(product_id=product.id, log_entry_id=log.id)

    assert result["status"] == "skipped"
