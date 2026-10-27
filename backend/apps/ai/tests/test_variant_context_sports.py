"""Контекст вариантов для AI у спорттоваров: у SportsVariant нет is_active и sort_order."""

from decimal import Decimal
from uuid import uuid4

import pytest

from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.variant_detector import VariantContentDetector
from apps.catalog.models import Category, Product, SportsProduct, SportsVariant


@pytest.mark.django_db
def test_sports_variants_feed_context_without_is_active_field():
    """27.10.2026: мужские бриджи для плавания в «Плавание › Купальники» падали
    в AI с FieldError «Cannot resolve keyword 'is_active'»."""
    category = Category.objects.create(name="Купальники", slug=f"swimwear-{uuid4().hex[:8]}")
    base = Product.objects.create(
        name="Мужские бриджи для плавания",
        slug=f"swim-bridges-{uuid4().hex[:8]}",
        product_type="sports",
        category=category,
        price=Decimal("1000"),
    )
    sports = SportsProduct.objects.get(base_product=base)
    SportsVariant.objects.create(product=sports, color="Синий", size="L", price=Decimal("1000"))

    generator = ContentGenerator.__new__(ContentGenerator)
    generator.variant_detector = VariantContentDetector()
    context = generator._collect_variant_context(Product.objects.get(pk=base.pk))

    assert context is not None
    assert "Синий" in str(context)
