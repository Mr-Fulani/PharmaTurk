"""Пересобрать SEO БАДов кодом из готовых AI-логов, без модели (SEO-ядро 07.11.2026).

    manage.py rebuild_supplement_seo --ids 3958,537            # показать было/стало
    manage.py rebuild_supplement_seo --all --show 20           # все БАДы, только показ
    manage.py rebuild_supplement_seo --all --apply --backup /tmp/supp-seo-before.jsonl
    manage.py rebuild_supplement_seo --restore /tmp/supp-seo-before.jsonl

Меняются только SEO title / description / keywords (RU и EN); название (H1) не меняется. Пачки по 200,
бэкап — только SEO-поля и SEO лога (apps/ai/services/supplement_seo_refresh.py). Перед --restore текущие
значения тех же строк сохраняются в <файл>.before-restore-<время>.jsonl. Существующий файл бэкапа
не перезаписывается.
"""

import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.ai.services.supplement_seo_refresh import restore_backup, run
from apps.catalog.models import Product


class Command(BaseCommand):
    help = "SEO БАДов — заново кодом из AI-логов (без модели), с бэкапом SEO-полей."

    def add_arguments(self, parser):
        parser.add_argument("--ids", help="id товаров через запятую")
        parser.add_argument("--all", action="store_true", help="Все БАДы")
        parser.add_argument("--apply", action="store_true", help="Записать (без него — только показать)")
        parser.add_argument("--backup", help="Файл бэкапа SEO-полей (jsonl), обязателен с --apply")
        parser.add_argument("--restore", help="Вернуть SEO-поля из файла бэкапа")
        parser.add_argument("--show", type=int, default=10, help="Сколько примеров показать")

    def handle(self, *args, **options):
        if options["restore"]:
            # Своё имя у каждого снимка: повторный возврат не затирает прежний снимок.
            snapshot = f"{options['restore']}.before-restore-{timezone.now():%Y%m%d-%H%M%S-%f}.jsonl"
            restored = restore_backup(options["restore"], snapshot)
            self.stdout.write(f"Возвращено строк: {restored} из {options['restore']}; что было до возврата — {snapshot}.")
            return
        if options["apply"] and not options["backup"]:
            raise CommandError("--apply требует --backup <файл>")
        if bool(options["ids"]) == bool(options["all"]):
            raise CommandError("Нужно одно из: --ids 1,2,3 или --all")
        products = Product.objects.filter(product_type="supplements").order_by("id")
        if options["ids"]:
            products = products.filter(id__in=[int(x) for x in options["ids"].split(",") if x.strip()])
        ids = list(products.values_list("id", flat=True))
        if options["apply"]:
            # «x»: существующий бэкап не перезаписывается — в нём прежнее SEO уже записанных товаров.
            try:
                backup = open(options["backup"], "x")
            except FileExistsError:
                raise CommandError(f"Файл бэкапа уже есть: {options['backup']} — укажите новый.")
            with backup:
                stats, examples = run(ids, apply=True, backup=backup, show=options["show"])
        else:
            stats, examples = run(ids, show=options["show"])
        for plan in examples:
            self.stdout.write(f"\n{plan.product_id}")
            for change in plan.changes:
                if change.locale == "ru":
                    self.stdout.write(f"  {change.label}[ru].meta_title: {change.old['meta_title']!r}\n    → {change.new['meta_title']!r}")
                    self.stdout.write(f"  {change.label}[ru].meta_description: → {change.new['meta_description']!r}")
                    break
        self.stdout.write("\n" + json.dumps(dict(stats), ensure_ascii=False))
        if not options["apply"]:
            self.stdout.write("Только показ: для записи — --apply --backup <файл>.")
        else:
            self.stdout.write(f"Бэкап SEO-полей: {options['backup']}.")
