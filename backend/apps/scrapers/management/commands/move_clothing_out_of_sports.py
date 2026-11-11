"""Одежда — из «Спорттоваров» в свой раздел (решение владельца 11.11.2026: спорттовары —
снаряды и предметы, костюмы и другая одежда к ним не относятся). Показ по умолчанию;
запись — ``--apply --backup``; откат — ``--rollback``. Без сети.

Что переносится:
- товары SuperStep типа «спорттовары», которым раскладка парсера даёт раздел другого
  типа (``SuperstepParser.subgroup_route`` + ``route_categories``): спортивные костюмы
  попали в «Спорттовары», потому что раздел ``tracksuits`` лежит под ними;
- товары, названные явно: ``--move <id товара>:<slug раздела>`` (бриджи из Instagram,
  полотенца — куда решит владелец).

``--move-section tracksuits:suits`` сначала переносит сам раздел под другого родителя
(адрес ``/categories/tracksuits`` не меняется) и переносит все его товары другого типа.
Раздел с подразделами не переносится.

С товаром: создаётся доменная запись нового типа — копия общих полей прежней (цена,
наличие, главное фото, SEO) и её переводов; ``Product`` получает тип и раздел через
``update()``; ``retire_stale_domain_records`` снимает прежнюю запись с публикации (не
удаляет). Slug и адрес карточки не меняются; переводы ``Product``, предложения источника,
корзины и заказы ссылаются на ``Product`` и не трогаются.

Цветов и размеров у костюмов в «Спорттоварах» не было: тип их не хранит, карточка
показывала один цвет без выбора размера. Ответ парсера с цветами и размерами сохранён в
``external_data`` — команда создаёт по нему варианты (``_sync_fashion_variants``, без
фото), а фото прежней записи отдаёт варианту главного цвета. Фото остальных цветов и
свежее наличие даст повторный сбор этих карточек по ссылке (команда печатает ссылки).
У товара без сохранённых цветов (Instagram) галерея копируется как есть.

Наценка считается от раздела: если в новом разделе она другая, цена на сайте изменится —
показ печатает обе, ``--apply`` требует ``--allow-markup-change``.

    manage.py move_clothing_out_of_sports
    manage.py move_clothing_out_of_sports --move-section tracksuits:suits
    manage.py move_clothing_out_of_sports --move 15390:shorts --move 15406:shorts
    manage.py move_clothing_out_of_sports --apply --backup /backups/sports-clothing-move.json
    manage.py move_clothing_out_of_sports --rollback /backups/sports-clothing-move.json

Поисковый индекс перенесённых товаров пересчитывается сам (``schedule_reindex``).
Откат возвращает тип, раздел и прежнюю доменную запись; созданная запись нового типа не
удаляется, а снимается с публикации (её фото и варианты остаются).
"""
import json
from types import SimpleNamespace

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.domain_sync import (
    _GALLERY_RELATIONS,
    _base_product_to_domain_kwargs,
    _child_relation,
    _copied_values,
    _copy_children,
    _ordered,
    domain_models,
    retire_stale_domain_records,
)
from apps.catalog.models import Category, Product
from apps.catalog.product_search import schedule_reindex
from apps.catalog.scraper_category_mapping import _resolve_product_type, route_categories
from apps.catalog.services.cross_source_duplicates import resolve_for_products
from apps.catalog.services.product_resolve import RESOLVE_CACHE_PREFIX
from apps.catalog.utils.manufacturer_brands import ensure_brand_category
from apps.catalog.utils.product_markup import apply_markup_percent, get_effective_product_markup
from apps.scrapers.parsers.superstep import SuperstepParser
from apps.scrapers.services import ScraperIntegrationService

SPORTS_TYPE = "sports"


def _pair(value, what):
    left, _, right = str(value).partition(":")
    if not left or not right:
        raise CommandError(f"{what}: нужны два значения через двоеточие, получено «{value}».")
    return left, right


def _type_key(product_type):
    return str(product_type or "").replace("-", "_")


