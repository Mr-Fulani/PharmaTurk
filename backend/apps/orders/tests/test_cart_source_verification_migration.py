from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

MIGRATE_FROM = [
    ("catalog", "0202_productsourceoffer"),
    ("orders", "0009_cart_identity_constraints"),
]
MIGRATE_TO = [
    ("catalog", "0202_productsourceoffer"),
    ("orders", "0010_cartitem_source_verification"),
]


@pytest.mark.django_db(transaction=True)
def test_cart_verification_schema_preserves_existing_cart_items():
    executor = MigrationExecutor(connection)
    latest_targets = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate(MIGRATE_FROM)
        old_apps = executor.loader.project_state(MIGRATE_FROM).apps
        OldProduct = old_apps.get_model("catalog", "Product")
        OldCart = old_apps.get_model("orders", "Cart")
        OldCartItem = old_apps.get_model("orders", "CartItem")
        product = OldProduct.objects.create(
            name="Existing cart product",
            slug="existing-cart-product-before-verification",
        )
        cart = OldCart.objects.create(session_key="existing-cart-before-verification")
        item = OldCartItem.objects.create(
            cart_id=cart.pk,
            product_id=product.pk,
            quantity=2,
            price=Decimal("42.50"),
            currency="TRY",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(MIGRATE_TO)
        new_apps = executor.loader.project_state(MIGRATE_TO).apps
        NewCartItem = new_apps.get_model("orders", "CartItem")
        migrated = NewCartItem.objects.get(pk=item.pk)

        assert migrated.quantity == 2
        assert migrated.price == Decimal("42.50")
        assert migrated.source_offer_id is None
        assert migrated.verification_status == "not_checked"
        assert migrated.verification_issues == []
        assert migrated.observed_stock_precision == "unknown"
        assert migrated.observed_stock_quantity is None
        assert migrated.observed_public_price is None
        assert migrated.observed_public_currency == ""
    finally:
        MigrationExecutor(connection).migrate(latest_targets)
