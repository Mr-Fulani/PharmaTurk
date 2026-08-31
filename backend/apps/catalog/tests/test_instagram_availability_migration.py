import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

MIGRATE_FROM = [("catalog", "0205_media_enrichment_manual_moderation")]
MIGRATE_TO = [("catalog", "0206_restore_instagram_catalog_availability")]


@pytest.mark.django_db(transaction=True)
def test_instagram_products_are_restored_without_touching_other_sources():
    executor = MigrationExecutor(connection)
    latest_targets = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate(MIGRATE_FROM)
        old_apps = executor.loader.project_state(MIGRATE_FROM).apps
        Product = old_apps.get_model("catalog", "Product")
        ProductSourceOffer = old_apps.get_model("catalog", "ProductSourceOffer")
        IslamicClothingProduct = old_apps.get_model("catalog", "IslamicClothingProduct")

        instagram = Product.objects.create(
            name="Instagram burkini",
            slug="instagram-burkini-before-restore",
            product_type="islamic_clothing",
            price=100,
            currency="RUB",
            is_available=False,
            availability_status="out_of_stock",
            external_url="https://www.instagram.com/p/POST1/",
            external_data={"source": "instagram"},
        )
        domain = IslamicClothingProduct.objects.create(
            base_product_id=instagram.pk,
            name=instagram.name,
            slug=instagram.slug,
            price=instagram.price,
            currency=instagram.currency,
            is_available=False,
            external_url=instagram.external_url,
            external_data={"source": "instagram"},
        )
        offer = ProductSourceOffer.objects.create(
            product_id=instagram.pk,
            parser_key="instagram",
            source_domain="www.instagram.com",
            canonical_url=instagram.external_url,
            offer_key="i" * 64,
            external_product_id="POST1",
            availability_status="out_of_stock",
            stock_precision="boolean",
            stock_quantity=None,
            last_error_code="not_found",
            last_error_message="caption had no price",
            consecutive_failures=2,
        )
        unrelated = Product.objects.create(
            name="Unrelated unavailable product",
            slug="unrelated-unavailable-before-instagram-restore",
            product_type="clothing",
            is_available=False,
            availability_status="out_of_stock",
            external_url="https://www.zara.com/product/1",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(MIGRATE_TO)
        new_apps = executor.loader.project_state(MIGRATE_TO).apps
        NewProduct = new_apps.get_model("catalog", "Product")
        NewProductSourceOffer = new_apps.get_model("catalog", "ProductSourceOffer")
        NewIslamicClothingProduct = new_apps.get_model("catalog", "IslamicClothingProduct")

        restored = NewProduct.objects.get(pk=instagram.pk)
        restored_domain = NewIslamicClothingProduct.objects.get(pk=domain.pk)
        restored_offer = NewProductSourceOffer.objects.get(pk=offer.pk)
        assert restored.is_available is True
        assert restored.availability_status == "in_stock"
        assert restored_domain.is_available is True
        assert restored_offer.availability_status == "in_stock"
        assert restored_offer.stock_precision == "unknown"
        assert restored_offer.stock_quantity is None
        assert restored_offer.last_error_code == ""
        assert restored_offer.last_error_message == ""
        assert restored_offer.consecutive_failures == 0

        untouched = NewProduct.objects.get(pk=unrelated.pk)
        assert untouched.is_available is False
        assert untouched.availability_status == "out_of_stock"
    finally:
        MigrationExecutor(connection).migrate(latest_targets)