def move_product(product, category):
    """Переносит товар в раздел другого типа; возвращает строку бэкапа."""
    models = domain_models()
    target_type = _resolve_product_type(category)
    target_model = models[target_type]
    source_model = models.get(_type_key(product.product_type))
    source = source_model.objects.filter(base_product_id=product.pk).first() if source_model else None
    row = {
        "product_id": product.pk,
        "product_type": product.product_type,
        "category_id": product.category_id,
        "source": {"type": _type_key(product.product_type), "pk": source.pk, "is_active": source.is_active} if source else None,
    }

    target = target_model.objects.filter(base_product_id=product.pk).first()
    if target is None:
        values = _copied_values(source, target_model, {"base_product", "created_at", "updated_at"}) if source else {}
        # То, что показывает сайт, — из Product: save() доменной записи пишет её поля обратно в Product.
        values.update(_base_product_to_domain_kwargs(product))
        values.update(category_id=category.pk, gender=values["gender"] or getattr(source, "gender", "") or "")
        for field, shown in (
            ("meta_title", product.seo_title),
            ("meta_description", product.seo_description),
            ("meta_keywords", ", ".join(product.keywords or [])),
        ):
            values[field] = values.get(field) or shown or ""
        if target_model.objects.filter(slug=product.slug).exists():
            raise CommandError(f"Товар {product.pk}: slug {product.slug} уже занят в «{target_model._meta.verbose_name}».")
        fields = {name for field in target_model._meta.concrete_fields for name in (field.name, field.attname)}
        # bulk_create — без save(): запись создаётся молча, тип и раздел Product ставит update() ниже.
        target = target_model.objects.bulk_create(
            [target_model(**{key: value for key, value in values.items() if key in fields})]
        )[0]
        translations = _child_relation(target_model, ("translations",))
        if source and translations and _child_relation(source_model, ("translations",)):
            _name, translation_model, parent_field = translations
            translation_model.objects.bulk_create([
                translation_model(**_copied_values(item, translation_model, {parent_field}), **{parent_field: target})
                for item in source.translations.all()
            ])
    else:
        target_model.objects.filter(pk=target.pk).update(category=category, is_active=product.is_active)
    row["target"] = {"type": target_type, "pk": target.pk}

    Product.objects.filter(pk=product.pk).update(
        product_type=target_type, category=category, updated_at=timezone.now(),
    )
    product.refresh_from_db()
    row["variants"] = _restore_colour_variants(product, source, target)
    product.refresh_from_db()
    report = retire_stale_domain_records(product)
    row["gallery"] = sum(item["gallery"] for item in report)
    if product.brand and ensure_brand_category(product.brand, target_type):
        product.brand.save(update_fields=["category_slugs", "primary_category_slug"])
    cache.delete(RESOLVE_CACHE_PREFIX + product.slug)
    return row


def _restore_colour_variants(product, source, target) -> int:
    """Цвета и размеры из сохранённого ответа парсера (``fashion_variants``) — без сети.

    Спорттовар их не хранит, но ответ парсера лежит в ``external_data``. Фото прежней
    записи — это фото главного цвета: они уходят в его вариант, а не в общую галерею
    (у одежды галерея — у вариантов, иначе после повторного сбора фото задвоились бы).
    Фото остальных цветов скачает повторный сбор карточки.
    """
    specs = ((product.external_data or {}).get("attributes") or {}).get("fashion_variants")
    service = ScraperIntegrationService()
    if not isinstance(specs, list) or not specs or not service._fashion_model_config(product.product_type):
        return 0
    if target.variants.exists():
        return 0
    service._sync_fashion_variants(
        product, variants=[{**spec, "images": []} for spec in specs if isinstance(spec, dict)],
    )
    variants = list(target.variants.order_by("sort_order", "pk"))
    gallery = _child_relation(type(source), _GALLERY_RELATIONS) if source else None
    if variants and gallery:
        main = next((v for v in variants if v.external_url and v.external_url == product.external_url), variants[0])
        _copy_children(list(_ordered(getattr(source, gallery[0]))), _child_relation(type(main), ("images",)), main)
        type(main).objects.filter(pk=main.pk).update(
            main_image=source.main_image or "", main_image_file=getattr(source.main_image_file, "name", "") or "",
        )
    return len(variants)


