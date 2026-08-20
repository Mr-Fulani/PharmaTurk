import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


MIGRATE_FROM = [("orders", "0007_update_currency_max_length")]
MIGRATE_TO = [("orders", "0009_cart_identity_constraints")]


@pytest.mark.django_db(transaction=True)
def test_cart_identity_migration_keeps_lowest_id_for_duplicate_anonymous_session():
    executor = MigrationExecutor(connection)
    latest_targets = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate(MIGRATE_FROM)
        old_apps = executor.loader.project_state(MIGRATE_FROM).apps
        OldCart = old_apps.get_model("orders", "Cart")
        canonical = OldCart.objects.create(
            session_key="migration-duplicate-anonymous-session",
            currency="RUB",
        )
        duplicate = OldCart.objects.create(
            session_key="migration-duplicate-anonymous-session",
            currency="USD",
        )
        assert canonical.pk < duplicate.pk

        executor = MigrationExecutor(connection)
        executor.migrate(MIGRATE_TO)
        new_apps = executor.loader.project_state(MIGRATE_TO).apps
        NewCart = new_apps.get_model("orders", "Cart")
        surviving_ids = list(
            NewCart.objects.filter(
                user__isnull=True,
                session_key="migration-duplicate-anonymous-session",
            ).values_list("pk", flat=True)
        )

        assert surviving_ids == [canonical.pk]
    finally:
        # Migration tests mutate global schema state; always restore every app
        # to its graph leaf so later tests see the normal current schema.
        MigrationExecutor(connection).migrate(latest_targets)
