"""Перенести эфирные масла и гидролаты из БАДов в раздел «Эфирные масла» (dry-run по умолчанию).

ilacfiyati.com держит линейку PHYTOIL (эфирные масла, гидролаты, цветочные воды
Elentra İlaç) среди БАДов, и они сохранялись у нас БАДами: в описании карточки
стояло «Биологически активная добавка к пище», а семантическая проверка AI
отклоняла тексты (title_category_mismatch, supplement_health_claim). Правило
отбора — catalog.essential_oils.

    manage.py move_essential_oils_from_supplements                       # показ
    manage.py move_essential_oils_from_supplements --product 23956       # показ по товару
    manage.py move_essential_oils_from_supplements --apply --backup /backups/essential-oils.json

С товаром (одна транзакция на товар):
1. создаётся IncenseProduct — копия общих полей SupplementProduct (цена, наличие,
   главное фото, EN SEO, внешние данные) и его переводов; категория — раздел масел;
2. Product: product_type=incense и та же категория через update(). save() здесь
   нельзя: новая доменная запись синхронизировала бы в Product пустые RU SEO;
3. domain_sync.retire_stale_domain_records: галерея БАДа копируется в новую запись,
   SupplementProduct снимается с публикации (is_active=False, не удаляется);
4. из описаний (Product, его переводы, новая запись и её переводы) убирается
   абзац-оговорка БАДа (ai.services.supplement_content.DISCLAIMER);
5. «Хит продаж» снимается (только лекарства и БАДы), бренду добавляется тип incense.

Slug и адрес карточки не меняются (/product/<slug> у обоих типов). ProductSourceOffer,
цены в валютах, корзины и заказы ссылаются на Product и не трогаются. Атрибуты БАДа
(форма, вещество, порция) остаются у снятой записи. Название и SEO не переписываются:
их обновит повторная AI-обработка уже как масла.

Откат по бэкапу: IncenseProduct.objects.filter(pk__in=…).delete() — через queryset,
не instance.delete() (тот удалил бы и Product; файлы не удалятся — на них ссылается
запись БАДа), затем вернуть Product (product_type, category_id, is_featured,
description), описания ProductTranslation, is_active/is_featured SupplementProduct и
category_slugs/primary_category_slug бренда.
"""
import json
from collections import Counter

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
from apps.catalog.essential_oils import PRODUCT_TYPE, essential_oil_category, essential_oil_category_slug
from apps.catalog.models import (
    IncenseProduct,
    IncenseProductTranslation,
    Product,
    ProductTranslation,
    SupplementProduct,
)
from apps.catalog.scraper_category_mapping import _resolve_product_type
from apps.catalog.services.product_resolve import RESOLVE_CACHE_PREFIX
from apps.catalog.utils.manufacturer_brands import ensure_brand_category

_DISCLAIMER_HTML = tuple(f"<p>{text}</p>" for text in DISCLAIMER.values())


def without_disclaimer(description: str) -> str:
    """Описание без оговорки БАДа; без оговорки — как было."""
    original = description or ""
    text = original
    for chunk in (*_DISCLAIMER_HTML, *DISCLAIMER.values()):
        text = text.replace(chunk, "")
    return text.strip() if text != original else original


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

    def handle(self, *args, **options):
        if options["apply"] and not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл>.")
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
        self.stdout.write("id | название | раздел сейчас → раздел | активен | в наличии | цена | фото | оговорка БАДа")
        for product, slug in candidates:
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
                f"{photos} | {'да' if disclaimer else 'нет'}"
            )
        self.stdout.write("Итого: " + ", ".join(f"{key} {value}" for key, value in stats.items()) if stats else "Итого: 0")

        if not options["apply"]:
            self.stdout.write("Dry-run: ничего не изменено. Для записи: --apply --backup <файл>.")
            return

        backup = [
            {
                "product": {
                    "id": product.pk,
                    "product_type": product.product_type,
                    "category_id": product.category_id,
                    "is_featured": product.is_featured,
                    "description": product.description,
                },
                "product_translations": list(product.translations.values("id", "description")),
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
            json.dump(backup, fh, ensure_ascii=False, indent=1)

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
            description=without_disclaimer(product.description), updated_at=timezone.now(),
        )
        IncenseProduct.objects.filter(pk=incense.pk).update(
            category=category, is_featured=False, description=without_disclaimer(incense.description),
        )
        for model, owner in ((ProductTranslation, product.pk), (IncenseProductTranslation, incense.pk)):
            for row in model.objects.filter(product_id=owner):
                cleaned = without_disclaimer(row.description)
                if cleaned != (row.description or ""):
                    model.objects.filter(pk=row.pk).update(description=cleaned)

        product.refresh_from_db()
        report = retire_stale_domain_records(product)
        if supplement:
            SupplementProduct.objects.filter(pk=supplement.pk).update(is_featured=False)
        if product.brand and ensure_brand_category(product.brand, PRODUCT_TYPE):
            product.brand.save(update_fields=["category_slugs", "primary_category_slug"])
        cache.delete(RESOLVE_CACHE_PREFIX + product.slug)
        return {"gallery": sum(row["gallery"] for row in report)}
