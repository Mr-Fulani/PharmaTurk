"""Пересчёт порядка «Популярные» у лекарств и БАДов (docs/CATALOG_SEARCH_DEMAND.md).

То же, что ночная задача ``catalog.recompute_sort_ranks``. Без ``--apply`` ничего не
пишет: показывает, сколько товаров сменит место и первые строки списка до и после.
"""
from django.core.management.base import BaseCommand

from apps.catalog.services.catalog_sort_rank import changed_sort_ranks, ranked_models


class Command(BaseCommand):
    help = "Пересчитывает порядок «Популярные». Без --apply — только показ."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Записать новый порядок.")
        parser.add_argument("--top", type=int, default=20, help="Сколько первых товаров показать.")

    def handle(self, *args, **options):
        top = options["top"]
        for model in ranked_models():
            title = model._meta.verbose_name_plural
            ranks = dict(model.objects.filter(is_active=True).values_list("id", "sort_rank"))
            before = sorted(ranks, key=lambda pk: (-ranks[pk], -pk))[:top]
            changed = changed_sort_ranks(model)
            ranks.update({product.id: product.sort_rank for product in changed})
            after = sorted(ranks, key=lambda pk: (-ranks[pk], -pk))[:top]
            names = dict(model.objects.filter(id__in=before + after).values_list("id", "name"))

            self.stdout.write(f"\n{title}: место сменят {len(changed)} из {len(ranks)}")
            for label, ids in (("Сейчас", before), ("Станет", after)):
                self.stdout.write(f"  {label}:")
                for place, pk in enumerate(ids, start=1):
                    self.stdout.write(f"    {place}. {names[pk]} (id {pk})")
            if options["apply"]:
                # bulk_update не вызывает save(): карточки и Product не трогаем.
                model.objects.bulk_update(changed, ["sort_rank"], batch_size=1000)

        done = "Записано." if options["apply"] else "Показ без записи (для записи добавьте --apply)."
        self.stdout.write(f"\n{done}")
