from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


MIGRATE_FROM = [("orders", "0012_cartitem_pending_confirmation")]
MIGRATE_TO = [("orders", "0013_supplement_pending_items_payable")]


@pytest.mark.django_db(transaction=True)
def test_pending_supplement_cart_items_become_payable_without_touching_other_types():
    executor = MigrationExecutor(connection)
    latest_targets = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate(MIGRATE_FROM)
        old_apps = executor.loader.project_state(MIGRATE_FROM).apps
        Product = old_apps.get_model("catalog", "Product")
        Cart = old_apps.get_model("orders", "Cart")
        CartItem = old_apps.get_model("orders", "CartItem")

        supplement = Product.objects.create(
            name="Pending supplement before policy change",
            slug="pending-supplement-before-policy-change",
            product_type="supplements",
            price=Decimal("49.70"),
            currency="TRY",
        )
        clothing = Product.objects.create(
            name="Pending clothing control",
            slug="pending-clothing-control",
            product_type="clothing",
            price=Decimal("100.00"),
            currency="TRY",
        )
        cart = Cart.objects.create(
            session_key="supplement-payable-migration",
            currency="TRY",
        )
        supplement_item = CartItem.objects.create(
            cart_id=cart.pk,
            product_id=supplement.pk,
            quantity=1,
            price=Decimal("57.16"),
            currency="TRY",
            verification_status="pending_confirmation",
            verification_issues=["supplier_confirmation_required"],
        )
        clothing_item = CartItem.objects.create(
            cart_id=cart.pk,
            product_id=clothing.pk,
            quantity=1,
            price=Decimal("115.00"),
            currency="TRY",
            verification_status="pending_confirmation",
            verification_issues=["supplier_confirmation_required"],
        )

        executor = MigrationExecutor(connection)
        executor.migrate(MIGRATE_TO)
        new_apps = executor.loader.project_state(MIGRATE_TO).apps
        NewCartItem = new_apps.get_model("orders", "CartItem")

        migrated_supplement = NewCartItem.objects.get(pk=supplement_item.pk)
        assert migrated_supplement.verification_status == "not_checked"
        assert migrated_supplement.verification_issues == []

        untouched_clothing = NewCartItem.objects.get(pk=clothing_item.pk)
        assert untouched_clothing.verification_status == "pending_confirmation"
        assert untouched_clothing.verification_issues == [
            "supplier_confirmation_required"
        ]
    finally:
        MigrationExecutor(connection).migrate(latest_targets)
