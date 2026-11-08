"""Разделы по спросу в рунете (исследование 05.11.2026, reports/superstep-seo-core-2026-11-05.md).

Создаёт недостающие разделы, под которые у SuperStep есть товары и которые ищут
(«флиска», «рюкзак», «термокружка stanley»), и переименовывает разделы, названия
которых так не ищут («Слайды» → «Шлёпанцы»). Остальные нужные разделы уже есть
(«Беговые», «Угги», «Сабо») — их заполняет раскладка парсера. 07.11.2026 добавлены
«Туфли на каблуке» и «Балетки» под женскую обувь Seniorah: на проде команда создаст
только их, прежние разделы уже есть.

Переименование — только если название ещё прежнее (ручные правки не затираются).
Описание, равное старому названию, заменяется новым (как в constants.py); автоматические
title/description и тексты посадочной страницы со старым названием очищаются — страница
строит их из нового названия. Товары не переносятся.

    manage.py ensure_demand_categories                                          # показ
    manage.py ensure_demand_categories --apply --backup /backups/demand-categories.json
    manage.py ensure_demand_categories --only heels,ballet-flats --apply --backup /backups/heels.json

``--only`` — только перечисленные slug (новые разделы и переименования): остальное ждёт
решения владельца.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max

from apps.catalog.models import Category, CategoryTranslation, Product

# (родитель, slug, RU, EN, описание RU, описание EN)
NEW_CATEGORIES = [
    ("knitwear", "fleece", "Флиски", "Fleece Jackets", "Флиски и флисовые кофты", "Fleece jackets"),
    ("bags-wallets", "backpacks", "Рюкзаки", "Backpacks", "Рюкзаки городские и спортивные", "City and sports backpacks"),
    (
        "drinkware", "thermoses", "Термосы и термокружки", "Thermoses & Travel Mugs",
        "Термосы, термокружки и термобутылки", "Thermoses, travel mugs and insulated bottles",
    ),
    # Женская обувь Seniorah (решение владельца 07.11.2026, reports/seniorah-feasibility-2026-11-07.md):
    # «туфли на каблуке» и «балетки» ищут именно так, а своего раздела у них не было.
    (
        "dress-shoes", "heels", "Туфли на каблуке", "Heels",
        "Женские туфли на каблуке: шпильки, лодочки, на толстом каблуке",
        "Women's heels: stilettos, pumps, block heels",
    ),
    (
        "casual-shoes", "ballet-flats", "Балетки", "Ballet Flats",
        "Балетки женские: лаковые, замшевые, Мэри Джейн", "Women's ballet flats: patent, suede, Mary Jane",
    ),
]
# (slug, прежнее RU, новое RU, новое описание RU): «шлёпанцы» и «сланцы» ищут, «слайды» —
# нет; «толстовка» — самое частое слово для худи и свитшотов. Порядок важен: имя
# уникально внутри родителя, поэтому «Шлёпанцы» сначала освобождаются.
RENAMES = [
    ("flip-flops", "Шлёпанцы", "Сланцы и вьетнамки", "Сланцы и вьетнамки"),
    ("slides", "Слайды", "Шлёпанцы", "Шлёпанцы"),
    ("hoodies", "Худии", "Толстовки и худи", "Толстовки и худи"),
]
AUTO_META_FIELDS = ("meta_title", "og_title", "meta_description", "og_description", "meta_keywords")
LANDING_FIELDS = ("h1", "meta_title", "meta_description", "seo_text")


def _category_row(category):
    return {
        "id": category.pk,
        "slug": category.slug,
        "name": category.name,
        **{field: getattr(category, field) for field in AUTO_META_FIELDS},
        "description": category.description,
        "translations": [
            {"locale": t.locale, "name": t.name, "description": t.description, **{f: getattr(t, f) for f in LANDING_FIELDS}}
            for t in category.translations.all()
        ],
    }


class Command(BaseCommand):
    help = "Создаёт и переименовывает разделы по спросу в рунете (по умолчанию — только показ)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Записать изменения.")
        parser.add_argument("--backup", default="", help="JSON-файл бэкапа (обязателен с --apply).")
        parser.add_argument(
            "--only",
            default="",
            help="Только эти slug через запятую (например heels,ballet-flats); без него — все.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        if apply and not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл>.")

        creates, renames, taken = self._plan(self._only(options["only"]))
        for parent, slug, name_ru in taken:
            self.stdout.write(
                f"! «{name_ru}» уже есть в «{parent.name}» ({parent.slug}) под другим slug — {slug} не создаю"
            )
        self._report_ballet_flats(creates)
        for parent, slug, name_ru, *_ in creates:
            self.stdout.write(f"+ раздел «{name_ru}» ({slug}) в «{parent.name}» ({parent.slug})")
        for category, old, new, _ in renames:
            self.stdout.write(f"~ «{old}» → «{new}» ({category.slug})")
        if not creates and not renames:
            self.stdout.write("Изменений нет.")
            return
        if not apply:
            self.stdout.write("Показ: ничего не изменено. Для записи: --apply --backup <файл>.")
            return

        with open(options["backup"], "w", encoding="utf-8") as fh:
            json.dump({"renamed": [_category_row(c) for c, *_ in renames], "created": [c[1] for c in creates]}, fh, ensure_ascii=False, indent=1)
        with transaction.atomic():
            for parent, slug, name_ru, name_en, desc_ru, desc_en in creates:
                self._create(parent, slug, name_ru, name_en, desc_ru, desc_en)
            for category, old, new, description in renames:
                self._rename(category, old, new, description)
        self.stdout.write(self.style.SUCCESS(
            f"Создано разделов: {len(creates)}, переименовано: {len(renames)}. Бэкап: {options['backup']}"
        ))

    @staticmethod
    def _only(raw):
        """Набор slug из ``--only`` или None (все). Незнакомый slug — ошибка, а не тишина."""
        slugs = {slug.strip() for slug in str(raw or "").split(",") if slug.strip()}
        if not slugs:
            return None
        known = {row[1] for row in NEW_CATEGORIES} | {row[0] for row in RENAMES}
        unknown = sorted(slugs - known)
        if unknown:
            raise CommandError(f"Неизвестные slug в --only: {', '.join(unknown)}. Есть: {', '.join(sorted(known))}.")
        return slugs

    def _plan(self, only=None):
        missing_parents = []
        creates = []
        taken = []
        for parent_slug, slug, *names in NEW_CATEGORIES:
            if only is not None and slug not in only:
                continue
            if Category.objects.filter(slug=slug).exists():
                continue
            parent = Category.objects.filter(slug=parent_slug).first()
            if parent is None:
                missing_parents.append(parent_slug)
                continue
            # Имя уникально внутри родителя: раздел с тем же именем (заведённый руками)
            # уронил бы всю транзакцию на IntegrityError.
            if Category.objects.filter(parent=parent, name=names[0]).exists():
                taken.append((parent, slug, names[0]))
                continue
            creates.append((parent, slug, *names))
        if missing_parents:
            raise CommandError(f"Нет родительских разделов: {', '.join(missing_parents)}.")
        renames = [
            (category, old, new, description)
            for slug, old, new, description in RENAMES
            if only is None or slug in only
            for category in Category.objects.filter(slug=slug, name=old)
        ]
        return creates, renames, taken

    def _report_ballet_flats(self, creates):
        """Товары «балетки» вне «Повседневной обуви»: после появления раздела «Балетки»
        проверка названия может счесть их чужими разделу (title_category_mismatch)."""
        if not any(slug == "ballet-flats" for _, slug, *_ in creates):
            return
        rows = (
            Product.objects.filter(name__icontains="балетк")
            .exclude(category__slug="casual-shoes")
            .values_list("id", "name", "category__slug")
            .order_by("id")
        )
        count = rows.count()
        if not count:
            return
        self.stdout.write(f"Товары «балетк…» вне casual-shoes: {count} (после раздела «Балетки» проверить):")
        for product_id, name, category in rows[:20]:
            self.stdout.write(f"  {product_id} [{category}] {name}")

    def _create(self, parent, slug, name_ru, name_en, desc_ru, desc_en):
        last = Category.objects.filter(parent=parent).aggregate(value=Max("sort_order"))["value"]
        category = Category.objects.create(
            slug=slug,
            name=name_ru,
            description=desc_ru,
            parent=parent,
            category_type=parent.category_type,
            gender=parent.gender,
            is_active=True,
            sort_order=(last or 0) + 1,
        )
        for locale, name, description in (("ru", name_ru, desc_ru), ("en", name_en, desc_en)):
            CategoryTranslation.objects.create(category=category, locale=locale, name=name, description=description)

    def _rename(self, category, old, new, description):
        category.name = new
        fields = ["name"]
        if (category.description or "").strip() == old:
            category.description = description
            fields.append("description")
        for field in AUTO_META_FIELDS:
            if old in str(getattr(category, field) or ""):
                setattr(category, field, "")  # шаблон страницы соберёт из нового названия
                fields.append(field)
        category.save(update_fields=fields)
        for translation in CategoryTranslation.objects.filter(category=category, locale="ru"):
            if translation.name == old:
                translation.name = new
            if (translation.description or "").strip() == old:
                translation.description = description
            for field in LANDING_FIELDS:
                if old in str(getattr(translation, field) or ""):
                    setattr(translation, field, "")  # текст со старым названием — шаблон до перегенерации
            translation.save()
