# Частичные индексы под базовые exclude-фильтры каталога.
#
# Условия вида external_data ? 'is_stub' заставляют Postgres детоастить
# огромные jsonb парсеров на каждой строке (~275 МБ чтения на запрос):
# COUNT списка медикаментов — 1.4 с, DISTINCT гендер-фасетов — 1.8-1.9 с.
# Частичный индекс, предикат которого текстуально совпадает с фильтром ORM,
# даёт index-only scan без чтения jsonb (замер на проде: 1404 мс → 2.7 мс,
# 1793 мс → 1.9 мс, 1703 мс → 12 мс).
#
# SQL написан вручную: предикат обязан совпадать с SQL, который генерирует
# ORM из exclude(...) в ProductViewSet.queryset и MedicineProductViewSet.
# _base_queryset — иначе планировщик не докажет импликацию и не возьмёт индекс.

from django.db import migrations


CREATE_PRODUCT_IDX = """
CREATE INDEX IF NOT EXISTS catalog_product_catalog_facets_idx
ON catalog_product (category_id, gender, product_type)
WHERE is_active
  AND NOT (external_data ? 'source_variant_id' OR external_data ? 'source_variant_slug')
  AND NOT (product_type = 'medicines' AND external_data ? 'is_stub' AND (external_data -> 'is_stub') = 'true'::jsonb);
"""
DROP_PRODUCT_IDX = "DROP INDEX IF EXISTS catalog_product_catalog_facets_idx;"

CREATE_MEDICINE_IDX = """
CREATE INDEX IF NOT EXISTS catalog_medicine_nonstub_cat_created_idx
ON catalog_medicineproduct (category_id, created_at DESC)
WHERE is_active
  AND NOT (external_data ? 'is_stub' AND (external_data -> 'is_stub') = 'true'::jsonb);
"""
DROP_MEDICINE_IDX = "DROP INDEX IF EXISTS catalog_medicine_nonstub_cat_created_idx;"


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0193_alter_jewelry_image_url_blank"),
    ]

    operations = [
        migrations.RunSQL(CREATE_PRODUCT_IDX, reverse_sql=DROP_PRODUCT_IDX),
        migrations.RunSQL(CREATE_MEDICINE_IDX, reverse_sql=DROP_MEDICINE_IDX),
    ]
