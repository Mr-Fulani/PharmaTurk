# Автовакуум таблиц товаров с большими external_data — сразу после массовых правок.
#
# COUNT списков (/api/catalog/products, /api/catalog/medicines/products) читается
# index-only сканом частичных индексов 0194/0208/0212 и не трогает jsonb. Такой
# скан дёшев, пока страницы таблицы отмечены «все строки видимы» в visibility
# map. Каждый UPDATE снимает отметку со своей страницы, вернуть её может только
# VACUUM. По умолчанию autovacuum ждёт 20 % мёртвых строк, а autoanalyze — 10 %
# изменённых: после массовых правок (чистка old_price, перескрейпы, AI) ANALYZE
# пересчитывал долю видимых страниц, а VACUUM так и не запускался (у лекарств
# ≈ 2000 мёртвых строк при пороге 2657). Планировщик считал index-only скан
# дорогим и уходил в seq scan, проверяя external_data ? 'is_stub' на каждой
# строке, то есть детоастя 394 МБ TOAST (прод 20–21.10: COUNT лекарств 12,8 с
# вместо 4 мс, лечилось только ручным VACUUM). План ломается уже при < 75 %
# видимых страниц — это ≈ 550 правленых лекарств (замер на копии таблицы).
#
# 1 % ставит VACUUM раньше ANALYZE: у лекарств 180 мёртвых строк против 1353
# изменений, у Product — 311 против 2660; вставки — 1130/1261 против тех же
# порогов ANALYZE. TOAST-таблицы без своих toast.* берут эти же значения.
# Повторный VACUUM дешёвый: страницы, уже отмеченные видимыми, он пропускает.

from django.db import migrations


TABLES = ("catalog_product", "catalog_medicineproduct")

OPTIONS = (
    "autovacuum_vacuum_scale_factor = 0.01, "
    "autovacuum_vacuum_insert_scale_factor = 0.01"
)

RESET_OPTIONS = "autovacuum_vacuum_scale_factor, autovacuum_vacuum_insert_scale_factor"


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0217_brand_storefront_nonpublic_indexes"),
    ]

    operations = [
        migrations.RunSQL(
            f"ALTER TABLE {table} SET ({OPTIONS});",
            reverse_sql=f"ALTER TABLE {table} RESET ({RESET_OPTIONS});",
        )
        for table in TABLES
    ]
