"""Пересчёт текста товаров для поиска на сайте (docs/PRODUCT_SEARCH.md). По умолчанию только показ.

    manage.py rebuild_product_search_index                    # сколько строк новых/изменится, примеры
    manage.py rebuild_product_search_index --apply            # записать
    manage.py rebuild_product_search_index --ids 12,345 --apply
    manage.py rebuild_product_search_index --clear --apply    # откат: очистить, поиск снова по названию

Пока таблица пуста, сайт ищет по-старому (по названию). Первое заполнение идёт
одной транзакцией: новый поиск включается сразу для всех товаров. Повторные
прогоны пишут пачками по --batch-size. Сеть не нужна, OpenAI не вызывается.
"""
import time
from contextlib import nullcontext

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models_search import ProductSearchIndex
from apps.catalog.product_search import iter_search_rows, search_index_ready, write_search_rows


class Command(BaseCommand):
    help = "Пересчитывает ProductSearchIndex (поиск товаров). Без --apply только показывает."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Записать (иначе только показ).")
        parser.add_argument("--ids", default="", help="ID товаров через запятую (по умолчанию все).")
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--sample", type=int, default=5, help="Сколько изменений показать.")
        parser.add_argument("--clear", action="store_true", help="Очистить индекс (откат к поиску по названию).")

    def handle(self, *args, **options):
        if options["clear"]:
            return self._clear(options["apply"])

        ids = None
        if options["ids"]:
            try:
                ids = [int(part) for part in options["ids"].split(",") if part.strip()]
            except ValueError as exc:
                raise CommandError("--ids: только числа через запятую") from exc

        first_fill = not search_index_ready()
        started = time.monotonic()
        existing = {
            row[0]: row[1:]
            for row in ProductSearchIndex.objects.values_list("product_id", "name", "brand", "text").iterator()
        }
        created = changed = same = 0
        samples = []
        pending = []
        written = 0

        def flush():
            nonlocal written
            if pending and options["apply"]:
                with transaction.atomic():
                    written += write_search_rows(pending)
            pending.clear()

        with transaction.atomic() if (options["apply"] and first_fill) else nullcontext():
            for pk, fields in iter_search_rows(ids, batch_size=options["batch_size"]):
                old = existing.get(pk)
                new = (fields["name"], fields["brand"], fields["text"])
                if old == new:
                    same += 1
                    continue
                if old is None:
                    created += 1
                else:
                    changed += 1
                if len(samples) < options["sample"]:
                    samples.append((pk, old[2] if old else "", fields["text"]))
                pending.append((pk, fields))
                if len(pending) >= options["batch_size"]:
                    flush()
            flush()

        elapsed = time.monotonic() - started
        self.stdout.write(
            f"Товаров: {created + changed + same}; новых строк: {created}, изменится: {changed}, "
            f"без изменений: {same}; {elapsed:.1f} с"
        )
        for pk, old_text, new_text in samples:
            self.stdout.write(f"  #{pk}: {old_text[:120]!r} → {new_text[:200]!r}")
        if options["apply"]:
            mode = "одной транзакцией (первое заполнение)" if first_fill else "пачками"
            self.stdout.write(self.style.SUCCESS(f"Записано строк: {written}, {mode}."))
        else:
            self.stdout.write("Показ. Для записи — --apply.")

    def _clear(self, apply):
        count = ProductSearchIndex.objects.count()
        if not apply:
            self.stdout.write(f"Строк в индексе: {count}. Очистка — --clear --apply (поиск вернётся к названию).")
            return
        ProductSearchIndex.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f"Удалено строк: {count}. Поиск снова идёт по названию."))
