"""Перенести заданные товары из БАДов в раздел лекарств (dry-run по умолчанию).

ilacfiyati.com держит в «Takviye edici gıda» и то, что БАДом не является: глазные капли
(CACICOL), назальные спреи и промывание носа, пластыри, наружные средства. Парсер сохранял
их БАДами. Владелец 20.11.2026 утвердил список таких товаров — их место в разделе лекарств.
Автоотбора нет: переносится только то, что названо в --product.

    manage.py move_supplements_to_medicines --product 7237 --product 24477      # показ
    manage.py move_supplements_to_medicines --product 7237 --product 24477 \
        --apply --allow-markup-change --backup /backups/supp-to-meds.json

С товаром (одна транзакция на товар):
1. создаётся MedicineProduct — копия общих полей SupplementProduct (цена, наличие, главное
   фото, форма выпуска, вещество, EN SEO, внешние данные) и его переводов; категория — корень
   «Лекарства» (slug medicines). ATC, тип рецепта, поля SGK остаются пустыми — в источнике их нет;
2. Product: product_type=medicines, та же категория и метка
   external_data["moved_from_supplements"] через update(). save() здесь нельзя: новая
   доменная запись синхронизировала бы в Product пустые RU SEO;
3. domain_sync.retire_stale_domain_records: галерея БАДа копируется в новую запись,
   SupplementProduct снимается с публикации (is_active=False, не удаляется);
4. из описаний (Product, его переводы, новая запись и её переводы) убирается абзац-оговорка
   БАДа, из ключевых слов — «БАД …» / «food supplement …»;
5. «Хит продаж» снимается (лекарства в хиты не входят), бренду добавляется тип medicines;
6. остаток 0 у товара «в наличии» сбрасывается в «не задан»: у БАДов заявка остаток не
   смотрит, а лекарство с остатком 0 в «Список заявки» не добавить; отметка «ввоз ограничен»
   считается по веществу, как при обычном сохранении лекарства.

Метка moved_from_supplements — защита от возврата: источник по-прежнему отдаёт товар в
разделе БАДов, и задача парсера с подразделом БАДов иначе вернула бы ему категорию и тип
(scrapers.services._category_changes_domain). Обычный обход раздела обновляет цену, наличие
и пустые поля записи лекарства (штрихкод, производитель) и тип не трогает.

Наценка = цена на сайте. Она считается от раздела (utils.product_markup): у БАДов — процент
корня «БАДы», у лекарств — шкала раздела «Лекарства». Показ печатает цену с наценкой до и
после; --apply отказывает, если наценка меняется, пока не указан --allow-markup-change
(решение владельца).

Slug и адрес карточки не меняются (/product/<slug> у обоих типов). ProductSourceOffer, цены
в валютах, корзины и заявки ссылаются на Product и не трогаются. Название и SEO не
переписываются. Повторный запуск уже перенесённые товары пропускает. После записи —
rebuild_product_search_index --ids <id,…> --apply (update() сигналы поиска обходит).

Откат по бэкапу: MedicineProduct.objects.filter(base_product_id__in=…).delete() — через
queryset, не instance.delete() (тот удалил бы и Product; файлы не удалятся — на них
ссылается запись БАДа), затем вернуть Product (product_type, category_id, is_featured,
stock_quantity, description, keywords, meta_keywords) и убрать из его external_data ключ
moved_from_supplements, вернуть описания и meta_keywords ProductTranslation,
is_active/is_featured SupplementProduct, category_slugs/primary_category_slug бренда.
"""
import json
from collections import Counter
from types import SimpleNamespace

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.ai.services.supplement_content import DISCLAIMER
from apps.catalog.controlled_substances import refresh_medicine
from apps.catalog.domain_sync import (
    MOVED_FROM_SUPPLEMENTS_KEY,
    _base_product_to_domain_kwargs,
    _copied_values,
    retire_stale_domain_records,
)
from apps.catalog.management.commands.move_essential_oils_from_supplements import (
    strip_supplement_wording_from_translations,
    without_disclaimer,
    without_supplement_keywords,
)
from apps.catalog.models import (
    DOSAGE_FORM_CHOICES,
    Category,
    MedicineProduct,
    MedicineProductTranslation,
    Product,
    ProductTranslation,
    SupplementProduct,
)
from apps.catalog.scraper_category_mapping import _resolve_product_type
from apps.catalog.services.product_resolve import RESOLVE_CACHE_PREFIX
from apps.catalog.utils.manufacturer_brands import ensure_brand_category
from apps.catalog.utils.product_markup import apply_markup_percent, get_effective_product_markup

