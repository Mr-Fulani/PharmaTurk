from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.models import Category, FurnitureProduct


@pytest.mark.django_db
def test_furniture_backfill_is_dry_run_by_default_and_reports_bad_title():
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
    assert "TITLE_MISMATCH" in stdout.getvalue()
    assert "DRY-RUN" in stdout.getvalue()

    stdout = StringIO()
    call_command("backfill_furniture_attributes", "--apply", stdout=stdout)

    assert product.dynamic_attributes.get(attribute_key__slug="furniture-type").value_ru == (
        "Двуспальное основание кровати"
    )
    assert product.dynamic_attributes.get(attribute_key__slug="width").value_en == "194 cm"
    assert "APPLY" in stdout.getvalue()
