from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.management import call_command

from apps.ai.models import AIProcessingLog, AIProcessingStatus
from apps.ai.tasks import enqueue_or_apply_product_ai
from apps.catalog.admin_base import AI_ADMIN_MAX_PRODUCTS, RunAIActionMixin
from apps.catalog.models import Category, Product

pytestmark = pytest.mark.django_db


def _product(index, product_type="supplements", **extra):
    return Product.objects.create(
        name=f"Bulk product {index}",
        slug=f"bulk-product-{product_type}-{index}",
        product_type=product_type,
        price=10,
        currency="TRY",
        external_id=f"bulk-{product_type}-{index}",
        external_data={},
        **extra,
    )


@pytest.fixture
def submitted(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.ai.tasks.process_product_ai_task.apply_async",
        lambda **kwargs: calls.append(kwargs),
    )
    return calls


def test_dry_run_reports_selection_and_queues_nothing(submitted):
    for index in range(3):
        _product(index)
    out = StringIO()

    call_command("ai_enqueue", "--product-type", "supplements", "--limit", "2", "--dry-run", stdout=out)

    assert "Выбрано товаров: 2" in out.getvalue()
    assert AIProcessingLog.objects.count() == 0
    assert submitted == []


def test_enqueue_filters_skips_processed_and_disables_vectors(submitted, django_capture_on_commit_callbacks):
    root = Category.objects.create(name="БАДы", slug="bulk-supplements-root")
    child = Category.objects.create(name="Витамины", slug="bulk-vitamins", parent=root)
    in_tree = [_product(index, category=child) for index in range(3)]
    _product(10)  # без категории — вне выборки
    _product(11, product_type="medicines")  # другой тип
    AIProcessingLog.objects.create(
        product=in_tree[0], processing_type="full", status=AIProcessingStatus.APPROVED, input_data={}
    )

    with django_capture_on_commit_callbacks(execute=True):
        call_command(
            "ai_enqueue",
            "--product-type", "supplements",
            "--category", "bulk-supplements-root",
            "--limit", "10",
            "--batch-size", "1",
            "--no-index-vectors",
            stdout=StringIO(),
        )

    queued_ids = sorted(call["kwargs"]["product_id"] for call in submitted)
    assert queued_ids == sorted(product.id for product in in_tree[1:])
    assert all(call["kwargs"]["index_vectors"] is False for call in submitted)
    assert all(call["kwargs"]["auto_apply"] is False for call in submitted)


def test_wait_mode_stops_after_batch_with_too_many_failures(monkeypatch, submitted):
    for index in range(4):
        _product(index)
    monkeypatch.setattr(
        "apps.ai.management.commands.ai_enqueue.Command._wait_for_batch",
        lambda self, log_ids, timeout: len(log_ids),
    )
    out = StringIO()

    call_command(
        "ai_enqueue",
        "--product-type", "supplements",
        "--limit", "4",
        "--batch-size", "2",
        "--wait",
        "--max-failures", "1",
        stdout=out,
    )

    assert "Остановка" in out.getvalue()
    assert AIProcessingLog.objects.count() == 2


def test_auto_apply_applies_existing_completed_log_instead_of_doing_nothing(
    monkeypatch, submitted, django_capture_on_commit_callbacks
):
    product = _product(1)
    ready = AIProcessingLog.objects.create(
        product=product, processing_type="full", status=AIProcessingStatus.COMPLETED, input_data={}
    )
    delay = Mock()
    monkeypatch.setattr("apps.ai.tasks.apply_ai_log_task.delay", delay)

    with django_capture_on_commit_callbacks(execute=True):
        log, action = enqueue_or_apply_product_ai(product_id=product.id, auto_apply=True)

    assert action == "apply_queued"
    assert log.id == ready.id
    delay.assert_called_once_with(ready.id)
    assert submitted == []


def test_admin_refuses_huge_selection():
    admin = RunAIActionMixin()
    admin.message_user = Mock()

    too_large = admin._ai_selection_too_large(
        None, SimpleNamespace(count=lambda: AI_ADMIN_MAX_PRODUCTS + 1)
    )

    assert too_large is True
    assert "ai_enqueue" in str(admin.message_user.call_args)
