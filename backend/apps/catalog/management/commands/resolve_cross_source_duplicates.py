"""Одинаковые товары FLO и SuperStep: показать более дорогое предложение (показ по умолчанию).

Правила и устройство — docs/CROSS_SOURCE_DUPLICATES.md, сервис —
apps/catalog/services/cross_source_duplicates.py.

    manage.py resolve_cross_source_duplicates                          # отчёт: пары и кто победит
    manage.py resolve_cross_source_duplicates --product 123 --product 456
    manage.py resolve_cross_source_duplicates --apply --backup /backups/dups.json
    manage.py resolve_cross_source_duplicates --unhide-all --apply --backup /backups/dups-undo.json

Ничего не удаляет: скрытый цвет — ``is_active=False`` и строка CrossSourceDuplicate,
скрытая целиком карточка — ``is_active=False`` у Product и доменной записи. Откат —
``--unhide-all --apply``; бэкап хранит прежние is_active и строки дублей.
Автоматический пересчёт (после импорта, проверки карточки, ночью) включает
CROSS_SOURCE_DUPLICATES_ENABLED=true — после «да» владельца по отчёту.
"""
import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.catalog.models import CrossSourceDuplicate, Product
from apps.catalog.services.cross_source_duplicates import TYPE_MODELS, CrossSourceDuplicateService

SOURCE_TITLES = {"flo": "FLO", "superstep": "SuperStep"}


class Command(BaseCommand):
    help = "FLO ↔ SuperStep: показать более дорогое из одинаковых предложений (без --apply — только отчёт)."

    def add_arguments(self, parser):
        parser.add_argument("--product", type=int, action="append", default=[], help="pk Product (можно несколько раз).")
        parser.add_argument(
            "--type", action="append", default=[], choices=sorted(TYPE_MODELS), help="Тип товара (по умолчанию все)."
        )
        parser.add_argument("--sample", type=int, default=20, help="Сколько пар показать в отчёте.")
        parser.add_argument("--unhide-all", action="store_true", help="Откат: вернуть на сайт всё скрытое как дубли.")
        parser.add_argument("--apply", action="store_true", help="Изменить данные (иначе только показ).")
        parser.add_argument("--backup", default="", help="JSON-файл бэкапа (обязателен с --apply).")

    def handle(self, *args, **options):
        if options["apply"] and not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл>.")
        service = CrossSourceDuplicateService(options["type"] or TYPE_MODELS)
        product_ids = options["product"] or None

        if options["unhide_all"]:
            rows = CrossSourceDuplicate.objects.filter(product_type__in=service.product_types)
            self.stdout.write(f"Скрыто как дубли сейчас: цветов {rows.count()}, карточек целиком "
                              f"{rows.filter(product_hidden=True).values('hidden_product').distinct().count()}.")
            if not options["apply"]:
                self.stdout.write("Dry-run: ничего не изменено. Для отката: --unhide-all --apply --backup <файл>.")
                return
            self._write_backup(options["backup"], service, list(rows.values_list("hidden_variant_id", flat=True)))
            shown = service.unhide_all()
            self.stdout.write(self.style.SUCCESS(f"Возвращено на сайт цветов: {shown}. Бэкап: {options['backup']}"))
            return

        report = service.resolve(product_ids, dry_run=True)
        decisions = report["decisions"]
        self._print_report(decisions, options["sample"])
        if not options["apply"]:
            self.stdout.write("Dry-run: ничего не изменено. Для записи: --apply --backup <файл>.")
            return

        variant_ids = [m.variant_id for d in decisions for m in [d.shown, *(h[0] for h in d.hidden)]]
        self._write_backup(options["backup"], service, variant_ids)
        report = service.resolve(product_ids)
        self.stdout.write(self.style.SUCCESS(
            f"Групп: {report['groups']}. Скрыто новых цветов: {report['hidden']}, осталось скрытыми: "
            f"{report['kept']}, возвращено на сайт: {report['shown']}. Бэкап: {options['backup']}"
        ))

    def _print_report(self, decisions, sample: int) -> None:
        hidden = [(d, m, match, reason) for d in decisions for m, match, reason in d.hidden]
        by_type = Counter(d.product_type for d in decisions)
        self.stdout.write(f"Групп одинаковых цветов: {len(decisions)} ({', '.join(f'{k}: {v}' for k, v in by_type.items()) or '—'}).")
        self.stdout.write(f"Скрыть цветов: {len(hidden)}, из них уже скрыты: {sum(1 for _, m, _, _ in hidden if m.row)}.")
        self.stdout.write(
            "Как узнали: штрихкод — {}, бренд + артикул — {}.".format(
                sum(1 for *_, match, _ in hidden if match == CrossSourceDuplicate.Match.EAN),
                sum(1 for *_, match, _ in hidden if match == CrossSourceDuplicate.Match.ARTICLE),
            )
        )
        winners = Counter(d.shown.source for d in decisions)
        self.stdout.write("Показан: " + (", ".join(f"{SOURCE_TITLES.get(k, k)} — {v}" for k, v in winners.items()) or "—"))
        stock = sum(1 for d in decisions if any(r == CrossSourceDuplicate.Reason.STOCK for *_, r in d.hidden))
        self.stdout.write(f"Показан более дешёвый, потому что у дорогого нет размеров: {stock}.")

        names = dict(
            Product.objects.filter(
                pk__in={m.product_id for d in decisions[:sample] for m in [d.shown, *(h[0] for h in d.hidden)]}
            ).values_list("pk", "name")
        )
        for decision in decisions[:sample]:
            shown = decision.shown
            self.stdout.write(
                f"  ПОКАЗ {self._describe(shown, names)}"
                + "".join(f"\n    скрыть {self._describe(m, names)} [{match}, {reason}]" for m, match, reason in decision.hidden)
            )

    @staticmethod
    def _describe(member, names) -> str:
        stock = "есть размеры" if member.available else "нет размеров"
        return (
            f"{SOURCE_TITLES.get(member.source, member.source)} #{member.product_id} "
            f"«{names.get(member.product_id, '')}» на сайте {member.site_price} {member.currency} "
            f"(у продавца {member.price}), {stock}"
        )

    @staticmethod
    def _write_backup(path: str, service: CrossSourceDuplicateService, variant_ids) -> None:
        variant_ids = set(variant_ids)
        variants, product_ids = [], set()
        for product_type in service.product_types:
            variant_model = TYPE_MODELS[product_type][0]
            for vid, base_id, active in variant_model.objects.filter(pk__in=variant_ids).values_list(
                "id", "product__base_product_id", "is_active"
            ):
                variants.append({"product_type": product_type, "id": vid, "is_active": active})
                product_ids.add(base_id)
        rows = list(
            CrossSourceDuplicate.objects.filter(product_type__in=service.product_types).values(
                "product_type", "hidden_variant_id", "shown_variant_id", "hidden_product_id", "shown_product_id",
                "match", "reason", "product_hidden",
            )
        )
        products = [
            {"id": pid, "is_active": active}
            for pid, active in Product.objects.filter(pk__in=product_ids).values_list("id", "is_active")
        ]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(
                {"created_at": timezone.now().isoformat(), "variants": variants, "products": products, "rows": rows},
                fh,
                ensure_ascii=False,
                indent=1,
            )
