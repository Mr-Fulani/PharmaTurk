"""Выравнивает sequence catalog_globalattributekey после 0128.

0128 копировал ServiceAttributeKey → GlobalAttributeKey с явными id
(get_or_create(id=...)), что не двигает sequence PostgreSQL. На свежей БД
(тесты, новое развёртывание) первый же objects.create() получал занятый id
и падал с duplicate pkey. Идемпотентно: setval на MAX(id).
"""

from django.db import migrations


def fix_sequence(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT setval(pg_get_serial_sequence('catalog_globalattributekey', 'id'), "
            "GREATEST((SELECT COALESCE(MAX(id), 0) FROM catalog_globalattributekey), 1))"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0185_dedup_doubled_slugs"),
    ]

    operations = [
        migrations.RunPython(fix_sequence, migrations.RunPython.noop),
    ]
