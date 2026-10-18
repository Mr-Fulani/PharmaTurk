"""Перегенерировать только названия БАДов, отклонённые валидатором.

Берёт открытые записи модерации БАДов, у которых среди причин есть
title_identity_lost или title_untranslated, и для каждого лога делает один
короткий запрос только за RU/EN-названием (тот же повтор, что в обработке:
ContentGenerator._retry_supplement_title, ≈$0.0002). Название записывается в
лог, только если проходит проверки. Товар команда не меняет: после неё
закрыть модерацию и применить названия — close_resolved_ai_moderation.

    manage.py retry_ai_titles --limit 50 --dry-run
    manage.py retry_ai_titles --limit 50
    manage.py close_resolved_ai_moderation --product-type supplements --dry-run
"""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.ai.models import AIModerationQueue, AIProcessingStatus
from apps.ai.services.content_generator import SUPPLEMENT_TITLE_RETRY_REASONS, ContentGenerator
from apps.ai.services.quality_checker import get_moderation_reasons


class Command(BaseCommand):
    help = "Перегенерировать только отклонённые названия БАДов на модерации (один короткий запрос на лог)"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, required=True, help="Максимум логов с повтором за запуск")
        parser.add_argument("--dry-run", action="store_true", help="Только показать логи; OpenAI не вызывается")

    def handle(self, *args, **options):
        if options["limit"] <= 0:
            raise CommandError("--limit должен быть > 0")
        queue = (
            AIModerationQueue.objects.filter(
                resolved_at__isnull=True,
                log_entry__status=AIProcessingStatus.MODERATION,
                log_entry__product__product_type="supplements",
            )
            .select_related("log_entry__product")
            .order_by("id")
        )

        generator = None if options["dry_run"] else ContentGenerator()
        selected = fixed = failed = 0
        cost = Decimal("0")
        for task in queue.iterator():
            if selected >= options["limit"]:
                break
            log = task.log_entry
            reasons = [r for r in get_moderation_reasons(log) if r in SUPPLEMENT_TITLE_RETRY_REASONS]
            if not reasons:
                continue
            selected += 1
            if options["dry_run"]:
                self.stdout.write(f"лог {log.id}, товар {log.product_id}: {', '.join(reasons)} — «{log.generated_title}»")
                continue

            attrs = dict(log.extracted_attributes or {})
            seo = dict(attrs.get("seo_translations") or {})
            ru_seo = dict(seo.get("ru") or {})
            en_seo = dict(seo.get("en") or {})
            content = {
                "ru": {"generated_title": ru_seo.get("generated_title") or log.generated_title},
                "en": {"generated_title": en_seo.get("generated_title") or ""},
            }
            content, retry = generator._retry_supplement_title(log.product, content)
            if not retry:
                failed += 1
                self.stdout.write(self.style.WARNING(f"лог {log.id}: запрос не выполнен"))
                continue
            retry_cost = Decimal(str(retry.get("cost_usd") or 0))
            cost += retry_cost
            log.cost_usd = (log.cost_usd or Decimal("0")) + retry_cost
            raw = log.raw_llm_response if isinstance(log.raw_llm_response, dict) else {}
            log.raw_llm_response = {
                **raw,
                "title_retry": {
                    "tokens": retry.get("tokens"),
                    "cost_usd": retry.get("cost_usd"),
                    "repaired_fields": retry.get("repaired_fields", []),
                    "failed_fields": retry.get("failed_fields", []),
                },
            }
            update_fields = ["cost_usd", "raw_llm_response", "updated_at"]
            if retry.get("repaired_fields"):
                new_ru = content["ru"]["generated_title"]
                new_en = content["en"]["generated_title"]
                log.generated_title = generator._normalize_product_name(new_ru, "supplements")
                ru_seo["generated_title"] = new_ru
                seo["ru"] = ru_seo
                if new_en:
                    en_seo["generated_title"] = new_en
                    seo["en"] = en_seo
                attrs["seo_translations"] = seo
                log.extracted_attributes = attrs
                update_fields += ["generated_title", "extracted_attributes"]
                fixed += 1
                self.stdout.write(f"лог {log.id}: «{log.generated_title}» / «{new_en}»")
            else:
                failed += 1
                self.stdout.write(self.style.WARNING(f"лог {log.id}: новое название не прошло проверку"))
            log.save(update_fields=update_fields)

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(
                f"Итого: к повтору {selected} логов, оценка ≈ ${selected * 0.0002:.4f}"
            ))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Итого: исправлено {fixed}, не исправлено {failed}, стоимость ${cost:.6f}. "
            "Дальше: close_resolved_ai_moderation --product-type supplements"
        ))
