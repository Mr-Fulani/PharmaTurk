import gzip
import json
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.management.commands import source_ai_cards
from apps.ai.models import AIProcessingLog, AIProcessingStatus
from apps.catalog.models import Brand, Category, Product

pytestmark = pytest.mark.django_db


@pytest.fixture
def category():
    return Category.objects.create(name="Кроссовки", slug="source-cards-sneakers")


def _product(external_id, category=None, **extra):
    return Product.objects.create(
        name=f"Nike {external_id} Erkek Spor Ayakkabı",
        slug=f"p-{external_id}",
        product_type="shoes",
        price=100,
        currency="TRY",
        external_id=external_id,
        external_data={},
        category=category,
        **extra,
    )


def _log(product, status=AIProcessingStatus.COMPLETED, **extra):
    return AIProcessingLog.objects.create(
        product=product, processing_type="full", status=status, input_data={"name": product.name}, **extra
    )


class FakeGenerator:
    calls, applied, options, synced = [], [], [], []

    def process_product(self, product_id, processing_type, auto_apply, options=None):
        FakeGenerator.calls.append((product_id, processing_type, auto_apply))
        FakeGenerator.options.append(options)
        return AIProcessingLog.objects.create(
            product_id=product_id,
            processing_type="full",
            status=AIProcessingStatus.COMPLETED,
            input_data={},
            raw_llm_response={"rule_content": {"description_source": "memory", "title_sources": {"ru": "rules"}}},
        )

    def apply_log_to_product(self, log):
        FakeGenerator.applied.append(log.pk)
        product = log.product
        product.name = "Мужские кроссовки Nike"  # применение меняет название, а не цену/бренд/раздел
        product.save(update_fields=["name"])
        log.status = AIProcessingStatus.APPROVED
        log.application_status = "applied"
        return log

    def sync_variant_titles_from_parent(self, product, log_entry=None):
        FakeGenerator.synced.append(product.pk)
        return 0


@pytest.fixture
def generator(monkeypatch, settings):
    settings.AI_OPENAI_ENABLED = False
    FakeGenerator.calls, FakeGenerator.applied, FakeGenerator.options, FakeGenerator.synced = [], [], [], []
    monkeypatch.setattr(source_ai_cards, "ContentGenerator", FakeGenerator)
    monkeypatch.setattr(source_ai_cards.Command, "_check_night", staticmethod(lambda: None))
    return FakeGenerator


def test_show_counts_only_new_active_products_with_category(generator, category):
    _product("superstep-1", category)
    done = _product("superstep-2", category)
    _product("superstep-3", category, is_active=False)
    _product("superstep-4")  # без раздела — категоризация шла бы через OpenAI
    _product("flo-5", category)
    _log(done)
    out = StringIO()

    call_command("source_ai_cards", "--source", "superstep", stdout=out)

    assert "Без русской карточки: 1" in out.getvalue()
    assert "'неактивные': 1, 'без раздела': 1" in out.getvalue()
    assert generator.calls == []


def test_run_makes_drafts_without_applying_and_reports_memory(generator, category):
    first, second = _product("superstep-1", category), _product("superstep-2", category)
    _product("superstep-3")  # без раздела
    out = StringIO()

    call_command("source_ai_cards", "--source", "superstep", "--run", "--workers", "1", stdout=out)

    assert sorted(generator.calls) == [(first.id, "full", False), (second.id, "full", False)]
    report = json.loads(out.getvalue().strip().splitlines()[-1])
    assert report["логов"] == 2 and report["описание"] == {"memory": 2}
    assert generator.applied == []


def test_run_refuses_when_openai_is_enabled(generator, settings, category):
    settings.AI_OPENAI_ENABLED = True
    _product("superstep-1", category)

    with pytest.raises(CommandError, match="OpenAI"):
        call_command("source_ai_cards", "--source", "superstep", "--run", "--workers", "1", stdout=StringIO())
    assert generator.calls == []


def test_force_reprocesses_products_with_logs(generator, category):
    done = _product("superstep-1", category)
    _log(done)

    call_command("source_ai_cards", "--source", "superstep", "--run", "--force", "--workers", "1", stdout=StringIO())

    assert generator.calls == [(done.id, "full", False)]
    assert generator.options == [{"force": True}]


def test_bad_ids_and_missing_since_are_command_errors(generator):
    with pytest.raises(CommandError, match="--ids"):
        call_command("source_ai_cards", "--source", "superstep", "--ids", "1,abc", stdout=StringIO())
    with pytest.raises(CommandError, match="--since"):
        call_command("source_ai_cards", "--source", "superstep", "--apply", "--backup", "/tmp/x.json")


