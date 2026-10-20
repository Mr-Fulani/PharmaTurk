"""Аудит памяти абзацев инструкций лекарств: сдвинутые и чужие переводы.

Пакетный перевод иногда сдвигает ответы модели: абзацу достаётся перевод
соседнего («5. X'İN SAKLANMASI» → «Храните при комнатной температуре ниже
25°C»). Команда проверяет все записи ``medicine_paragraph`` правилами
``medicine_paragraph_check`` без LLM: правила абзаца (номер заголовка, числа,
длина, RU≠EN, понятия, частота) и сдвиг относительно соседних записей (записи
одного запроса стоят в памяти подряд).

    manage.py medicine_paragraph_audit --dry-run
    manage.py medicine_paragraph_audit --dry-run --report /tmp/paragraph_audit.jsonl
    manage.py medicine_paragraph_audit --backup /tmp/paragraph_audit_backup.json

Без ``--dry-run`` подозрительные записи сначала выгружаются в ``--backup``
(формат ``loaddata``), затем переносятся в namespace
``medicine_paragraph_suspect``: память их больше не находит, и абзац
переведётся заново при следующей обработке товара или
``medicine_paragraph_batch submit``. Строки остаются в БД и видны в админке.
Откат: ``manage.py loaddata <backup>``. Записи, исправленные вручную
(``updated_at`` позже ``created_at``), не трогаются.
"""

import json
import random
from collections import Counter
from datetime import timedelta

from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.ai.models import AITranslationMemory
from apps.ai.services.medicine_memory import PARAGRAPH_NAMESPACE
from apps.ai.services.medicine_paragraph_check import audit_sequence

SUSPECT_NAMESPACE = f"{PARAGRAPH_NAMESPACE}_suspect"
# Запись памяти создаётся bulk_create, hits меняет .update(): updated_at сдвигает только save() из админки.
MANUAL_EDIT_GAP = timedelta(minutes=1)
CHUNK_SIZE = 2000
MOVE_BATCH_SIZE = 500


