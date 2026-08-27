from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

MIGRATE_FROM = [("orders", "0010_cartitem_source_verification")]
MIGRATE_TO = [("orders", "0011_orderitem_source_snapshot")]


@pytest.mark.django_db(transaction=True)
def test_orderitem_snapshot_schema_preserves_historical_order_lines():
    executor = MigrationExecutor(connection)
    latest_targets = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate(MIGRATE_FROM)
        old_apps = executor.loader.project_state(MIGRATE_FROM).apps
        OldProduct = old_apps.get_model("catalog", "Product")
        OldOrder = old_apps.get_model("orders", "Order")
        OldOrderItem = old_apps.get_model("orders", "OrderItem")
        product = OldProduct.objects.create(
            name="Historical order product",
            slug="historical-order-product-before-source-snapshot",
        )
        order = OldOrder.objects.create(
            number="HISTORICAL-SOURCE-SNAPSHOT",
            contact_name="Historical User",
            contact_phone="+905550000000",
        )
        item = OldOrderItem.objects.create(
            order_id=order.pk,
            product_id=product.pk,
            product_name=product.name,
            price=Decimal("42.50"),
            quantity=2,
            total=Decimal("85.00"),
        )

        executor = MigrationExecutor(connection)
        executor.migrate(MIGRATE_TO)
        new_apps = executor.loader.project_state(MIGRATE_TO).apps
        NewOrderItem = new_apps.get_model("orders", "OrderItem")
        migrated = NewOrderItem.objects.get(pk=item.pk)

        assert migrated.price == Decimal("42.50")
        assert migrated.source_parser == ""
        assert migrated.source_url == ""
        assert migrated.source_selected_options == {}
        assert migrated.source_price is None
        assert migrated.source_stock_quantity is None
        assert migrated.source_checked_at is None
        assert migrated.supplier_confirmation_required is False
    finally:
        MigrationExecutor(connection).migrate(latest_targets)
