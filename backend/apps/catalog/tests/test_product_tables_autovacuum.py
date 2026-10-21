import pytest
from django.db import connection


# Размер таблиц на проде (октябрь 2026): от него зависят пороги autovacuum.
PROD_ROWS = {
    "catalog_product": 26_100,
    "catalog_medicineproduct": 13_000,
}


@pytest.mark.django_db
@pytest.mark.parametrize(("table", "rows"), PROD_ROWS.items())
def test_vacuum_comes_before_analyze_after_mass_update(table, rows):
    """Иначе ANALYZE видит снятую visibility map и COUNT уходит в seq scan с детоастом (0218)."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT reloptions FROM pg_class WHERE relname = %s", [table])
        options = dict(option.split("=", 1) for option in cursor.fetchone()[0] or [])
        cursor.execute("SELECT name, setting FROM pg_settings WHERE name LIKE 'autovacuum%'")
        settings = dict(cursor.fetchall())

    def threshold(kind):
        def value(name):
            return float(options.get(name, settings[name]))

        return value(f"autovacuum_{kind}_threshold") + value(f"autovacuum_{kind}_scale_factor") * rows

    analyze = threshold("analyze")
    assert threshold("vacuum") < analyze
    assert threshold("vacuum_insert") < analyze