class Command(BaseCommand):
    help = "Поиск сдвинутых переводов в памяти абзацев инструкций лекарств (--dry-run — только отчёт)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Только отчёт, без изменений")
        parser.add_argument("--backup", default="", help="Файл бэкапа затронутых строк (нужен без --dry-run)")
        parser.add_argument("--report", default="", help="JSONL со всеми подозрительными записями")
        parser.add_argument("--examples", type=int, default=10, help="Сколько примеров напечатать")

    def handle(self, *args, **options):
        if not options["dry_run"] and not options["backup"]:
            raise CommandError("Без --dry-run нужен --backup <файл>: затронутые строки сохраняются до изменения")
        pks, edited, reasons = self._scan()
        flagged = [pk for pk, row_reasons in zip(pks, reasons) if row_reasons and pk not in edited]
        by_pk = dict(zip(pks, reasons))
        self._summary(len(pks), flagged, edited, by_pk)
        self._examples(flagged, by_pk, options["examples"])
        if options["report"]:
            self._write_report(flagged, by_pk, options["report"])
        if options["dry_run"] or not flagged:
            return
        self._write_backup(flagged, options["backup"])
        moved = self._quarantine(flagged)
        self.stdout.write(self.style.SUCCESS(
            f"Перенесено в {SUSPECT_NAMESPACE}: {moved}. Бэкап: {options['backup']} "
            f"(откат: manage.py loaddata {options['backup']}). Абзацы переведутся заново при следующей обработке."
        ))

    def _scan(self):
        pks: list[int] = []
        edited: set[int] = set()
        qs = (
            AITranslationMemory.objects.filter(namespace=PARAGRAPH_NAMESPACE)
            .order_by("pk")
            .values_list("pk", "source_text", "ru_text", "en_text", "created_at", "updated_at")
        )

        def rows():
            for pk, source, ru, en, created_at, updated_at in qs.iterator(chunk_size=CHUNK_SIZE):
                pks.append(pk)
                if updated_at - created_at > MANUAL_EDIT_GAP:
                    edited.add(pk)
                if len(pks) % 50000 == 0:
                    self.stdout.write(f"проверено записей: {len(pks)}")
                    self.stdout.flush()
                yield source, ru, en

        reasons = audit_sequence(rows())
        return pks, edited, reasons

    def _summary(self, total, flagged, edited, by_pk):
        counts = Counter(reason for pk in flagged for reason in by_pk[pk])
        only_shifted = sum(1 for pk in flagged if by_pk[pk] == ["shifted"])
        skipped = sum(1 for pk in edited if by_pk[pk])
        share = f" ({len(flagged) / total:.1%})" if total else ""
        self.stdout.write(f"Записей {PARAGRAPH_NAMESPACE}: {total}; подозрительных: {len(flagged)}{share}")
        for reason, count in counts.most_common():
            self.stdout.write(f"  {reason}: {count}")
        self.stdout.write(f"  только сдвиг по соседям (shifted): {only_shifted}")
        if skipped:
            self.stdout.write(f"Исправлены вручную и не трогаются: {skipped}")

    def _rows(self, pks):
        """Записи по списку pk порциями (один IN на 65 тыс. параметров Postgres не примет)."""
        for start in range(0, len(pks), CHUNK_SIZE):
            yield from AITranslationMemory.objects.filter(pk__in=pks[start:start + CHUNK_SIZE]).order_by("pk")

    def _examples(self, flagged, by_pk, limit):
        sample = sorted(random.Random(0).sample(flagged, min(limit, len(flagged))))
        for entry in self._rows(sample):
            self.stdout.write(
                f"pk={entry.pk} {','.join(by_pk[entry.pk])}\n"
                f"  TR: {entry.source_text[:150]}\n  RU: {entry.ru_text[:150]}\n  EN: {entry.en_text[:150]}"
            )

    def _write_report(self, flagged, by_pk, path):
        with open(path, "w", encoding="utf-8") as report:
            for entry in self._rows(flagged):
                report.write(json.dumps({
                    "pk": entry.pk,
                    "source_hash": entry.source_hash,
                    "reasons": by_pk[entry.pk],
                    "hits": entry.hits,
                    "source_text": entry.source_text,
                    "ru_text": entry.ru_text,
                    "en_text": entry.en_text,
                }, ensure_ascii=False) + "\n")
        self.stdout.write(f"Отчёт: {path} ({len(flagged)} строк)")

    def _backup_rows(self, flagged):
        """Затронутые строки и их копии от прошлого аудита — их заменит перенос."""
        for start in range(0, len(flagged), CHUNK_SIZE):
            rows = list(AITranslationMemory.objects.filter(pk__in=flagged[start:start + CHUNK_SIZE]).order_by("pk"))
            yield from rows
            yield from AITranslationMemory.objects.filter(
                namespace=SUSPECT_NAMESPACE, source_hash__in=[row.source_hash for row in rows]
            )

    def _write_backup(self, flagged, path):
        with open(path, "w", encoding="utf-8") as backup:
            serializers.serialize("json", self._backup_rows(flagged), stream=backup)
        self.stdout.write(f"Бэкап {len(flagged)} строк: {path}")

    def _quarantine(self, flagged) -> int:
        moved = 0
        for start in range(0, len(flagged), MOVE_BATCH_SIZE):
            chunk = flagged[start:start + MOVE_BATCH_SIZE]
            with transaction.atomic():
                rows = AITranslationMemory.objects.filter(pk__in=chunk, namespace=PARAGRAPH_NAMESPACE)
                hashes = list(rows.values_list("source_hash", flat=True))
                # Копия того же абзаца от прошлого аудита: уникальность (namespace, source_hash).
                AITranslationMemory.objects.filter(namespace=SUSPECT_NAMESPACE, source_hash__in=hashes).delete()
                moved += rows.update(namespace=SUSPECT_NAMESPACE)
        return moved
