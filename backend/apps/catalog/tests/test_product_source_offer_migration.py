import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

MIGRATE_FROM = [("catalog", "0201_canonicalize_favorite_product_identity")]
MIGRATE_TO = [("catalog", "0202_productsourceoffer")]


@pytest.mark.django_db(transaction=True)
def test_product_source_offer_schema_is_forward_compatible_with_existing_products():
    executor = MigrationExecutor(connection)
    latest_targets = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate(MIGRATE_FROM)
        old_apps = executor.loader.project_state(MIGRATE_FROM).apps
        OldProduct = old_apps.get_model("catalog", "Product")
        old_product = OldProduct.objects.create(
            name="Existing product before source offers",
            slug="existing-product-before-source-offers",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(MIGRATE_TO)
        new_apps = executor.loader.project_state(MIGRATE_TO).apps
        NewProduct = new_apps.get_model("catalog", "Product")
        SourceOffer = new_apps.get_model("catalog", "ProductSourceOffer")

        assert NewProduct.objects.filter(pk=old_product.pk).exists()
        offer = SourceOffer.objects.create(
            product_id=old_product.pk,
            parser_key="zara",
            source_domain="www.zara.com",
            canonical_url="https://www.zara.com/product-p1.html",
            offer_key="a" * 64,
            availability_status="unknown",
            stock_precision="unknown",
        )
        assert offer.product_id == old_product.pk
    finally:
        MigrationExecutor(connection).migrate(latest_targets)
