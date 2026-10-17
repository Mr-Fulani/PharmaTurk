# Name-ordered partial index for public medicine cards.
#
# The category page SSR and its client refetch ask for ordering=name_asc.
# 0194/0195 cover the stub predicate only in created_at order, so the name
# order still scanned every MedicineProduct row and detoasted its multi-MB
# external_data to evaluate the stub exclusion before a top-N sort (synthetic
# 12.5k rows: 1.2 s cold / 0.19 s warm → 0.08 s / 1 ms).  The predicate must
# stay textually identical to MedicineProductViewSet._base_queryset so the
# planner can prove it; category_id lets the category scope be checked from the
# index before fetching heap rows.  B-tree serves name_desc by a backward scan.

from django.db import migrations


CREATE_INDEX = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_medicine_nonstub_name_idx
ON catalog_medicineproduct (name, category_id)
WHERE is_active
  AND NOT (external_data ? 'is_stub' AND (external_data -> 'is_stub') = 'true'::jsonb);
"""

DROP_INDEX = """
DROP INDEX CONCURRENTLY IF EXISTS catalog_medicine_nonstub_name_idx;
"""


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("catalog", "0208_product_public_created_partial_index"),
    ]

    operations = [
        migrations.RunSQL(CREATE_INDEX, reverse_sql=DROP_INDEX),
    ]
