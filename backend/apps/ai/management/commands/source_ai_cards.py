"""Русские карточки новых товаров одного источника: правила + Claude, черновиками.

    manage.py source_ai_cards --source superstep                          # показать: сколько новых
    manage.py source_ai_cards --source superstep --run --limit 500        # черновики, товары не меняются
    manage.py source_ai_cards --source superstep --report --since 2026-11-07
    manage.py source_ai_cards --source superstep --apply --since 2026-11-07T07:00 --backup ~/backups/ss-rows.json.gz
    manage.py source_ai_cards --restore ~/backups/ss-rows.json.gz         # откат применения из бэкапа
    manage.py source_ai_cards --source superstep --fix-text fixes.json    # показать правку фраз черновиков
    manage.py source_ai_cards --source superstep --fix-text fixes.json --backup ~/backups/ss-fix.json  # записать

Черновик — обычный лог AI (полная обработка без применения): название, SEO и атрибуты
собирают правила (apps/ai/services/rules), описание пишет модель и кладёт в память
переводов — повторный такой же текст следующих партий берётся из памяти бесплатно.
Только Claude: с AI_OPENAI_ENABLED=true черновики не делаются (запасной путь ушёл бы в OpenAI),
товары без раздела не берутся (их категоризация — через эмбеддинги OpenAI).
Применяются только «Завершено» с даты --since (модерация остаётся людям); цену, валюту, бренд
и раздел применение не меняет (раздел — только у товара без раздела). Порядок — AI_GUIDE.md.
"""

import gzip
import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.apps import apps as django_apps
from django.conf import settings
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.ai.models import (
    AIApplicationStatus,
    AIModerationQueue,
    AIProcessingLog,
    AIProcessingStatus,
    AITranslationMemory,
)
from apps.ai.services.bulk_ops import select_products_for_ai
from apps.ai.services.content_generator import ContentGenerator
from apps.catalog.models import Product

MAX_WORKERS = 6
# Доменная запись и Product: переводы, атрибуты, размеры — пишет применение; варианты —
# синхронизация их названий после применения.
BACKUP_RELATIONS = ("translations", "dynamic_attributes", "sizes", "variants")
MOSCOW = ZoneInfo("Europe/Moscow")
NIGHT_START, NIGHT_END = time(1, 0), time(6, 30)
# Русский перевод товара при применении берётся из seo_translations.ru, а не из generated_description.
RU_SEO_FIELDS = ("generated_description", "meta_description", "og_description")


