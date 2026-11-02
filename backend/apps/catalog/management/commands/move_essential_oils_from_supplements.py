"""Перенести эфирные масла и гидролаты из БАДов в раздел «Эфирные масла» (dry-run по умолчанию).

ilacfiyati.com держит линейку PHYTOIL (эфирные масла, гидролаты, цветочные воды
Elentra İlaç) среди БАДов, и они сохранялись у нас БАДами: в описании карточки
стояло «Биологически активная добавка к пище», а семантическая проверка AI
отклоняла тексты (title_category_mismatch, supplement_health_claim). Правило
отбора — catalog.essential_oils.

    manage.py move_essential_oils_from_supplements                       # показ
    manage.py move_essential_oils_from_supplements --product 23956       # показ по товару
    manage.py move_essential_oils_from_supplements --section-markup 50                # показ с наценкой раздела 50 %
    manage.py move_essential_oils_from_supplements --section-markup 50 --apply --backup /backups/essential-oils.json

С товаром (одна транзакция на товар):
1. создаётся IncenseProduct — копия общих полей SupplementProduct (цена, наличие,
   главное фото, EN SEO, внешние данные) и его переводов; категория — раздел масел;
2. Product: product_type=incense и та же категория через update(). save() здесь
   нельзя: новая доменная запись синхронизировала бы в Product пустые RU SEO;
3. domain_sync.retire_stale_domain_records: галерея БАДа копируется в новую запись,
   SupplementProduct снимается с публикации (is_active=False, не удаляется);
4. из описаний (Product, его переводы, новая запись и её переводы) убирается
   абзац-оговорка БАДа (ai.services.supplement_content.DISCLAIMER), из ключевых слов —
   «БАД …» / «food supplement …» (supplement_content.build_seo; вещество есть отдельным словом);
5. «Хит продаж» снимается (только лекарства и БАДы), бренду добавляется тип incense.

Наценка = цена на сайте. Она считается от раздела (utils.product_markup): у БАДов — 50 %
корня «БАДы», у «Эфирных масел» своей нет, сработает общая (02.11.2026 — 25 %), и цена упала
бы ≈ на 17 %. Показ печатает цену с наценкой до и после; --apply отказывает, если наценка
меняется, пока не выбран вариант: --section-markup 50 (записать разделу essential-oils
наценку, цена прежняя) или --allow-markup-change (решение владельца снизить цену).

Slug и адрес карточки не меняются (/product/<slug> у обоих типов). ProductSourceOffer,
цены в валютах, корзины и заказы ссылаются на Product и не трогаются. Атрибуты БАДа
(форма, вещество, порция) остаются у снятой записи. Название и SEO не переписываются:
их обновит повторная AI-обработка уже как масла.

Откат по бэкапу: IncenseProduct.objects.filter(pk__in=…).delete() — через queryset,
не instance.delete() (тот удалил бы и Product; файлы не удалятся — на них ссылается
запись БАДа), затем вернуть Product (product_type, category_id, is_featured,
description, keywords, meta_keywords), описания и meta_keywords ProductTranslation,
is_active/is_featured SupplementProduct, category_slugs/primary_category_slug бренда и
margin_percent раздела essential-oils.
"""
import json
from collections import Counter
from decimal import Decimal
from types import SimpleNamespace

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.ai.services.supplement_content import DISCLAIMER
from apps.catalog.domain_sync import (
    _base_product_to_domain_kwargs,
    _copied_values,
    retire_stale_domain_records,
)
from apps.catalog.essential_oils import (
    PRODUCT_TYPE,
    ROOT_SLUG,
    essential_oil_category,
    essential_oil_category_slug,
)
from apps.catalog.models import (
    Category,
    IncenseProduct,
    IncenseProductTranslation,
    Product,
    ProductTranslation,
    SupplementProduct,
)
from apps.catalog.scraper_category_mapping import _resolve_product_type
from apps.catalog.services.product_resolve import RESOLVE_CACHE_PREFIX
from apps.catalog.utils.manufacturer_brands import ensure_brand_category
from apps.catalog.utils.product_markup import apply_markup_percent, get_effective_product_markup

_DISCLAIMER_HTML = tuple(f"<p>{text}</p>" for text in DISCLAIMER.values())


def without_disclaimer(description: str) -> str:
    """Описание без оговорки БАДа; без оговорки — как было."""
    original = description or ""
    text = original
    for chunk in (*_DISCLAIMER_HTML, *DISCLAIMER.values()):
        text = text.replace(chunk, "")
    return text.strip() if text != original else original


_SUPPLEMENT_KEYWORDS = ("бад", "food supplement")


def _is_supplement_keyword(keyword: str) -> bool:
    text = keyword.strip().casefold()
    return any(text == word or text.startswith(word + " ") for word in _SUPPLEMENT_KEYWORDS)