PRODUCT_TYPE = "medicines"
ROOT_SLUG = "medicines"
_DOSAGE_FORMS = {code for code, _label in DOSAGE_FORM_CHOICES}


def is_moved(product) -> bool:
    external = product.external_data if isinstance(product.external_data, dict) else {}
    return product.product_type == PRODUCT_TYPE and bool(external.get(MOVED_FROM_SUPPLEMENTS_KEY))


def legacy_zero_stock(product) -> bool:
    """«В наличии» при остатке 0 — наследие импорта БАДов. Заявка БАДа остаток не смотрит
    (подтверждает поставщик), а лекарство с остатком 0 в «Список заявки» не добавить.
    Парсер ilacfiyati остаток не ведёт (None) — приводим к тому же."""
    return bool(product.is_available and product.stock_quantity == 0)


class Command(BaseCommand):
    help = "Переносит заданные товары из БАДов в раздел лекарств (тип medicines)."

    def add_arguments(self, parser):
        parser.add_argument("--product", type=int, action="append", default=[], help="pk Product (можно несколько раз).")
        parser.add_argument("--apply", action="store_true", help="Изменить данные (иначе только показ).")
        parser.add_argument("--backup", default="", help="JSON-файл бэкапа (обязателен с --apply).")
        parser.add_argument(
            "--allow-markup-change", action="store_true",
            help="Разрешить перенос, при котором меняется наценка (цена на сайте) — только по решению владельца.",
        )

    def handle(self, *args, **options):
        ids = list(dict.fromkeys(options["product"]))
        if not ids:
            raise CommandError("Нужен хотя бы один --product <id>: автоотбора нет.")
        if options["apply"] and not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл>.")
        category = Category.objects.filter(slug=ROOT_SLUG, parent__isnull=True, is_active=True).first()
        if category is None or _resolve_product_type(category) != PRODUCT_TYPE:
            raise CommandError(f"Нет активного корневого раздела лекарств ({ROOT_SLUG}).")

        found = Product.objects.select_related("category", "brand").in_bulk(ids)
        missing = [pk for pk in ids if pk not in found]
        if missing:
            raise CommandError(f"Нет товаров с id: {', '.join(map(str, missing))}.")
        already = [found[pk] for pk in ids if is_moved(found[pk])]
        products = [found[pk] for pk in ids if not is_moved(found[pk])]
        wrong_type = [product for product in products if product.product_type != "supplements"]
        if wrong_type:
            raise CommandError("Не БАДы, не переношу: " + ", ".join(
                f"{product.pk} ({product.product_type})" for product in wrong_type
            ))
        # Запись лекарства у БАДа или занятый slug — состояние, которое команда сама не создаёт:
        # разбирать вручную, а не угадывать.
        taken = MedicineProduct.objects.filter(base_product_id__in=[product.pk for product in products])
        if taken.exists():
            raise CommandError("У БАДа уже есть запись лекарства: Product " + ", ".join(
                str(pk) for pk in taken.values_list("base_product_id", flat=True)
            ))
        busy = MedicineProduct.objects.filter(slug__in=[product.slug for product in products])
        if busy.exists():
            raise CommandError("Slug уже занят другим лекарством: " + ", ".join(busy.values_list("slug", flat=True)))

        supplements = {
            row.base_product_id: row
            for row in SupplementProduct.objects.filter(base_product_id__in=[product.pk for product in products])
        }
        stats = Counter()
        markup_changes = Counter()
        self.stdout.write(
            "id | название | раздел сейчас → раздел | активен | в наличии | цена источника | "
            "цена с наценкой до → после | фото | оговорка БАДа"
        )
        for product in already:
            self.stdout.write(f"{product.pk} | {product.name} | уже перенесён, пропускаю")
        for product in products:
            before, _source = get_effective_product_markup(product)
            moved = SimpleNamespace(brand=product.brand, category=category, product_type=PRODUCT_TYPE)
            after, _source = get_effective_product_markup(moved, product.price, product.currency)
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
            stats["остаток 0 → не задан"] += legacy_zero_stock(product)
            self.stdout.write(
                f"{product.pk} | {product.name} | {product.category.slug if product.category else '—'} → "
                f"{category.slug} | {'да' if product.is_active else 'нет'} | "
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
                "Цена на сайте изменится (наценка раздела). По решению владельца — --allow-markup-change."
            )

        backup = [
            {
                "product": {
                    "id": product.pk,
                    "product_type": product.product_type,
                    "category_id": product.category_id,
                    "is_featured": product.is_featured,
                    "stock_quantity": product.stock_quantity,
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
            for product in products
        ]
        with open(options["backup"], "w", encoding="utf-8") as fh:
            json.dump({"products": backup}, fh, ensure_ascii=False, indent=1)

        moved = Counter()
        for product in products:
            with transaction.atomic():
                moved["фото"] += self._move(product, supplements.get(product.pk), category)
            moved["товаров"] += 1
        self.stdout.write(self.style.SUCCESS(
            f"Перенесено товаров: {moved['товаров']}, фото: {moved['фото']}. Бэкап: {options['backup']}"
        ))

    def _move(self, product, supplement, category) -> int:
        external = dict(product.external_data) if isinstance(product.external_data, dict) else {}
        external[MOVED_FROM_SUPPLEMENTS_KEY] = timezone.now().date().isoformat()

        values = _base_product_to_domain_kwargs(product)
        if supplement:
            values.update(_copied_values(supplement, MedicineProduct, {"base_product", "created_at", "updated_at"}))
        # Карточку находит по slug Product (product_resolve), поэтому slug — как у Product.
        values.update(
            name=product.name, slug=product.slug, base_product_id=product.pk, category_id=category.pk,
            is_featured=False, description=without_disclaimer(values["description"]),
            meta_keywords=without_supplement_keywords(values.get("meta_keywords", "")),
            external_data={**(values.get("external_data") or {}), MOVED_FROM_SUPPLEMENTS_KEY: external[MOVED_FROM_SUPPLEMENTS_KEY]},
        )
        if product.is_available and values.get("stock_quantity") == 0:
            values["stock_quantity"] = None
        medicine = MedicineProduct(**values)
        # Отметка «ввоз ограничен» по веществу: её ставит сигнал save(), а bulk_create его обходит.
        refresh_medicine(medicine)
        # bulk_create — без save(): тот синхронизировал бы в Product пустые RU SEO новой записи.
        medicine = MedicineProduct.objects.bulk_create([medicine])[0]
        translations = []
        for row in supplement.translations.all() if supplement else []:
            data = _copied_values(row, MedicineProductTranslation, {"product"})
            # У перевода БАДа форма и вещество — свободный текст длиннее полей лекарства.
            if data.get("dosage_form") not in _DOSAGE_FORMS:
                data["dosage_form"] = ""
            data["active_ingredient"] = (data.get("active_ingredient") or "")[:300]
            translations.append(MedicineProductTranslation(product=medicine, **data))
        MedicineProductTranslation.objects.bulk_create(translations)

        Product.objects.filter(pk=product.pk).update(
            product_type=PRODUCT_TYPE, category=category, is_featured=False,
            description=without_disclaimer(product.description),
            keywords=without_supplement_keywords(product.keywords),
            meta_keywords=without_supplement_keywords(product.meta_keywords),
            external_data=external, updated_at=timezone.now(),
            **({"stock_quantity": None} if legacy_zero_stock(product) else {}),
        )
        strip_supplement_wording_from_translations(ProductTranslation, product.pk)
        strip_supplement_wording_from_translations(MedicineProductTranslation, medicine.pk)

        product.refresh_from_db()
        report = retire_stale_domain_records(product)
        if supplement:
            SupplementProduct.objects.filter(pk=supplement.pk).update(is_featured=False)
        if product.brand and ensure_brand_category(product.brand, PRODUCT_TYPE):
            product.brand.save(update_fields=["category_slugs", "primary_category_slug"])
        cache.delete(RESOLVE_CACHE_PREFIX + product.slug)
        return sum(row["gallery"] for row in report)
