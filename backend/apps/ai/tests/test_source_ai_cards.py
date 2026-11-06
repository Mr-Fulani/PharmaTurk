import gzip
import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.models import AIProcessingLog, AIProcessingStatus
from apps.catalog.models import Product

pytestmark = pytest.mark.django_db


def _product(external_id, **extra):
    return Product.objects.create(
        name=f"Nike {external_id} Erkek Spor Ayakkabı",
        slug=f"p-{external_id}",
        product_type="shoes",
        price=100,
        currency="TRY",
        external_id=external_id,
        external_data={},
        **extra,
    )


class FakeGenerator:
    calls = []
    applied = []

    def process_product(self, product_id, processing_type, auto_apply):
        FakeGenerator.calls.append((product_id, processing_type, auto_apply))
        return AIProcessingLog.objects.create(
            product_id=product_id,
            processing_type="full",
            status=AIProcessingStatus.COMPLETED,
            input_data={},
            raw_llm_response={"rule_content": {"description_source": "memory", "title_sources": {"ru": "rules"}}},
        )

    def apply_log_to_product(self, log):
        FakeGenerator.applied.append(log.pk)
        log.status = AIProcessingStatus.APPROVED
        log.application_status = "applied"
        return log


@pytest.fixture
def generator(monkeypatch):
    FakeGenerator.calls, FakeGenerator.applied = [], []
    monkeypatch.setattr("apps.ai.management.commands.source_ai_cards.ContentGenerator", FakeGenerator)
    return FakeGenerator


def test_show_counts_only_new_products_of_source(generator):
    _product("superstep-1")
    done = _product("superstep-2")
    _product("flo-3")
    AIProcessingLog.objects.create(product=done, processing_type="full", status=AIProcessingStatus.COMPLETED, input_data={})
    out = StringIO()

    call_command("source_ai_cards", "--source", "superstep", stdout=out)

    assert "Без русской карточки: 1" in out.getvalue()
    assert generator.calls == []


def test_run_makes_drafts_without_applying_and_reports_memory(generator):
    first, second = _product("superstep-1"), _product("superstep-2")
    _product("flo-3")
    out = StringIO()

    call_command("source_ai_cards", "--source", "superstep", "--run", "--workers", "1", stdout=out)

    assert sorted(generator.calls) == [(first.id, "full", False), (second.id, "full", False)]
    report = json.loads(out.getvalue().strip().splitlines()[-1])
    assert report["логов"] == 2
    assert report["описание"] == {"memory": 2}
    assert generator.applied == []


def test_apply_requires_backup(generator):
    with pytest.raises(CommandError):
        call_command("source_ai_cards", "--source", "superstep", "--apply")


def test_apply_backs_up_rows_and_applies_only_completed(generator, tmp_path):
    ready, moderated = _product("superstep-1"), _product("superstep-2")
    other = _product("flo-3")
    log = AIProcessingLog.objects.create(product=ready, processing_type="full", status=AIProcessingStatus.COMPLETED, input_data={})
    AIProcessingLog.objects.create(product=moderated, processing_type="full", status=AIProcessingStatus.MODERATION, input_data={})
    AIProcessingLog.objects.create(product=other, processing_type="full", status=AIProcessingStatus.COMPLETED, input_data={})
    backup = tmp_path / "rows.json.gz"

    call_command("source_ai_cards", "--source", "superstep", "--apply", "--backup", str(backup), stdout=StringIO())

    assert generator.applied == [log.pk]
    rows = json.loads(gzip.open(backup, "rt").read())
    assert {"model": "catalog.product", "pk": ready.pk} in [{"model": r["model"], "pk": r["pk"]} for r in rows]
    assert all(r["pk"] != other.pk for r in rows if r["model"] == "catalog.product")
