"""
Migration 0163: Синхронизация max_length image_file/main_image_file 100 → 500.

БД уже обновлена напрямую через ALTER TABLE (2026-04-02).
Эта миграция — «маркер»: помечает изменение как применённое в истории Django
без повторного выполнения SQL.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0162_bannertranslation_bannermediatranslation"),
    ]

    operations = [
        # БД уже обновлена вручную:
        # DO $$ DECLARE r RECORD; BEGIN
        #   FOR r IN SELECT table_name, column_name FROM information_schema.columns
        #     WHERE column_name IN ('image_file','main_image_file')
        #       AND character_maximum_length=100 AND table_schema='public'
        #   LOOP
        #     EXECUTE format('ALTER TABLE %I ALTER COLUMN %I TYPE varchar(500)', r.table_name, r.column_name);
        #   END LOOP;
        # END; $$;
        #
        # Выполняем SELECT 1 чтобы зафиксировать миграцию в django_migrations таблице
        # без побочных эффектов. Модели будут обновлены отдельным коммитом.
        migrations.RunSQL(
            sql="SELECT 1",
            reverse_sql="SELECT 1",
        ),
    ]
