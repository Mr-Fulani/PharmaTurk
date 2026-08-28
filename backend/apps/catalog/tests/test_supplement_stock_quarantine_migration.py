from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


MIGRATE_FROM = [("catalog", "0203_productmarketcheck_medicineanalog_market_fields")]
MIGRATE_TO = [("catalog", "0204_quarantine_ilacfiyati_fake_stock")]


@pytest.mark.django_db(transaction=True)
def test_ilacfiyati_supplement_stock_is_quarantined_without_losing_offer_metadata():
    executor = MigrationExecutor(connection)
    latest_targets = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate(MIGRATE_FROM)
        old_apps = executor.loader.project_state(MIGRATE_FROM).apps
        Product = old_apps.get_model("catalog", "Product")
        ProductSourceOffer = old_apps.get_model("catalog", "ProductSourceOffer")
        SupplementProduct = old_apps.get_model("catalog", "SupplementProduct")

        base = Product.objects.create(
            name="Legacy reference supplement",
            slug="legacy-reference-supplement-before-quarantine",
            product_type="supplements",
            price=Decimal("49.70"),
            currency="TRY",
            is_available=True,
            stock_quantity=3,
            external_url=(
                "https://ilacfiyati.com/takviye-edici-gida/"
                "legacy-reference-supplement"
            ),
            external_data={"source": "ilacfiyati"},
        )
        supplement = SupplementProduct.objects.create(
            base_product_id=base.pk,
            name=base.name,
            slug=base.slug,
            price=base.price,
            currency="TRY",
            is_available=True,
            stock_quantity=3,
            external_url="",
            external_data={},
        )
        reference_offer = ProductSourceOffer.objects.create(
            product_id=base.pk,
            parser_key="ilacfiyati",
            source_domain="ilacfiyati.com",
            canonical_url=base.external_url,
            offer_key="a" * 64,
            source_price=Decimal("49.70"),
            source_currency="TRY",
            availability_status="in_stock",
            stock_precision="boolean",
            stock_quantity=None,
            response_metadata={"legacy_marker": "preserve-me"},
        )

        unrelated = Product.objects.create(
            name="Real supplier supplement",
            slug="real-supplier-supplement-before-quarantine",
            product_type="supplements",
            price=Decimal("80.00"),
            currency="TRY",
            is_available=True,
            stock_quantity=7,
            external_url="https://supplier.example/supplements/real",
        )
        unrelated_supplement = SupplementProduct.objects.create(
            base_product_id=unrelated.pk,
            name=unrelated.name,
            slug=unrelated.slug,
            price=unrelated.price,
            currency="TRY",
            is_available=True,
            stock_quantity=7,
            external_url=unrelated.external_url,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(MIGRATE_TO)
        new_apps = executor.loader.project_state(MIGRATE_TO).apps
        NewProduct = new_apps.get_model("catalog", "Product")
        NewProductSourceOffer = new_apps.get_model("catalog", "ProductSourceOffer")
        NewSupplementProduct = new_apps.get_model("catalog", "SupplementProduct")

        migrated_base = NewProduct.objects.get(pk=base.pk)
        migrated_supplement = NewSupplementProduct.objects.get(pk=supplement.pk)
        migrated_offer = NewProductSourceOffer.objects.get(pk=reference_offer.pk)
        assert migrated_base.is_available is False
        assert migrated_base.stock_quantity is None
        assert migrated_supplement.is_available is False
        assert migrated_supplement.stock_quantity is None
        assert migrated_offer.availability_status == "unknown"
        assert migrated_offer.stock_precision == "unknown"
        assert migrated_offer.stock_quantity is None
        assert migrated_offer.response_metadata == {"legacy_marker": "preserve-me"}

        untouched_base = NewProduct.objects.get(pk=unrelated.pk)
        untouched_supplement = NewSupplementProduct.objects.get(
            pk=unrelated_supplement.pk
        )
        assert untouched_base.is_available is True
        assert untouched_base.stock_quantity == 7
        assert untouched_supplement.is_available is True
        assert untouched_supplement.stock_quantity == 7
    finally:
        MigrationExecutor(connection).migrate(latest_targets)
