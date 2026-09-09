from types import SimpleNamespace

import pytest
from django.core.management.base import CommandError
from django.db import migrations, models

from apps.scrapers.management.commands.backend_release_plan import scoped_plan


def plan(operation, app="scrapers", backwards=False):
    return [(SimpleNamespace(app_label=app, name="next", operations=[operation]), backwards)]


def test_no_pending_schema_requires_no_database_dump():
    assert scoped_plan([]) == {"migrations": [], "tables": []}


def test_nullable_uuid_addition_is_scoped_to_control_table():
    result = scoped_plan(plan(migrations.AddField("sitescrapertask", "run_token", models.UUIDField(null=True))))
    assert result["tables"] == ["scrapers_sitescrapertask", "django_migrations"]


@pytest.mark.parametrize("field", [
    models.UUIDField(), models.UUIDField(null=True, default=None),
    models.UUIDField(null=True, db_default=None), models.UUIDField(null=True, unique=True),
    models.UUIDField(null=True, db_index=True), models.UUIDField(null=True, db_column="other"),
    models.CharField(null=True, max_length=40),
])
def test_other_field_shapes_require_full_release(field):
    with pytest.raises(CommandError):
        scoped_plan(plan(migrations.AddField("sitescrapertask", "field", field)))


@pytest.mark.parametrize("operation", [
    migrations.RemoveField("sitescrapertask", "field"),
    migrations.AlterField("sitescrapertask", "field", models.UUIDField(null=True)),
    migrations.RunPython(migrations.RunPython.noop), migrations.RunSQL("SELECT 1"),
    migrations.AddField("medicineproduct", "field", models.UUIDField(null=True)),
])
def test_data_or_other_tables_require_full_release(operation):
    with pytest.raises(CommandError):
        scoped_plan(plan(operation))


def test_wrong_app_or_reverse_rejected():
    operation = migrations.AddField("sitescrapertask", "field", models.UUIDField(null=True))
    for candidate in [plan(operation, app="catalog"), plan(operation, backwards=True)]:
        with pytest.raises(CommandError):
            scoped_plan(candidate)
