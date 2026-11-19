"""Что изменится, если включить шкалу наценки. Только чтение: в базу ничего не пишет.

Примеры:
    manage.py markup_scale_preview --scale "0:100,5000:50,10000:20"
    manage.py markup_scale_preview --scale-id 3 --category shoes --category clothing
    manage.py markup_scale_preview --scale "0:100,2000:50" --csv /tmp/markup_scale.csv

Без --category шкала примеряется как глобальная (лекарства и услуги под неё не идут),
с --category — как выбранная у этих разделов. Считаются активные товары с ценой, по цене
самого товара; у товаров с вариантами цена варианта может попасть на другую ступень.
"""

import csv
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from statistics import median
from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.currency_models import GlobalCurrencySettings, load_markup_scales
from apps.catalog.models import Brand, Category, Product
from apps.catalog.utils.product_markup import resolve_markup_rule

PREVIEW_ID = -1
HUNDRED = Decimal("100")


def parse_scale(text):
    steps = []
    for part in text.split(","):
        try:
            price_from, percent = (Decimal(value.strip()) for value in part.split(":"))
        except (ValueError, InvalidOperation):
            raise CommandError(f"Ступень «{part}» не разобрана. Формат: от:процент, например 0:100,5000:50.")
        if price_from < 0 or not 0 <= percent <= 500:
            raise CommandError(f"Ступень «{part}»: цена не меньше 0, процент от 0 до 500.")
        steps.append((price_from, percent))
    steps.sort()
    if not steps or steps[0][0] != 0:
        raise CommandError("Первая ступень должна начинаться с 0 лир.")
    if len({start for start, _percent in steps}) != len(steps):
        raise CommandError("Две ступени начинаются с одной и той же цены.")
    return tuple(steps)


