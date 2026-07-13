import pytest

from apps.ai.models import AIProcessingLog, AIProcessingStatus
from apps.ai.tasks import enqueue_product_ai_task
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
