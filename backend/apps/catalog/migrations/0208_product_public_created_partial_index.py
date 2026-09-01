# Ordered and brand-scoped partial indexes for public Product rows.
#
# 0194 made COUNT/facet queries index-only, but the product SELECT still used a
# parallel sequential scan because the index did not provide created_at order.
# Evaluating the public visibility predicate detoasts external_data for every
# Product row (~0.8-3.3 s on production even with LIMIT 12).  This index keeps
# the same predicate and lets PostgreSQL walk already-public rows in display
# order until it has the requested page.  The UI's default client-side order is
# name_asc, so the same public projection is provided for name in both scan
# directions.  category_id/product_type are part of each ordered index so the
# category predicate can be checked from the index before fetching heap rows.
#
# BrandSerializer also exposes an exact products_count in product detail and
# resolve payloads.  The existing plain brand_id index still has to detoast
# external_data to discard shadow/stub rows (2.45 s on the measured product).
# A brand partial index preserves the exact API contract while making that
# count index-only.

from django.db import migrations


CREATE_INDEX = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_product_public_created_idx
ON catalog_product (created_at DESC, category_id, product_type)
WHERE is_active
  AND NOT (external_data ? 'source_variant_id' OR external_data ? 'source_variant_slug')
  AND NOT (product_type = 'medicines' AND external_data ? 'is_stub' AND (external_data -> 'is_stub') = 'true'::jsonb);
"""

CREATE_NAME_INDEX = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_product_public_name_idx
ON catalog_product (name, category_id, product_type)
WHERE is_active
  AND NOT (external_data ? 'source_variant_id' OR external_data ? 'source_variant_slug')
  AND NOT (product_type = 'medicines' AND external_data ? 'is_stub' AND (external_data -> 'is_stub') = 'true'::jsonb);
"""

CREATE_BRAND_INDEX = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_product_public_brand_available_idx
ON catalog_product (brand_id)
WHERE is_active
  AND is_available
  AND NOT (external_data ? 'source_variant_id' OR external_data ? 'source_variant_slug')
  AND NOT (product_type = 'medicines' AND external_data ? 'is_stub' AND (external_data -> 'is_stub') = 'true'::jsonb);
"""

DROP_CREATED_INDEX = """
DROP INDEX CONCURRENTLY IF EXISTS catalog_product_public_created_idx;
"""

DROP_NAME_INDEX = """
DROP INDEX CONCURRENTLY IF EXISTS catalog_product_public_name_idx;
"""

DROP_BRAND_INDEX = """
DROP INDEX CONCURRENTLY IF EXISTS catalog_product_public_brand_available_idx;
"""


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("catalog", "0207_add_product_name_trigram_search_index"),
    ]

    operations = [
        migrations.RunSQL(CREATE_INDEX, reverse_sql=DROP_CREATED_INDEX),
        migrations.RunSQL(CREATE_NAME_INDEX, reverse_sql=DROP_NAME_INDEX),
        migrations.RunSQL(CREATE_BRAND_INDEX, reverse_sql=DROP_BRAND_INDEX),
    ]
