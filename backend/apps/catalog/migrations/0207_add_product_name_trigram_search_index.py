from django.db import migrations


class Migration(migrations.Migration):
    """Accelerate case-insensitive substring search without locking writes."""

    atomic = False

    dependencies = [
        ("catalog", "0206_restore_instagram_catalog_availability"),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS pg_trgm",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                "catalog_product_upper_name_trgm_idx "
                "ON catalog_product USING gin (UPPER(name) gin_trgm_ops)"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS "
                "catalog_product_upper_name_trgm_idx"
            ),
        ),
    ]
