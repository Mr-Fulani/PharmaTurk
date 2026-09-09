"""Read-only gate for code-only/scoped additive backend releases."""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, migrations, models
from django.db.migrations.executor import MigrationExecutor
from django.db.models import NOT_PROVIDED

from apps.scrapers.models import InstagramScraperTask, SiteScraperTask
from config.celery import app


def scoped_plan(plan):
    """Fail closed: only nullable UUID additions to parser control rows qualify.

    No catalogue rewrites, arbitrary SQL/Python, defaults, indexes or destructive
    schema operations. Extending this allowlist requires a reviewed code change.
    """
    names = []
    for migration, backwards in plan:
        if backwards or migration.app_label != "scrapers" or not migration.operations:
            raise CommandError("Migration requires the full release workflow")
        for operation in migration.operations:
            if type(operation) is not migrations.AddField:
                raise CommandError("Only reviewed additive parser-control migrations qualify")
            field = operation.field
            if (
                operation.model_name.lower() != "sitescrapertask"
                or type(field) is not models.UUIDField
                or not field.null
                or field.default is not NOT_PROVIDED
                or field.db_default is not NOT_PROVIDED
                or field.unique or field.primary_key or field.db_index
                or field.db_column is not None
            ):
                raise CommandError("Unsafe field for scoped release; use full workflow")
        names.append([migration.app_label, migration.name])
    return {
        "migrations": names,
        "tables": ["scrapers_sitescrapertask", "django_migrations"] if names else [],
    }


class Command(BaseCommand):
    help = "Validate a backend-only release without changing any data or schema"

    def handle(self, *args, **options):
        if SiteScraperTask.objects.filter(status__in=["pending", "running"]).exists():
            raise CommandError("Pause active site parsers before a backend release")
        if InstagramScraperTask.objects.filter(status__in=["pending", "running"]).exists():
            raise CommandError("Pause active Instagram parsers before a backend release")
        active = app.control.inspect(timeout=3).active()
        if not active or any(active.values()):
            raise CommandError("Workers must respond and have no active work before release")
        executor = MigrationExecutor(connection)
        executor.loader.check_consistent_history(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        self.stdout.write(json.dumps(scoped_plan(plan), sort_keys=True))
