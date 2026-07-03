# Второй частичный индекс для списка медикаментов: ORDER BY created_at LIMIT N.
#
# Индекс (category_id, created_at) из 0194 закрывает COUNT, но не даёт
# глобального порядка по created_at — планировщик брал seq scan и детоастил
# jsonb в WHERE (~790 мс). Упорядоченный скан по этому индексу отдаёт первые
# 12 строк за доли мс (замер на проде: 790 мс → 0.45 мс).
# Предикат обязан текстуально совпадать с фильтром ORM (см. 0194).

from django.db import migrations


CREATE_IDX = """
CREATE INDEX IF NOT EXISTS catalog_medicine_nonstub_created2_idx
ON catalog_medicineproduct (created_at DESC)
WHERE is_active
  AND NOT (external_data ? 'is_stub' AND (external_data -> 'is_stub') = 'true'::jsonb);
"""
DROP_IDX = "DROP INDEX IF EXISTS catalog_medicine_nonstub_created2_idx;"


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0194_nonstub_partial_indexes"),
    ]

    operations = [
        migrations.RunSQL(CREATE_IDX, reverse_sql=DROP_IDX),
    ]
