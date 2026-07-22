from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import Category, FurnitureProduct


@pytest.mark.django_db
def test_furniture_backfill_is_dry_run_by_default_and_audits_titles_only_on_request():
    category = Category.objects.create(name="Основания кроватей", slug="bed-bases")
    product = FurnitureProduct.objects.create(
        name="Кровать TONSTAD",
        slug="backfill-tonstad",
        category=category,
        furniture_type="çift kişilik baza",
        dimensions="<p>Genişlik: 194 cm</p>",
    )
    stdout = StringIO()

    call_command("backfill_furniture_attributes", stdout=stdout)

    assert product.dynamic_attributes.count() == 0
    assert "TITLE_MISMATCH" not in stdout.getvalue()
    assert "audit_titles=false" in stdout.getvalue()
    assert "DRY-RUN" in stdout.getvalue()

    stdout = StringIO()
    call_command(
        "backfill_furniture_attributes",
        "--audit-titles",
        stdout=stdout,
    )

    assert "TITLE_MISMATCH" in stdout.getvalue()
    assert "audit_titles=true" in stdout.getvalue()
    assert "DRY-RUN" in stdout.getvalue()

    stdout = StringIO()
    call_command("backfill_furniture_attributes", "--apply", stdout=stdout)

    assert product.dynamic_attributes.get(attribute_key__slug="furniture-type").value_ru == (
        "Двуспальное основание кровати"
    )
    assert product.dynamic_attributes.get(attribute_key__slug="width").value_en == "194 cm"
    assert "APPLY" in stdout.getvalue()


@pytest.mark.django_db
def test_furniture_backfill_supports_batches_limits_resume_and_is_idempotent():
    category = Category.objects.create(name="Основания кроватей", slug="batch-bed-bases")
    products = [
        FurnitureProduct.objects.create(
            name=f"Основание {index}",
            slug=f"batch-bed-base-{index}",
            category=category,
            furniture_type="çift kişilik baza",
        )
        for index in range(3)
    ]
    stdout = StringIO()

    call_command(
        "backfill_furniture_attributes",
        "--apply",
        "--batch-size",
        "1",
        "--start-pk",
        str(products[1].pk),
        "--limit",
        "1",
        stdout=stdout,
    )

    assert products[0].dynamic_attributes.count() == 0
    assert products[1].dynamic_attributes.count() == 1
    assert products[2].dynamic_attributes.count() == 0
    assert f"last_pk={products[1].pk}" in stdout.getvalue()
    assert f"resume_start_pk={products[1].pk + 1}" in stdout.getvalue()

    stdout = StringIO()
    call_command(
        "backfill_furniture_attributes",
        "--apply",
        "--start-pk",
        str(products[1].pk),
        "--limit",
        "1",
        stdout=stdout,
    )

    assert "changed=0" in stdout.getvalue()


@pytest.mark.django_db
def test_furniture_backfill_preserves_manual_values_unless_overwrite_is_explicit():
    category = Category.objects.create(name="Основания кроватей", slug="overwrite-bed-bases")
    product = FurnitureProduct.objects.create(
        name="Основание",
        slug="overwrite-bed-base",
        category=category,
        furniture_type="çift kişilik baza",
    )
    call_command("backfill_furniture_attributes", "--apply")
    value = product.dynamic_attributes.get(attribute_key__slug="furniture-type")
    value.value = "Ручное значение"
    value.value_ru = "Ручное значение"
    value.save(update_fields=["value", "value_ru"])

    call_command("backfill_furniture_attributes", "--apply")
    value.refresh_from_db()
    assert value.value_ru == "Ручное значение"

    call_command("backfill_furniture_attributes", "--apply", "--overwrite")
    value.refresh_from_db()
    assert value.value_ru == "Двуспальное основание кровати"


@pytest.mark.django_db
def test_furniture_backfill_rejects_unsafe_or_invalid_flag_combinations():
    with pytest.raises(CommandError, match="--overwrite"):
        call_command("backfill_furniture_attributes", "--overwrite")
    with pytest.raises(CommandError, match="--batch-size"):
        call_command("backfill_furniture_attributes", "--batch-size", "0")
    with pytest.raises(CommandError, match="--start-pk"):
        call_command("backfill_furniture_attributes", "--start-pk", "-1")


@pytest.mark.django_db
def test_furniture_title_audit_has_bounded_query_count(django_assert_max_num_queries):
    bed_bases = Category.objects.create(name="Основания кроватей", slug="bed-bases")
    Category.objects.create(name="Кровати", slug="beds")
    for index in range(10):
        FurnitureProduct.objects.create(
            name=f"Кровать MODEL-{index}",
            slug=f"query-count-bed-base-{index}",
            category=bed_bases,
        )

    with django_assert_max_num_queries(6):
        call_command(
            "backfill_furniture_attributes",
            "--audit-titles",
            "--batch-size",
            "3",
            stdout=StringIO(),
        )


@pytest.mark.django_db
def test_furniture_apply_batch_has_bounded_query_count(django_assert_max_num_queries):
    category = Category.objects.create(name="Основания кроватей", slug="bulk-bed-bases")
    for index in range(10):
        FurnitureProduct.objects.create(
            name=f"Основание BULK-{index}",
            slug=f"bulk-query-count-{index}",
            category=category,
            furniture_type="çift kişilik baza",
        )

    with django_assert_max_num_queries(20):
        call_command(
            "backfill_furniture_attributes",
            "--apply",
            "--batch-size",
            "20",
            stdout=StringIO(),
        )

    assert (
        sum(product.dynamic_attributes.count() for product in FurnitureProduct.objects.all()) == 10
    )
