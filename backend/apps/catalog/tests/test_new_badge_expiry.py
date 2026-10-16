"""Бейдж «Новинка» — только для недавно добавленных товаров."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Product


@pytest.mark.django_db
def test_expire_new_badges_clears_only_old_products(settings, monkeypatch):
    from apps.catalog.tasks import expire_new_badges

    monkeypatch.setattr(Product, "update_currency_prices", lambda *a, **k: None)
    settings.NEW_BADGE_DAYS = 30
    old = Product.objects.create(name="Old", slug="nb-old", price=Decimal("1"), is_new=True)
    fresh = Product.objects.create(name="Fresh", slug="nb-fresh", price=Decimal("1"), is_new=True)
    Product.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=45))

    cleared = expire_new_badges.run()

    old.refresh_from_db()
    fresh.refresh_from_db()
    assert cleared == 1
    assert old.is_new is False
    assert fresh.is_new is True
