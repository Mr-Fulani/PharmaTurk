"""Правка сохранённых переводов описаний товаров теми же правилами, что и новых (rules/polish.py).

    manage.py polish_product_memory                                       # только показать
    manage.py polish_product_memory --apply --backup /backups/pdmem-before.json
    manage.py polish_product_memory --restore /backups/pdmem-before.json   # вернуть как было

Необязательная команда. Описание из памяти и так правится при каждом чтении (pipeline), а с
06.11.2026 в память пишется ответ модели как есть. Команда нужна, чтобы сами записи в админке
(«Память переводов») и в выгрузках были без «Ергономичная», висящих хвостов «нейтрален и.»,
«воды» и турецких оригиналов в скобках. Запись, у которой после правки не остаётся текста, не меняется.
"""

import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.ai.models import AITranslationMemory
from apps.ai.services.rules.memory import NAMESPACE_PREFIX
from apps.ai.services.rules.polish import polish_description


class Command(BaseCommand):
    help = "Переводы описаний товаров в памяти — через правку rules/polish (показ; запись с --apply --backup)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Записать (без него — только показать)")
        parser.add_argument("--backup", help="Новый файл бэкапа строк перед записью (обязателен с --apply)")
        parser.add_argument("--show", type=int, default=10, help="Сколько примеров показать")
        parser.add_argument("--restore", metavar="BACKUP", help="Вернуть записи из бэкапа --apply")

    def handle(self, *args, **options):
        if options["restore"]:
            with open(options["restore"], encoding="utf-8") as handle:
                saved = json.load(handle)
            with transaction.atomic():
                for item in saved:
                    AITranslationMemory.objects.filter(pk=item["pk"]).update(ru_text=item["ru_text"], en_text=item["en_text"])
            self.stdout.write(f"Восстановлено записей: {len(saved)}")
            return
        if options["apply"] and not options["backup"]:
            raise CommandError("--apply требует --backup <файл>")
        rows = AITranslationMemory.objects.filter(namespace__startswith=f"{NAMESPACE_PREFIX}:").only(
            "pk", "ru_text", "en_text"
        )
        stats, changed = Counter(), []
        for row in rows.iterator(chunk_size=500):
            stats["записей"] += 1
            ru, en = polish_description(row.ru_text, "ru"), polish_description(row.en_text, "en")
            if (ru, en) == (row.ru_text, row.en_text):
                continue
            if (row.ru_text and not ru) or (row.en_text and not en):
                stats["пустые после правки — не меняются"] += 1
                continue
            stats["к изменению"] += 1
            changed.append((row, ru, en))
        for row, ru, _en in changed[: options["show"]]:
            self.stdout.write(f"\n{row.pk}: {row.ru_text[:160]!r}\n   → {ru[:160]!r}")
        self.stdout.write("\n" + json.dumps(dict(stats), ensure_ascii=False))
        if not options["apply"]:
            self.stdout.write("Только показ: для записи — --apply --backup <файл>.")
            return
        with open(options["backup"], "x", encoding="utf-8") as handle:  # чужой бэкап не затирается
            json.dump([{"pk": row.pk, "ru_text": row.ru_text, "en_text": row.en_text} for row, _ru, _en in changed], handle, ensure_ascii=False)
        with transaction.atomic():
            for row, ru, en in changed:
                row.ru_text, row.en_text = ru, en
            AITranslationMemory.objects.bulk_update([row for row, _ru, _en in changed], ["ru_text", "en_text"], batch_size=500)
        self.stdout.write(f"Записано: {len(changed)}, бэкап: {options['backup']}")