def without_supplement_keywords(value):
    """Ключевые слова (список или строка через запятую) без «БАД …» / «food supplement …»."""
    if isinstance(value, list):
        return [item for item in value if not _is_supplement_keyword(str(item))]
    if not value:
        return value
    items = [item.strip() for item in str(value).split(",")]
    kept = [item for item in items if item and not _is_supplement_keyword(item)]
    return ", ".join(kept) if len(kept) != len([item for item in items if item]) else value


def markup_after(product, category, section_markup):
    """Наценка товара в новом разделе; section_markup — как если бы её записали разделу essential-oils."""
    if section_markup is None:
        return get_effective_product_markup(SimpleNamespace(brand=product.brand, category=category))[0]
    brand_margin, source = get_effective_product_markup(SimpleNamespace(brand=product.brand, category=None))
    if source == "brand":
        return brand_margin
    node = category
    while node is not None and node.slug != ROOT_SLUG:
        if node.margin_percent and node.margin_percent > 0:
            return Decimal(str(node.margin_percent))
        node = node.parent
    return section_markup


def find_candidates(product_ids):
    """[(Product, slug раздела)] — БАДы, которые правило считает эфирным маслом или гидролатом."""
    products = Product.objects.filter(product_type="supplements").select_related("category", "brand")
    if product_ids:
        products = products.filter(pk__in=product_ids)
    found = []
    for product in products.order_by("pk"):
        source_name = (product.external_data or {}).get("source_name") or product.name
        slug = essential_oil_category_slug(source_name, product.name)
        if slug:
            found.append((product, slug))
    return found


