# Частичные индексы под сортировки списка медикаментов.
#
# Каждый ORDER BY из MedicineProductViewSet._ORDERING_MAP должен читаться
# упорядоченным сканом индекса: без него Postgres проверяет stub-предикат по
# всей таблице и детоастит многомегабайтный external_data (см. 0194/0195/0209).
# Колонки индекса совпадают с ORDER BY, включая последний ключ id; category_id —
# в хвосте, чтобы фильтр категории проверялся по индексу до чтения строк.
# name_desc читается обратным сканом name-индекса. Для цены нужны два индекса:
# NULLS LAST в обе стороны обратным сканом не получить.
# Предикат обязан текстуально совпадать с MedicineProductViewSet._base_queryset.
#
# Индекс 0209 (name, category_id) заменяется: ORDER BY name, id он не покрывает.

from django.db import migrations


PREDICATE = """
WHERE is_active
  AND NOT (external_data ? 'is_stub' AND (external_data -> 'is_stub') = 'true'::jsonb)
"""

INDEXES = {
    "catalog_medicine_nonstub_rank_idx": "(sort_rank DESC, id DESC, category_id)",
    "catalog_medicine_nonstub_name_id_idx": "(name, id, category_id)",
    "catalog_medicine_nonstub_price_asc_idx": "(price ASC NULLS LAST, id, category_id)",
    "catalog_medicine_nonstub_price_desc_idx": "(price DESC NULLS LAST, id DESC, category_id)",
}

OLD_NAME_INDEX = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_medicine_nonstub_name_idx
ON catalog_medicineproduct (name, category_id)
""" + PREDICATE


def _create(name, columns):
    return f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON catalog_medicineproduct {columns}" + PREDICATE


def _drop(name):
    return f"DROP INDEX CONCURRENTLY IF EXISTS {name};"


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("catalog", "0211_medicine_sort_rank"),
    ]

    operations = [
        *[
            migrations.RunSQL(_create(name, columns), reverse_sql=_drop(name))
            for name, columns in INDEXES.items()
        ],
        migrations.RunSQL(
            _drop("catalog_medicine_nonstub_name_idx"),
            reverse_sql=OLD_NAME_INDEX,
        ),
    ]
