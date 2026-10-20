# Partial indexes of non-public rows for the brand storefront.
#
# /api/catalog/brands/<slug>/products and /categories filter every domain table
# by brand and drop service rows: domain copies of source variants and rows
# whose shadow Product is a variant or a medicine stub.  As plain conditions on
# external_data, PostgreSQL evaluated `?` on every row of the table before
# brand_id and detoasted the multi-MB parser dumps (production: TEB medicines
# 3.7 s, IKEA furniture 1.2 s per query; the same again for /categories).
#
# BrandViewSet now excludes these rows with `id NOT IN (subquery)`.  Each
# subquery reads one of the tiny indexes below (941 of 26k Product rows, almost
# no domain rows), and the main query no longer touches external_data at all.
# The predicates must stay textually identical to source_variant_q() and
# non_public_shadow_product_q() (apps/catalog/querysets.py), otherwise the
# planner cannot prove them and falls back to a detoasting seq scan.

from django.db import migrations


DOMAIN_TABLES = (
    "catalog_clothingproduct",
    "catalog_shoeproduct",
    "catalog_electronicsproduct",
    "catalog_furnitureproduct",
    "catalog_jewelryproduct",
    "catalog_bookproduct",
    "catalog_perfumeryproduct",
    "catalog_medicineproduct",
    "catalog_supplementproduct",
    "catalog_medicalequipmentproduct",
    "catalog_tablewareproduct",
    "catalog_accessoryproduct",
    "catalog_incenseproduct",
    "catalog_sportsproduct",
    "catalog_autopartproduct",
    "catalog_headwearproduct",
    "catalog_underwearproduct",
    "catalog_islamicclothingproduct",
)

SOURCE_VARIANT_PREDICATE = (
    "(external_data ? 'source_variant_id' OR external_data ? 'source_variant_slug')"
)

CREATE_PRODUCT_INDEX = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_product_nonpublic_id_idx
ON catalog_product (id)
WHERE (external_data ? 'source_variant_id'
  OR external_data ? 'source_variant_slug'
  OR (product_type = 'medicines' AND external_data ? 'is_stub' AND (external_data -> 'is_stub') = 'true'::jsonb));
"""

DROP_PRODUCT_INDEX = """
DROP INDEX CONCURRENTLY IF EXISTS catalog_product_nonpublic_id_idx;
"""


def _domain_index_name(table: str) -> str:
    return f"{table}_source_variant_idx"


def _create_domain_index(table: str) -> str:
    return (
        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_domain_index_name(table)} "
        f"ON {table} (id) WHERE {SOURCE_VARIANT_PREDICATE};"
    )


def _drop_domain_index(table: str) -> str:
    return f"DROP INDEX CONCURRENTLY IF EXISTS {_domain_index_name(table)};"


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("catalog", "0216_banner_how_to_order_position"),
    ]

    operations = [
        migrations.RunSQL(CREATE_PRODUCT_INDEX, reverse_sql=DROP_PRODUCT_INDEX),
        *(
            migrations.RunSQL(_create_domain_index(table), reverse_sql=_drop_domain_index(table))
            for table in DOMAIN_TABLES
        ),
    ]