class Command(BaseCommand):
    help = "Переносит эфирные масла и гидролаты из БАДов в раздел «Эфирные масла» (тип incense)."

    def add_arguments(self, parser):
        parser.add_argument("--product", type=int, action="append", default=[], help="pk Product (можно несколько раз).")
        parser.add_argument("--apply", action="store_true", help="Изменить данные (иначе только показ).")
        parser.add_argument("--backup", default="", help="JSON-файл бэкапа (обязателен с --apply).")
        parser.add_argument(
            "--section-markup", type=Decimal, default=None,
            help="Наценка %% разделу essential-oils (чтобы цена на сайте не изменилась; записывается с --apply).",
        )
        parser.add_argument(
            "--allow-markup-change", action="store_true",
            help="Разрешить перенос, при котором меняется наценка (цена на сайте) — только по решению владельца.",
        )

    def handle(self, *args, **options):
        if options["apply"] and not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл>.")
        section_markup = options["section_markup"]
        if section_markup is not None and section_markup <= 0:
            raise CommandError("--section-markup должна быть больше нуля (ноль = «не задано», сработает общая).")
        candidates = find_candidates(options["product"])
        categories = {}
        for _product, slug in candidates:
            if slug not in categories:
                category = essential_oil_category(slug)
                if category is None or _resolve_product_type(category) != PRODUCT_TYPE:
                    raise CommandError(f"Нет активного раздела эфирных масел типа {PRODUCT_TYPE} для «{slug}».")
                categories[slug] = category

        supplements = {
            row.base_product_id: row
            for row in SupplementProduct.objects.filter(base_product_id__in=[p.pk for p, _ in candidates])
        }
        stats = Counter()
        markup_changes = Counter()
        self.stdout.write(
            "id | название | раздел сейчас → раздел | активен | в наличии | цена источника | "
            "цена с наценкой до → после | фото | оговорка БАДа"
        )
        for product, slug in candidates:
            before, _source = get_effective_product_markup(product)
            after = markup_after(product, categories[slug], section_markup)
            if before != after:
                markup_changes[f"{before}% → {after}%"] += 1
            supplement = supplements.get(product.pk)
            photos = supplement.gallery_images.count() if supplement else 0
            disclaimer = DISCLAIMER["ru"] in (product.description or "") or any(
                DISCLAIMER["ru"] in (text or "")
                for text in product.translations.values_list("description", flat=True)
            )
            stats["товаров"] += 1
            stats["в наличии"] += bool(product.is_active and product.is_available)
            stats["с оговоркой БАДа"] += disclaimer
            stats["без записи БАДа"] += supplement is None
            self.stdout.write(
                f"{product.pk} | {product.name} | {product.category.slug if product.category else '—'} → "
                f"{categories[slug].slug} | {'да' if product.is_active else 'нет'} | "
                f"{'да' if product.is_available else 'нет'} | {product.price} {product.currency} | "
                f"{apply_markup_percent(product.price or 0, before)} → {apply_markup_percent(product.price or 0, after)} "
                f"({before}% → {after}%) | {photos} | {'да' if disclaimer else 'нет'}"
            )
        self.stdout.write("Итого: " + ", ".join(f"{key} {value}" for key, value in stats.items()) if stats else "Итого: 0")
        self.stdout.write(
            "Наценка меняется: " + ", ".join(f"{key} — {value} шт." for key, value in markup_changes.items())
            if markup_changes else "Наценка (цена на сайте) не меняется."
        )

        if not options["apply"]:
            self.stdout.write("Dry-run: ничего не изменено. Для записи: --apply --backup <файл>.")
            return
        if markup_changes and not options["allow_markup_change"]:
            raise CommandError(
                "Цена на сайте изменится (наценка раздела). Нужен --section-markup <%> или, "
                "по решению владельца, --allow-markup-change."
            )
        section = Category.objects.filter(slug=ROOT_SLUG).first()
        if section is None and section_markup is not None:
            raise CommandError(f"Нет раздела {ROOT_SLUG} для --section-markup.")

        backup = [
            {
                "product": {
                    "id": product.pk,
                    "product_type": product.product_type,
                    "category_id": product.category_id,
                    "is_featured": product.is_featured,
                    "description": product.description,
                    "keywords": product.keywords,
                    "meta_keywords": product.meta_keywords,
                },
                "product_translations": list(product.translations.values("id", "description", "meta_keywords")),
                "supplement": (
                    {"pk": supplements[product.pk].pk, "is_active": supplements[product.pk].is_active,
                     "is_featured": supplements[product.pk].is_featured}
                    if product.pk in supplements else None
                ),
                "brand": (
                    {"id": product.brand_id, "category_slugs": product.brand.category_slugs,
                     "primary_category_slug": product.brand.primary_category_slug}
                    if product.brand_id else None
                ),
            }
            for product, _slug in candidates
        ]
        with open(options["backup"], "w", encoding="utf-8") as fh:
            json.dump({"section_margin_percent": str(section.margin_percent) if section else None, "products": backup},
                      fh, ensure_ascii=False, indent=1)

        if section is not None and section_markup is not None and section.margin_percent != section_markup:
            Category.objects.filter(pk=section.pk).update(margin_percent=section_markup)

        moved = Counter()
        for product, slug in candidates:
            with transaction.atomic():
                result = self._move(product, supplements.get(product.pk), categories[slug])
            moved["товаров"] += 1
            moved["фото"] += result["gallery"]
        self.stdout.write(self.style.SUCCESS(
            f"Перенесено товаров: {moved['товаров']}, фото: {moved['фото']}. Бэкап: {options['backup']}"
        ))

    def _move(self, product, supplement, category):
        incense = IncenseProduct.objects.filter(base_product_id=product.pk).first()
        if incense is None:
            values = _base_product_to_domain_kwargs(product)
            if supplement:
                values.update(_copied_values(supplement, IncenseProduct, {"base_product", "created_at", "updated_at"}))
            # Карточку находит по slug Product (product_resolve), поэтому slug — как у Product.
            values.update(name=product.name, slug=product.slug, base_product_id=product.pk)
            if IncenseProduct.objects.filter(slug=values["slug"]).exists():
                raise CommandError(f"Product {product.pk}: slug {values['slug']} уже занят другим товаром-благовонием.")
            # bulk_create — без save(): тот синхронизировал бы в Product пустые RU SEO новой записи.
            incense = IncenseProduct.objects.bulk_create([IncenseProduct(**values)])[0]
            if supplement:
                IncenseProductTranslation.objects.bulk_create([
                    IncenseProductTranslation(product=incense, **_copied_values(row, IncenseProductTranslation, {"product"}))
                    for row in supplement.translations.all()
                ])

        Product.objects.filter(pk=product.pk).update(
            product_type=PRODUCT_TYPE, category=category, is_featured=False,
            description=without_disclaimer(product.description),
            keywords=without_supplement_keywords(product.keywords),
            meta_keywords=without_supplement_keywords(product.meta_keywords),
            updated_at=timezone.now(),
        )
        IncenseProduct.objects.filter(pk=incense.pk).update(
            category=category, is_featured=False, description=without_disclaimer(incense.description),
            meta_keywords=without_supplement_keywords(incense.meta_keywords),
        )
        for model, owner in ((ProductTranslation, product.pk), (IncenseProductTranslation, incense.pk)):
            for row in model.objects.filter(product_id=owner):
                changes = {
                    "description": without_disclaimer(row.description),
                    "meta_keywords": without_supplement_keywords(row.meta_keywords),
                }
                changes = {field: value for field, value in changes.items() if value != getattr(row, field)}
                if changes:
                    model.objects.filter(pk=row.pk).update(**changes)

        product.refresh_from_db()
        report = retire_stale_domain_records(product)
        if supplement:
            SupplementProduct.objects.filter(pk=supplement.pk).update(is_featured=False)
        if product.brand and ensure_brand_category(product.brand, PRODUCT_TYPE):
            product.brand.save(update_fields=["category_slugs", "primary_category_slug"])
        cache.delete(RESOLVE_CACHE_PREFIX + product.slug)
        return {"gallery": sum(row["gallery"] for row in report)}
