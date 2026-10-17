# Частичный индекс под порядок «Популярные» списка БАДов (см. 0212 для
# медикаментов). У БАДов нет stub-исключения, поэтому предикат — только
# is_active, как в SupplementProductViewSet.queryset.

from django.db import migrations


CREATE_INDEX = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_supplement_active_rank_idx
ON catalog_supplementproduct (sort_rank DESC, id DESC, category_id)
WHERE is_active;
"""

DROP_INDEX = "DROP INDEX CONCURRENTLY IF EXISTS catalog_supplement_active_rank_idx;"


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("catalog", "0213_supplement_sort_rank"),
    ]

    operations = [
        migrations.RunSQL(CREATE_INDEX, reverse_sql=DROP_INDEX),
    ]