class Command(BaseCommand):
    help = "Новые товары источника — через правила и Claude: черновики, отчёт, применение с бэкапом строк."

    def add_arguments(self, parser):
        parser.add_argument("--source", help="Префикс external_id, например superstep")
        parser.add_argument("--ids", help="Только эти id товаров (через запятую)")
        parser.add_argument("--limit", type=int, default=500, help="Сколько товаров за запуск --run")
        parser.add_argument("--workers", type=int, default=4, help=f"Параллельных запросов (до {MAX_WORKERS})")
        parser.add_argument("--force", action="store_true", help="С --run: заново и уже обработанные (старые логи закроются)")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--run", action="store_true", help="Сделать черновики (товары не меняются)")
        mode.add_argument("--report", action="store_true", help="Итог по логам источника")
        mode.add_argument("--apply", action="store_true", help="Применить черновики «Завершено» (нужны --since и --backup)")
        mode.add_argument("--restore", metavar="BACKUP", help="Вернуть строки из бэкапа --apply и удалить созданные им")
        mode.add_argument(
            "--fix-text",
            metavar="FILE",
            help="Заменить фразы в черновиках: JSON {id товара: [[было, стало], …]}; без --backup только показ",
        )
        parser.add_argument("--backup", help="Новый файл бэкапа строк перед применением (.json или .json.gz)")
        parser.add_argument("--since", help="Логи с этого момента: ГГГГ-ММ-ДД или ГГГГ-ММ-ДДTЧЧ:ММ (МСК)")

    def handle(self, *args, **options):
        if options["restore"]:
            self._restore(options["restore"])
            return
        if not options["source"]:
            raise CommandError("Нужен --source")
        prefix = f"{options['source'].strip().rstrip('-')}-"
        products = Product.objects.filter(external_id__startswith=prefix)
        if options["ids"]:
            products = products.filter(id__in=self._ids(options["ids"]))
        if options["run"] or options["apply"]:
            self._check_night()
        if options["fix_text"]:
            self._fix_text(products, options)
        elif options["apply"]:
            if not options["since"] or not options["backup"]:
                raise CommandError("--apply требует --since (с какого момента логи) и --backup <файл>")
            self._apply(products, options)
        elif options["report"]:
            self._report(self._logs(products, options))
        else:
            self._run(products, options)

    @staticmethod
    def _ids(raw):
        try:
            return [int(x) for x in raw.split(",") if x.strip()]
        except ValueError:
            raise CommandError(f"--ids: нужны числа через запятую, получено {raw!r}") from None

    @staticmethod
    def _check_night():
        now = timezone.now().astimezone(MOSCOW).time()
        if NIGHT_START <= now < NIGHT_END:
            raise CommandError("С 01:00 до 06:30 МСК не запускать: ночные задачи сервера.")

    @staticmethod
    def _since(raw):
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=MOSCOW)
            except ValueError:
                continue
        raise CommandError(f"--since: ГГГГ-ММ-ДД или ГГГГ-ММ-ДДTЧЧ:ММ, получено {raw!r}")

    def _logs(self, products, options):
        logs = AIProcessingLog.objects.filter(product__in=products, processing_type="full")
        if options["since"]:
            logs = logs.filter(created_at__gte=self._since(options["since"]))
        return logs

    def _run(self, products, options):
        active = products.filter(is_active=True)
        skipped = {
            "неактивные": products.filter(is_active=False).count(),
            "без раздела": active.filter(category__isnull=True).count(),
        }
        candidates = select_products_for_ai(
            ids=list(active.filter(category__isnull=False).values_list("id", flat=True)),
            include_processed=options["force"],
        )
        ids = list(candidates.values_list("id", flat=True)[: options["limit"]])
        by_type = Counter(candidates.values_list("product_type", flat=True))
        label = "Товаров" if options["force"] else "Без русской карточки"
        self.stdout.write(f"{label}: {candidates.count()} {dict(by_type)}; к обработке: {len(ids)}; не берутся: {skipped}")
        if not options["run"] or not ids:
            self.stdout.write("Только показ: черновики — --run." if ids else "Новых товаров нет.")
            return
        if getattr(settings, "AI_OPENAI_ENABLED", True):
            raise CommandError("AI_OPENAI_ENABLED=true: запасной путь ушёл бы в OpenAI. Только Claude — выключите OpenAI.")
        workers = max(1, min(options["workers"], MAX_WORKERS))
        local = threading.local()

        def process(product_id):
            try:
                if not hasattr(local, "generator"):
                    local.generator = ContentGenerator()
                log = local.generator.process_product(
                    product_id, processing_type="full", auto_apply=False,
                    options={"force": True} if options["force"] else None,
                )
                return product_id, log.pk, str(log.status)
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
            "статусы": dict(Counter(map(str, logs.values_list("status", flat=True)))),
            "описание": dict(sources),  # memory — из памяти, llm — новый перевод, template — из фактов
            "название": dict(titles),  # rules — правила, llm — модель
            "модерация": dict(reasons),
            "стоимость_usd": float(cost),
        }, ensure_ascii=False))

    @staticmethod
    def _owned_rows(product):
        """Product, доменная запись и их строки, которые меняет применение."""
        objects = {}
        for obj in (product, product.domain_item):
            if obj is None:
                continue
            objects[(obj._meta.label, obj.pk)] = obj
            for relation in BACKUP_RELATIONS:
                manager = getattr(obj, relation, None)
                if manager is not None and hasattr(manager, "all"):
                    for row in manager.all():
                        objects[(row._meta.label, row.pk)] = row
                        for child in ("translations", "sizes"):  # переводы и размеры вариантов
                            sub = getattr(row, child, None) if relation == "variants" else None
                            if sub is not None and hasattr(sub, "all"):
                                objects.update({(item._meta.label, item.pk): item for item in sub.all()})
        return objects

    @staticmethod
    def _applied_titles(logs):
        """Товар → (название последнего полностью применённого лога, его id).

        Название, проверенное и правленное модератором в логе (``moderator_title_review``), —
        ручное: такой лог не даёт права перезаписать название (ревью #349)."""
        rows = (
            AIProcessingLog.objects.filter(
                product_id__in=[log.product_id for log in logs],
                application_status=AIApplicationStatus.APPLIED,
                generated_title__gt="",
            )
            .order_by("product_id", "-id")
            .distinct("product_id")
            .values_list("product_id", "generated_title", "id", "extracted_attributes")
        )
        return {
            product_id: (title.strip(), pk)
            for product_id, title, pk, attrs in rows
            if not (isinstance(attrs, dict) and attrs.get("moderator_title_review"))
        }

    def _apply(self, products, options):
        latest = list(
            self._logs(products.filter(is_active=True), options)
            .select_related("product")
            .order_by("product_id", "-id")
            .distinct("product_id")
        )
        # Самый новый лог товара в модерации или с ошибкой — старый «Завершено» не применяем.
        logs = [log for log in latest if log.status == AIProcessingStatus.COMPLETED]
        newer = Counter(str(log.status) for log in latest if log.status != AIProcessingStatus.COMPLETED)
        if newer:
            self.stdout.write(f"Пропущены: самый новый лог не «Завершено» — {dict(newer)}")
        if not logs:
            self.stdout.write("Нет черновиков «Завершено» с этой даты.")
            return
        # Название, правленное после обработки, не перезаписываем: снимок лога защищает
        # только описание, SEO и переводы. Такие товары — в админку. Название, записанное
        # прошлым применением AI (повторный --run --force), — не ручная правка (Seniorah, 09.11.2026).
        applied_titles = self._applied_titles(logs)

        def renamed_by_hand(log):
            name = log.product.name or ""
            if name == str((log.input_data or {}).get("name") or ""):
                return False
            title, applied_id = applied_titles.get(log.product_id, ("", 0))
            return not (title and name.strip() == title and applied_id < log.pk)

        manual = [log for log in logs if renamed_by_hand(log)]
        logs = [log for log in logs if log not in manual]
        for log in manual:
            self.stdout.write(f"  {log.product_id}: название менялось после обработки — пропущен (лог {log.pk})")
        before = {}
        for log in logs:
            before.update(self._owned_rows(log.product))
        opener = gzip.open if options["backup"].endswith(".gz") else open
        with opener(options["backup"], "xt", encoding="utf-8") as handle:  # «x»: чужой бэкап не затирается
            handle.write(serializers.serialize("json", list(before.values())))
        self.stdout.write(f"Бэкап: {options['backup']} ({len(before)} строк, {len(logs)} товаров)")

        generator = ContentGenerator()
        result, created = Counter(), set()
        for log in logs:
            try:
                # Товар и названия его вариантов — одной транзакцией: сбой синхронизации откатывает
                # и применение, товар не остаётся записанным наполовину (06.11.2026: три спорттовара).
                with transaction.atomic():
                    applied = generator.apply_log_to_product(log)
                    product = Product.objects.get(pk=log.product_id)
                    generator.sync_variant_titles_from_parent(product, log_entry=applied)
            except Exception as exc:
                result["error"] += 1
                self.stdout.write(f"  {log.product_id} (лог {log.pk}): {exc}")
                continue
            result[str(applied.application_status or applied.status)] += 1
            created.update(key for key in self._owned_rows(product) if key not in before)
        with open(f"{options['backup']}.created.json", "x", encoding="utf-8") as handle:
            json.dump(sorted([label, pk] for label, pk in created), handle)
        self.stdout.write(
            f"Применено: {dict(result)}; новых строк: {len(created)} (список — {options['backup']}.created.json). "
            f"Откат: source_ai_cards --restore {options['backup']}"
        )

    def _fix_text(self, products, options):
        """Правка черновика во всех русских местах: описание и SEO лога, seo_translations.ru, память.

        Применение берёт русский перевод из seo_translations.ru, а память отдаёт старый текст
        следующим партиям: правка одного generated_description на сайт не доходит (10.11.2026).
        """
        try:
            with open(options["fix_text"], encoding="utf-8") as handle:
                fixes = {int(pid): [tuple(pair) for pair in pairs] for pid, pairs in json.load(handle).items()}
        except (OSError, ValueError, TypeError) as exc:
            raise CommandError(f"--fix-text: {exc}") from None
        write = bool(options["backup"])
        if write:
            self._check_night()
        logs = {
            log.product_id: log
            for log in self._logs(products.filter(id__in=list(fixes)), options)
            .filter(status=AIProcessingStatus.COMPLETED)
            .order_by("product_id", "-id")
            .distinct("product_id")
        }

        def fix(text, pairs):
            for old, new in pairs:
                text = text.replace(old, new)
            return text

        changes = []
        for pid, pairs in fixes.items():
            log = logs.get(pid)
            if log is None:
                self.stdout.write(f"  {pid}: нет черновика «Завершено» — пропущен")
                continue
            missing = [old for old, _new in pairs if (log.generated_description or "").count(old) != 1]
            if missing:
                self.stdout.write(f"  {pid}: фраза не встречается в описании ровно один раз — пропущен: {missing[0]!r}")
                continue
            # SEO-описание лога — поле на 160 знаков: длинная замена роняла всю запись (11.11.2026).
            seo_limit = AIProcessingLog._meta.get_field("generated_seo_description").max_length
            if len(fix(log.generated_seo_description or "", pairs)) > seo_limit:
                self.stdout.write(f"  {pid}: после правки SEO-описание длиннее {seo_limit} знаков — пропущен, сократите замену")
                continue
            seo_ru = dict(((log.extracted_attributes or {}).get("seo_translations") or {}).get("ru") or {})
            memory = list(AITranslationMemory.objects.filter(source_log=log))
            changes.append((log, pairs, seo_ru, memory))
            self.stdout.write(f"  {pid} (лог {log.pk}): замен {len(pairs)}, записей памяти {len(memory)}")
        if not write or not changes:
            self.stdout.write(f"К правке: {len(changes)} из {len(fixes)}" + ("" if write else " (показ, для записи нужен --backup)"))
            return
        with open(options["backup"], "x", encoding="utf-8") as handle:
            json.dump(
                [
                    {
                        "log": log.pk,
                        "generated_description": log.generated_description,
                        "generated_seo_description": log.generated_seo_description,
                        "seo_ru": {key: seo_ru.get(key) for key in RU_SEO_FIELDS},
                        "memory": {row.pk: row.ru_text for row in memory},
                    }
                    for log, _pairs, seo_ru, memory in changes
                ],
                handle,
                ensure_ascii=False,
            )
        with transaction.atomic():
            for log, pairs, seo_ru, memory in changes:
                log.generated_description = fix(log.generated_description, pairs)
                if log.generated_seo_description:
                    log.generated_seo_description = fix(log.generated_seo_description, pairs)
                attrs = dict(log.extracted_attributes or {})
                translations = dict(attrs.get("seo_translations") or {})
                for key in RU_SEO_FIELDS:
                    if isinstance(seo_ru.get(key), str):
                        seo_ru[key] = fix(seo_ru[key], pairs)
                if seo_ru:
                    translations["ru"] = seo_ru
                    attrs["seo_translations"] = translations
                    log.extracted_attributes = attrs
                log.save(update_fields=["generated_description", "generated_seo_description", "extracted_attributes"])
                for row in memory:
                    row.ru_text = fix(row.ru_text, pairs)
                    row.save(update_fields=["ru_text"])
        self.stdout.write(f"Исправлено черновиков: {len(changes)} из {len(fixes)}. Бэкап: {options['backup']}")

    def _restore(self, backup):
        opener = gzip.open if backup.endswith(".gz") else open
        try:
            with opener(backup, "rt", encoding="utf-8") as handle:
                rows = list(serializers.deserialize("json", handle.read()))
            with open(f"{backup}.created.json", encoding="utf-8") as handle:
                created = json.load(handle)
        except OSError as exc:
            raise CommandError(f"Нет файла бэкапа: {exc}") from None
        with transaction.atomic():
            for label, pk in created:
                django_apps.get_model(label).objects.filter(pk=pk).delete()
            for row in rows:
                row.save()
        self.stdout.write(
            f"Восстановлено строк: {len(rows)}, удалено созданных: {len(created)}. "
            "Логи AI остаются «Применено» — при новом применении нужен новый --run."
        )