class Command(BaseCommand):
    help = "Показывает, как изменятся цены при включении шкалы наценки (только чтение)"

    def add_arguments(self, parser):
        parser.add_argument("--scale", help='Ступени «от:процент» через запятую, например "0:100,5000:50,10000:20"')
        parser.add_argument("--scale-id", type=int, help="Номер уже заведённой шкалы")
        parser.add_argument(
            "--category", action="append", default=[],
            help="Slug раздела, у которого примеряется шкала (можно несколько). Без него — глобально.",
        )
        parser.add_argument("--csv", help="Куда записать построчный отчёт по товарам")
        parser.add_argument("--examples", type=int, default=5, help="Сколько примеров показать")

    def handle(self, *args, **options):
        scales = dict(load_markup_scales())
        if bool(options["scale"]) == bool(options["scale_id"]):
            raise CommandError("Укажите одно из двух: --scale или --scale-id.")
        if options["scale"]:
            name, steps = "проверяемая", parse_scale(options["scale"])
        else:
            if options["scale_id"] not in scales or not scales[options["scale_id"]][1]:
                raise CommandError(f"Шкалы с номером {options['scale_id']} нет или в ней нет ступеней.")
            name, steps = scales[options["scale_id"]]
        new_scales = {**scales, PREVIEW_ID: (name, steps)}

        categories = {category.pk: category for category in Category.objects.all()}
        for category in categories.values():
            category.parent = categories.get(category.parent_id)
        brands = {brand.pk: brand for brand in Brand.objects.filter(margin_percent__gt=0)}
        settings_now = GlobalCurrencySettings.load()
        settings_new = settings_now

        targets = []
        for slug in options["category"]:
            target = next((c for c in categories.values() if c.slug == slug), None)
            if target is None:
                raise CommandError(f"Раздела «{slug}» нет.")
            targets.append(target)

        rows = list(
            Product.objects.filter(is_active=True, price__gt=0).values_list(
                "id", "name", "product_type", "price", "currency", "brand_id", "category_id"
            )
        )

        def percents(settings, scales_map):
            rules, result = {}, []
            for _pk, _name, product_type, price, currency, brand_id, category_id in rows:
                key = (brand_id if brand_id in brands else None, category_id, product_type)
                if key not in rules:
                    rules[key] = resolve_markup_rule(
                        SimpleNamespace(
                            brand=brands.get(brand_id),
                            category=categories.get(category_id),
                            product_type=product_type,
                        ),
                        settings=settings,
                        scales=scales_map,
                    )
                result.append(rules[key].resolve(price, currency))
            return result

        now = percents(settings_now, scales)
        if targets:
            for target in targets:
                target.markup_scale_id = PREVIEW_ID  # только в памяти, не сохраняется
        else:
            settings_new = SimpleNamespace(
                default_margin_percentage=settings_now.default_margin_percentage,
                markup_scale_id=PREVIEW_ID,
            )
        new = percents(settings_new, new_scales)

        stats = defaultdict(lambda: {"всего": 0, "дороже": 0, "дешевле": 0, "изменения": []})
        steps_hit = Counter()
        changed = []
        for row, before, after in zip(rows, now, new):
            pk, product_name, product_type, price, currency, _brand_id, _category_id = row
            price_now = price * (1 + before.percent / HUNDRED)
            price_new = price * (1 + after.percent / HUNDRED)
            change = (price_new / price_now - 1) * HUNDRED
            entry = stats[product_type]
            entry["всего"] += 1
            if after.scale is not None and after.scale_name == name:
                steps_hit[after.scale.step_from] += 1
            if abs(change) >= Decimal("0.005"):
                entry["дороже" if change > 0 else "дешевле"] += 1
                entry["изменения"].append(change)
                changed.append((change, pk, product_type, product_name, price, currency, before, after, price_now, price_new))

        where = "у разделов " + ", ".join(t.slug for t in targets) if targets else "глобально"
        self.stdout.write(f"Шкала «{name}» {where}: " + "; ".join(f"от {s:f} — {p:f} %" for s, p in steps))
        self.stdout.write(f"Активных товаров с ценой: {len(rows)}; цена изменится у {len(changed)}.")
        self.stdout.write("")
        self.stdout.write("тип | всего | подорожает | подешевеет | без изменений | медиана изменения, % | от … до, %")
        for product_type in sorted(stats, key=lambda key: -stats[key]["всего"]):
            entry = stats[product_type]
            changes = entry["изменения"]
            same = entry["всего"] - entry["дороже"] - entry["дешевле"]
            spread = f"{median(changes):+.1f} | {min(changes):+.1f} … {max(changes):+.1f}" if changes else "— | —"
            self.stdout.write(
                f"{product_type} | {entry['всего']} | {entry['дороже']} | {entry['дешевле']} | {same} | {spread}"
            )
        self.stdout.write("")
        self.stdout.write("Товаров на ступенях шкалы: " + (
            "; ".join(f"от {start:f} лир — {steps_hit[start]}" for start in sorted(steps_hit)) or "ни одного"
        ))

        changed.sort(key=lambda item: item[0])
        count = max(options["examples"], 0)
        for title, sample in (("Сильнее всего подешевеют", changed[:count]), ("Сильнее всего подорожают", changed[::-1][:count])):
            sample = [item for item in sample if (item[0] < 0) == (title.endswith("подешевеют"))]
            if not sample:
                continue
            self.stdout.write("")
            self.stdout.write(f"{title} (цена источника с наценкой, без валютной):")
            for change, pk, product_type, product_name, price, currency, before, after, price_now, price_new in sample:
                self.stdout.write(
                    f"  {pk} | {product_type} | {product_name[:60]} | {price} {currency} | "
                    f"{before.percent:.1f} % → {after.percent:.1f} % | {price_now:.2f} → {price_new:.2f} ({change:+.1f} %)"
                )

        if options["csv"]:
            with open(options["csv"], "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow([
                    "id", "тип", "название", "цена источника", "валюта", "наценка сейчас, %",
                    "наценка по шкале, %", "цена сейчас", "цена по шкале", "изменение, %",
                ])
                for change, pk, product_type, product_name, price, currency, before, after, price_now, price_new in changed:
                    writer.writerow([
                        pk, product_type, product_name, price, currency, f"{before.percent:.2f}",
                        f"{after.percent:.2f}", f"{price_now:.2f}", f"{price_new:.2f}", f"{change:.2f}",
                    ])
            self.stdout.write("")
            self.stdout.write(f"Построчный отчёт: {options['csv']} ({len(changed)} строк)")
        self.stdout.write("")
        self.stdout.write("Ничего не записано: шкала не включена, цены на сайте прежние.")