class Command(BaseCommand):
    help = "Переносит одежду из «Спорттоваров» в раздел её типа (по умолчанию — только показ)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Перенести.")
        parser.add_argument("--backup", default="", help="JSON-файл бэкапа (обязателен с --apply).")
        parser.add_argument("--rollback", default="", help="Вернуть как было по файлу бэкапа.")
        parser.add_argument(
            "--move", action="append", default=[], metavar="ID:SLUG",
            help="Товар и раздел, куда его перенести (можно несколько раз).",
        )
        parser.add_argument(
            "--move-section", default="", metavar="SLUG:PARENT",
            help="Сначала перенести раздел под другого родителя (решение владельца).",
        )
        parser.add_argument(
            "--allow-markup-change", action="store_true",
            help="Разрешить перенос, при котором меняется наценка (цена на сайте) — по решению владельца.",
        )

    def handle(self, *args, **options):
        if options["rollback"]:
            return self._rollback(options["rollback"])
        if options["apply"] and not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл>.")
        with transaction.atomic():
            backup = self._run(options)
            if backup is None:
                # Показ: перенос раздела был нужен только для расчёта — откатываем.
                transaction.set_rollback(True)
                return
            with open(options["backup"], "w", encoding="utf-8") as fh:
                json.dump(backup, fh, ensure_ascii=False, indent=1)
        self.stdout.write(self.style.SUCCESS(
            f"Перенесено товаров: {len(backup['products'])}, фото: {sum(r['gallery'] for r in backup['products'])}. "
            f"Бэкап: {options['backup']}. Дальше: повторный сбор ссылок выше (фото остальных цветов, свежее наличие)."
        ))

    def _run(self, options):
        """Показ плана; с --apply — перенос. Возвращает бэкап или None (показ / нечего делать)."""
        section_backup = self._move_section(options["move_section"]) if options["move_section"] else None
        plan, skipped = self._plan(options["move"], section_backup)

        markup_changes = 0
        self.stdout.write("id | название | тип → тип | раздел → раздел | цена с наценкой до → после | ссылка источника")
        for product, target in plan:
            before = get_effective_product_markup(product)[0]
            after = get_effective_product_markup(SimpleNamespace(brand=product.brand, category=target))[0]
            markup_changes += before != after
            self.stdout.write(
                f"{product.pk} | {product.name} | {product.product_type} → {_resolve_product_type(target)} | "
                f"{product.category.slug if product.category else '—'} → {target.slug} | "
                f"{apply_markup_percent(product.price or 0, before)} → {apply_markup_percent(product.price or 0, after)} "
                f"({before}% → {after}%) | {product.external_url or '—'}"
            )
        for line in skipped:
            self.stdout.write(f"  пропущено: {line}")
        self.stdout.write(f"К переносу: {len(plan)}. Наценка меняется у {markup_changes}.")
        if not plan or not options["apply"]:
            if plan:
                self.stdout.write("Показ: ничего не изменено. Для записи: --apply --backup <файл>.")
            return None
        if markup_changes and not options["allow_markup_change"]:
            raise CommandError("Цена на сайте изменится (наценка раздела): нужен --allow-markup-change по решению владельца.")
        rows = [move_product(product, target) for product, target in plan]
        ids = [row["product_id"] for row in rows]
        # Появились цвета с ценой и наличием — как после сбора (правило о дублях FLO ↔ SuperStep).
        resolve_for_products(ids)
        schedule_reindex(ids)
        return {"section": section_backup, "products": rows}

    def _move_section(self, value):
        slug, parent_slug = _pair(value, "--move-section")
        section = Category.objects.filter(slug=slug).first()
        parent = Category.objects.filter(slug=parent_slug, is_active=True).first()
        if section is None or parent is None:
            raise CommandError(f"--move-section: нет раздела «{slug}» или активного родителя «{parent_slug}».")
        if section.children.exists():
            raise CommandError(f"--move-section: у раздела «{slug}» есть подразделы — переносите вручную.")
        backup = {"id": section.pk, "parent_id": section.parent_id, "category_type_id": section.category_type_id}
        node, category_type_id = parent, None
        while node is not None and category_type_id is None:
            category_type_id, node = node.category_type_id, node.parent
        Category.objects.filter(pk=section.pk).update(parent=parent, category_type_id=category_type_id)
        self.stdout.write(f"Раздел «{section.name}» ({slug}): родитель → «{parent.name}» ({parent_slug}).")
        return backup

    def _plan(self, explicit, section_backup):
        """([(товар, раздел)], [причины пропуска])."""
        models = domain_models()
        targets, skipped = {}, []

        def add(product, target):
            if _resolve_product_type(target) not in models:
                skipped.append(f"{product.pk}: у раздела {target.slug} нет типа товара с карточкой")
            elif _type_key(product.product_type) == _resolve_product_type(target) and product.category_id == target.pk:
                skipped.append(f"{product.pk}: уже в разделе {target.slug}")
            elif _type_key(product.product_type) == _resolve_product_type(target):
                skipped.append(f"{product.pk}: тип тот же — раздел меняется в админке, не этой командой")
            else:
                targets[product.pk] = (product, target)

        products = Product.objects.select_related("category", "brand")
        for product in products.filter(external_id__startswith="superstep-", product_type=SPORTS_TYPE).order_by("pk"):
            attrs = (product.external_data or {}).get("attributes") or {}
            _, route = SuperstepParser.subgroup_route(
                attrs.get("superstep_subgroup") or "", product.name,
                product.brand.name if product.brand_id else "", attrs.get("gender") or "",
            )
            found = route_categories(route)
            target = next((found[slug] for slug in route if slug in found), None)
            if target is not None and _resolve_product_type(target) != SPORTS_TYPE:
                add(product, target)
        if section_backup:
            section = Category.objects.select_related("category_type", "parent").get(pk=section_backup["id"])
            for product in products.filter(category=section).order_by("pk"):
                if _type_key(product.product_type) != _resolve_product_type(section):
                    add(product, section)
        for value in explicit:
            product_id, slug = _pair(value, "--move")
            product = products.filter(pk=product_id).first() if product_id.isdigit() else None
            target = Category.objects.filter(slug=slug, is_active=True).first()
            if product is None or target is None:
                raise CommandError(f"--move {value}: нет товара или активного раздела.")
            add(product, target)
        return list(targets.values()), skipped

    def _rollback(self, path):
        with open(path, encoding="utf-8") as fh:
            backup = json.load(fh)
        models = domain_models()
        with transaction.atomic():
            for row in backup["products"]:
                Product.objects.filter(pk=row["product_id"]).update(
                    product_type=row["product_type"], category_id=row["category_id"], updated_at=timezone.now(),
                )
                # Запись нового типа не удаляется (на её фото и варианты есть ссылки) — снимается.
                models[row["target"]["type"]].objects.filter(pk=row["target"]["pk"]).update(is_active=False)
                if row["source"]:
                    models[row["source"]["type"]].objects.filter(pk=row["source"]["pk"]).update(
                        is_active=row["source"]["is_active"], category_id=row["category_id"],
                    )
                slug = Product.objects.filter(pk=row["product_id"]).values_list("slug", flat=True).first()
                cache.delete(RESOLVE_CACHE_PREFIX + (slug or ""))
            section = backup.get("section")
            if section:
                Category.objects.filter(pk=section["id"]).update(
                    parent_id=section["parent_id"], category_type_id=section["category_type_id"],
                )
            schedule_reindex([row["product_id"] for row in backup["products"]])
        self.stdout.write(self.style.SUCCESS(f"Возвращено товаров: {len(backup['products'])}."))
