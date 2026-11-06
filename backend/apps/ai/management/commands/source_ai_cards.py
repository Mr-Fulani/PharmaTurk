"""Русские карточки новых товаров одного источника: правила + Claude, черновиками.

    manage.py source_ai_cards --source superstep                          # показать: сколько новых
    manage.py source_ai_cards --source superstep --run --limit 500        # черновики, товары не меняются
    manage.py source_ai_cards --source superstep --report --since 2026-11-06
    manage.py source_ai_cards --source superstep --apply --backup ~/backups/ss-rows.json.gz

Черновик — обычный лог AI (полная обработка без применения): название, SEO и атрибуты
собирают правила (apps/ai/services/rules), описание пишет модель и кладёт в память
переводов — повторный такой же текст следующих партий берётся из памяти бесплатно.
Применяются только «Завершено» (модерация остаётся людям); цену, валюту, бренд и раздел
применение не меняет (раздел — только у товара без раздела). Порядок — docs/AI_RUNS_ADMIN_GUIDE.md.
"""

import gzip
import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.db.models import Sum

from apps.ai.models import AIModerationQueue, AIProcessingLog, AIProcessingStatus
from apps.ai.services.bulk_ops import select_products_for_ai
from apps.ai.services.content_generator import ContentGenerator
from apps.catalog.models import Product

MAX_WORKERS = 6
BACKUP_RELATIONS = ("translations", "dynamic_attributes", "sizes")


class Command(BaseCommand):
    help = "Новые товары источника — через правила и Claude: черновики, отчёт, применение с бэкапом строк."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True, help="Префикс external_id, например superstep")
        parser.add_argument("--ids", help="Только эти id товаров (через запятую)")
        parser.add_argument("--limit", type=int, default=500, help="Сколько товаров за запуск --run")
        parser.add_argument("--workers", type=int, default=4, help=f"Параллельных запросов (до {MAX_WORKERS})")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--run", action="store_true", help="Сделать черновики (товары не меняются)")
        mode.add_argument("--report", action="store_true", help="Итог по логам источника")
        mode.add_argument("--apply", action="store_true", help="Применить черновики «Завершено» (нужен --backup)")
        parser.add_argument("--backup", help="Файл бэкапа строк перед применением (.json или .json.gz)")
        parser.add_argument("--since", help="Для --report и --apply: логи с этой даты (ГГГГ-ММ-ДД)")

    def handle(self, *args, **options):
        prefix = f"{options['source'].strip().rstrip('-')}-"
        products = Product.objects.filter(external_id__startswith=prefix)
        if options["ids"]:
            products = products.filter(id__in=[int(x) for x in options["ids"].split(",") if x.strip()])
        if options["apply"]:
            if not options["backup"]:
                raise CommandError("--apply требует --backup <файл>")
            self._apply(products, options)
        elif options["report"]:
            self._report(self._logs(products, options))
        else:
            self._run(products, options)

    def _logs(self, products, options):
        logs = AIProcessingLog.objects.filter(product__in=products, processing_type="full")
        if options["since"]:
            logs = logs.filter(created_at__date__gte=datetime.strptime(options["since"], "%Y-%m-%d").date())
        return logs

    def _run(self, products, options):
        candidates = select_products_for_ai(ids=list(products.values_list("id", flat=True)))
        ids = list(candidates.values_list("id", flat=True)[: options["limit"]])
        by_type = Counter(candidates.values_list("product_type", flat=True))
        self.stdout.write(f"Без русской карточки: {candidates.count()} {dict(by_type)}; к обработке: {len(ids)}")
        if not options["run"] or not ids:
            self.stdout.write("Только показ: черновики — --run." if ids else "Новых товаров нет.")
            return
        workers = max(1, min(options["workers"], MAX_WORKERS))
        local = threading.local()

        def process(product_id):
            try:
                if not hasattr(local, "generator"):
                    local.generator = ContentGenerator()
                log = local.generator.process_product(product_id, processing_type="full", auto_apply=False)
                return product_id, log.pk, log.status
            except Exception as exc:  # ошибка одного товара не останавливает партию
                return product_id, None, f"error: {exc}"[:200]
            finally:
                if workers > 1:
                    close_old_connections()  # у каждого потока своё соединение с БД

        log_ids, statuses = [], Counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = pool.map(process, ids) if workers > 1 else map(process, ids)
            for done, (product_id, log_id, status) in enumerate(results, start=1):
                statuses[status if log_id else "error"] += 1
                if log_id:
                    log_ids.append(log_id)
                else:
                    self.stdout.write(f"  {product_id}: {status}")
                if done % 50 == 0:
                    self.stdout.write(f"  готово {done}/{len(ids)}: {dict(statuses)}")
        self._report(AIProcessingLog.objects.filter(id__in=log_ids))

    def _report(self, logs):
        sources, titles = Counter(), Counter()
        for raw in logs.values_list("raw_llm_response", flat=True):
            rule = (raw or {}).get("rule_content") if isinstance(raw, dict) else None
            if not isinstance(rule, dict):
                sources["без правил"] += 1
                continue
            sources[rule.get("description_source") or "?"] += 1
            titles.update(f"{locale}:{source}" for locale, source in (rule.get("title_sources") or {}).items())
        reasons = Counter(
            AIModerationQueue.objects.filter(log_entry__in=logs, resolved_at__isnull=True).values_list("reason", flat=True)
        )
        cost = logs.aggregate(total=Sum("cost_usd"))["total"] or 0
        self.stdout.write(json.dumps({
            "логов": logs.count(),
            "статусы": dict(Counter(logs.values_list("status", flat=True))),
            "описание": dict(sources),  # memory — из памяти, llm — новый перевод, template — из фактов
            "название": dict(titles),  # rules — правила, llm — модель
            "модерация": dict(reasons),
            "стоимость_usd": float(cost),
        }, ensure_ascii=False))

    def _apply(self, products, options):
        logs = list(
            self._logs(products, options)
            .filter(status=AIProcessingStatus.COMPLETED)
            .select_related("product")
            .order_by("product_id", "-id")
            .distinct("product_id")
        )
        if not logs:
            self.stdout.write("Нет черновиков «Завершено».")
            return
        rows = []
        for log in logs:
            for obj in {id(o): o for o in (log.product, log.product.domain_item) if o is not None}.values():
                rows.append(obj)
                for relation in BACKUP_RELATIONS:
                    manager = getattr(obj, relation, None)
                    if manager is not None and hasattr(manager, "all"):
                        rows.extend(manager.all())
        opener = gzip.open if options["backup"].endswith(".gz") else open
        with opener(options["backup"], "wt", encoding="utf-8") as handle:
            handle.write(serializers.serialize("json", rows))
        self.stdout.write(f"Бэкап: {options['backup']} ({len(rows)} строк, {len(logs)} товаров)")
        generator = ContentGenerator()
        result = Counter()
        for log in logs:
            try:
                applied = generator.apply_log_to_product(log)
                result[applied.application_status or applied.status] += 1
            except Exception as exc:
                result["error"] += 1
                self.stdout.write(f"  {log.product_id} (лог {log.pk}): {exc}")
        self.stdout.write(f"Применено: {dict(result)}")