def test_night_window_blocks_run(monkeypatch, settings):
    settings.AI_OPENAI_ENABLED = False
    night = datetime(2026, 11, 6, 23, 0, tzinfo=dt_timezone.utc)  # 02:00 МСК
    monkeypatch.setattr(source_ai_cards.timezone, "now", lambda: night)

    with pytest.raises(CommandError, match="01:00"):
        call_command("source_ai_cards", "--source", "superstep", "--run", stdout=StringIO())


def test_apply_skips_product_whose_newest_log_is_in_moderation(generator, category, tmp_path):
    product = _product("superstep-1", category)
    _log(product)
    _log(product, status=AIProcessingStatus.MODERATION)
    out = StringIO()

    call_command(
        "source_ai_cards", "--source", "superstep", "--apply", "--since", "2026-11-05",
        "--backup", str(tmp_path / "rows.json"), stdout=out,
    )

    assert generator.applied == []
    assert "самый новый лог не «Завершено»" in out.getvalue()


def test_apply_backs_up_rows_keeps_price_brand_category_and_restores(generator, category, tmp_path):
    brand = Brand.objects.create(name="Nike", slug="source-cards-nike")
    ready = _product("superstep-1", category, brand=brand)
    moderated, old = _product("superstep-2", category), _product("superstep-3", category)
    edited, other = _product("superstep-4", category), _product("flo-5", category)
    log = _log(ready)
    _log(moderated, status=AIProcessingStatus.MODERATION)
    stale = _log(old)
    AIProcessingLog.objects.filter(pk=stale.pk).update(created_at=datetime(2026, 11, 1, tzinfo=dt_timezone.utc))
    edited_log = _log(edited)
    Product.objects.filter(pk=edited.pk).update(name="Кроссовки, правка менеджера")
    _log(other)
    backup = tmp_path / "rows.json.gz"
    out = StringIO()

    call_command(
        "source_ai_cards", "--source", "superstep", "--apply", "--since", "2026-11-05",
        "--backup", str(backup), stdout=out,
    )

    assert generator.applied == [log.pk] and generator.synced == [ready.pk]
    assert f"{edited.pk}: название менялось" in out.getvalue() and edited_log.pk not in generator.applied
    ready.refresh_from_db()
    assert (ready.price, ready.currency, ready.brand_id, ready.category_id) == (Decimal("100"), "TRY", brand.pk, category.pk)
    rows = json.loads(gzip.open(backup, "rt").read())
    assert [r["pk"] for r in rows if r["model"] == "catalog.product"] == [ready.pk]
    assert json.loads((tmp_path / "rows.json.gz.created.json").read_text()) == []
    with pytest.raises(FileExistsError):  # чужой бэкап не затирается
        call_command(
            "source_ai_cards", "--source", "superstep", "--apply", "--since", "2026-11-05",
            "--backup", str(backup), stdout=StringIO(),
        )

    call_command("source_ai_cards", "--restore", str(backup), stdout=StringIO())

    ready.refresh_from_db()
    assert ready.name == "Nike superstep-1 Erkek Spor Ayakkabı"


def test_failed_variant_sync_rolls_back_whole_product(generator, category, tmp_path, monkeypatch):
    product = _product("superstep-1", category)
    _log(product)

    def broken_sync(self, product, log_entry=None):
        raise RuntimeError("Cannot resolve keyword 'is_active' into field")

    monkeypatch.setattr(generator, "sync_variant_titles_from_parent", broken_sync)
    out = StringIO()

    call_command(
        "source_ai_cards", "--source", "superstep", "--apply", "--since", "2026-11-05",
        "--backup", str(tmp_path / "rows.json"), stdout=out,
    )

    product.refresh_from_db()
    assert product.name == "Nike superstep-1 Erkek Spor Ayakkabı"  # применение откатилось вместе с синхронизацией
    assert "'error': 1" in out.getvalue()
    assert json.loads((tmp_path / "rows.json.created.json").read_text()) == []


def test_variant_title_sync_skips_variants_without_name_field():
    from apps.ai.services.content_generator import ContentGenerator
    from apps.catalog.models import SportsProduct, SportsVariant

    product = Product.objects.create(
        name="Nike Elite Tournament 7 No Unisex Turuncu Basketbol Topu", slug="sports-sync-ball",
        product_type="sports", price=100, currency="TRY", external_id="superstep-26934",
    )
    sports, _ = SportsProduct.objects.update_or_create(
        base_product=product, defaults={"name": product.name, "slug": "sports-sync-ball"}
    )
    SportsVariant.objects.create(product=sports, color="Turuncu", size="7")
    generator = ContentGenerator.__new__(ContentGenerator)
    product.refresh_from_db()
    assert isinstance(product.domain_item, SportsProduct)  # иначе тест не дошёл бы до вариантов

    assert generator.sync_variant_titles_from_parent(product) == 0  # у SportsVariant нет name/is_active/sort_order
