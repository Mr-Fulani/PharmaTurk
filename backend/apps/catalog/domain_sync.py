"""
Синхронизация Product с доменными моделями (PerfumeryProduct, MedicineProduct и т.д.).

При создании/обновлении Product через скраперы или импорт автоматически создаётся
соответствующая запись в доменной таблице (если её ещё нет) и копируются общие поля.
Так товары попадают в нужные разделы админки и в правильные API-эндпоинты.
"""

import logging

from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.db.models.fields.files import FieldFile
from django.utils import timezone

logger = logging.getLogger(__name__)

# Маппинг product_type (из Product) -> (модель, related_name на Product)
# Только типы, у которых есть доменная модель с base_product.
PRODUCT_TYPE_TO_DOMAIN = None


def _get_domain_map():
    """Ленивая загрузка маппинга, чтобы избежать циклических импортов."""
    global PRODUCT_TYPE_TO_DOMAIN
    if PRODUCT_TYPE_TO_DOMAIN is not None:
        return PRODUCT_TYPE_TO_DOMAIN
    from .models import (
        AccessoryProduct,
        AutoPartProduct,
        BookProduct,
        ClothingProduct,
        ElectronicsProduct,
        FurnitureProduct,
        IncenseProduct,
        JewelryProduct,
        MedicalEquipmentProduct,
        MedicineProduct,
        PerfumeryProduct,
        ShoeProduct,
        SportsProduct,
        SupplementProduct,
        TablewareProduct,
    )
    m = {
        "clothing": (ClothingProduct, "clothing_item"),
        "shoes": (ShoeProduct, "shoe_item"),
        "electronics": (ElectronicsProduct, "electronics_item"),
        "furniture": (FurnitureProduct, "furniture_item"),
        "jewelry": (JewelryProduct, "jewelry_item"),
        "books": (BookProduct, "book_item"),
        "perfumery": (PerfumeryProduct, "perfumery_item"),
        "medicines": (MedicineProduct, "medicine_item"),
        "supplements": (SupplementProduct, "supplement_item"),
        "medical_equipment": (MedicalEquipmentProduct, "medical_equipment_item"),
        "tableware": (TablewareProduct, "tableware_item"),
        "accessories": (AccessoryProduct, "accessory_item"),
        "incense": (IncenseProduct, "incense_item"),
        "sports": (SportsProduct, "sports_item"),
        "auto_parts": (AutoPartProduct, "auto_part_item"),
    }
    globals()["PRODUCT_TYPE_TO_DOMAIN"] = m
    return m


def _base_product_to_domain_kwargs(product):
    """Собирает общие поля из Product для создания/обновления доменной записи."""
    return {
        "name": product.name or "",
        "slug": product.slug,
        "description": product.description or "",
        "gender": getattr(product, "gender", None) or "",
        "category_id": product.category_id,
        "brand_id": product.brand_id,
        "price": product.price,
        "old_price": product.old_price,
        "currency": product.currency or "RUB",
        "is_available": getattr(product, "is_available", True),
        "main_image": product.main_image or "",
        "video_url": product.video_url or "",
        "external_id": getattr(product, "external_id", "") or "",
        "external_url": getattr(product, "external_url", "") or "",
        "external_data": getattr(product, "external_data", {}) or {},
        "is_active": product.is_active,
        "is_new": product.is_new,
        "is_featured": product.is_featured,
        "base_product_id": product.pk,
    }


def _enrich_domain_kwargs_from_product(kwargs, product, DomainModel):
    """Добавляет stock_quantity в kwargs для доменной модели.

    EN SEO поля (meta_title, og_title, …) намеренно НЕ копируются из Product:
    они предназначены для AI-генерации и должны оставаться пустыми до обработки.
    Русские RU-поля (seo_title, seo_description, keywords) остаются на Product.
    """
    if hasattr(DomainModel, "stock_quantity"):
        kwargs["stock_quantity"] = getattr(product, "stock_quantity", None)


# Поля, которые синхронизируем из Product в домен при создании и при обновлении
DOMAIN_SYNC_FIELDS = (
    "name", "slug", "description", "category_id", "brand_id",
    "price", "old_price", "currency", "is_available", "main_image", "video_url",
    "external_id", "external_url", "external_data",
    "is_active", "is_new", "is_featured",
)


def ensure_domain_product_for_base(product):
    """
    Если у Product есть product_type с доменной моделью:
    - доменной записи нет → создаём и копируем данные из Product;
    - запись уже есть → обновляем её общие поля из Product (скрапер/импорт).

    Теневые варианты (external_data содержит source_variant_id или source_variant_slug)
    пропускаются: они не должны создавать записи в доменных таблицах.
    """
    if not product or not product.pk or not product.product_type:
        return
    # Ранний выход для теневых вариантов
    external = getattr(product, 'external_data', None) or {}
    if external.get('source_variant_id') or external.get('source_variant_slug'):
        return
    domain_map = _get_domain_map()
    if product.product_type not in domain_map:
        return
    DomainModel, _related_name = domain_map[product.product_type]
    domain = DomainModel.objects.filter(base_product_id=product.pk).first()
    kwargs = _base_product_to_domain_kwargs(product)
    _enrich_domain_kwargs_from_product(kwargs, product, DomainModel)

    if domain is None:
        # Проверяем, нет ли уже такого товара по слагу (чтобы избежать UniqueViolation)
        existing_by_slug = DomainModel.objects.filter(slug=kwargs['slug']).first()
        if existing_by_slug:
            # Привязываем существующий доменный товар к базовому, если он еще не привязан
            if not existing_by_slug.base_product_id:
                existing_by_slug.base_product_id = product.pk
                existing_by_slug.save()
                logger.info("Linked existing %s (slug=%s) to base Product pk=%s", DomainModel.__name__, product.slug, product.pk)
            domain = existing_by_slug
        else:
            try:
                DomainModel.objects.create(**kwargs)
                logger.info(
                    "Created %s for base Product pk=%s slug=%s",
                    DomainModel.__name__,
                    product.pk,
                    product.slug,
                )
            except Exception as e:
                logger.exception(
                    "Failed to create %s for Product pk=%s: %s",
                    DomainModel.__name__,
                    product.pk,
                    e,
                )
        return

    try:
        update_dict = {}
        for field in DOMAIN_SYNC_FIELDS:
            if hasattr(DomainModel, field) and field in kwargs:
                update_dict[field] = kwargs[field]
        # stock_quantity синхронизируем только если базовый Product имеет значение.
        # Если Product.stock_quantity = None — не перезаписываем доменную модель:
        # там может стоять значение от AI или вручную выставленное.
        if hasattr(DomainModel, "stock_quantity") and kwargs.get("stock_quantity") is not None:
            update_dict["stock_quantity"] = kwargs["stock_quantity"]
        # EN SEO поля (meta_title, og_title, …) не синхронизируем из Product при обновлении —
        # они заполняются AI и не должны перезаписываться данными из base Product.
        if update_dict:
            if hasattr(DomainModel, "updated_at"):
                update_dict["updated_at"] = timezone.now()
            DomainModel.objects.filter(pk=domain.pk).update(**update_dict)
    except Exception as e:
        logger.exception(
            "Failed to update %s for Product pk=%s: %s",
            DomainModel.__name__,
            product.pk,
            e,
        )


# --- Смена типа товара ------------------------------------------------------
# Смена product_type (админка, нормалайзер) создаёт запись нового домена, но
# прежняя доменная запись оставалась активной: товар продолжал отдаваться в
# выдаче старого типа, а фото (у одежды — фото вариантов) в новую запись не
# попадали. Переносим ссылки на медиа и снимаем прежнюю запись с публикации
# через update(): save() доменной записи синхронизирует её в Product и вернул
# бы товару старый тип и is_active=False. Файлы в хранилище не удаляются —
# на них по-прежнему ссылаются обе записи.

_VARIANT_RELATIONS = ("variants", "book_variants")
_GALLERY_RELATIONS = ("images", "gallery_images")


def domain_models():
    """product_type → доменная модель со связью base_product (все типы)."""
    from django.apps import apps

    from .models import AbstractDomainProduct

    return {
        model._domain_product_type: model
        for model in apps.get_app_config("catalog").get_models()
        if issubclass(model, AbstractDomainProduct)
        and model._domain_product_type
        and any(field.name == "base_product" for field in model._meta.concrete_fields)
    }


def is_retired_domain_record(domain, product) -> bool:
    """Запись прежнего типа товара, у которого уже есть запись текущего типа."""
    current_type = str(product.product_type or "").replace("-", "_")
    if not current_type or current_type == domain._domain_product_type:
        return False
    current_model = domain_models().get(current_type)
    return bool(current_model and current_model.objects.filter(base_product_id=product.pk).exists())


def _child_relation(model, names):
    """(имя менеджера, модель строк, поле-родитель) первой обратной FK из names."""
    for name in names:
        try:
            field = model._meta.get_field(name)
        except FieldDoesNotExist:
            continue
        if field.one_to_many:
            return name, field.related_model, field.field.name
    return None


def _media_key(row) -> str:
    file_name = getattr(getattr(row, "image_file", None), "name", "") or ""
    return file_name or (getattr(row, "image_url", "") or "")


def _copied_values(row, target_model, exclude) -> dict:
    """Значения полей строки, которые есть и у модели-получателя (без pk и родителя)."""
    target_fields = {field.name for field in target_model._meta.concrete_fields}
    values = {}
    for field in row._meta.concrete_fields:
        if field.primary_key or field.name in exclude or field.name not in target_fields:
            continue
        value = getattr(row, field.attname)
        values[field.attname] = value.name if isinstance(value, FieldFile) else value
    return values


def _copy_children(rows, relation, parent, *, sort_start=None) -> int:
    """Копирует строки картинок/размеров в relation записи parent (bulk_create без сигналов:
    ссылки на файлы переносятся как есть, ничего не скачивается)."""
    _name, model, parent_field = relation
    copies = []
    for index, row in enumerate(rows):
        values = _copied_values(row, model, {parent_field, "created_at", "updated_at"})
        if sort_start is not None and "sort_order" in values:
            values["sort_order"] = sort_start + index
        copies.append(model(**values, **{parent_field: parent}))
    model.objects.bulk_create(copies)
    return len(copies)


def _move_domain_media(stale, target, *, dry_run: bool) -> dict:
    """Переносит в target галерею stale и его варианты (или их фото, если у target вариантов нет)."""
    source_variants = _child_relation(type(stale), _VARIANT_RELATIONS)
    target_variants = _child_relation(type(target), _VARIANT_RELATIONS)
    source_gallery = _child_relation(type(stale), _GALLERY_RELATIONS)
    target_gallery = _child_relation(type(target), _GALLERY_RELATIONS)

    variants = []
    if source_variants:
        variants = list(getattr(stale, source_variants[0]).order_by("sort_order", "pk"))
    copy_variants = bool(
        variants and target_variants
        and not getattr(target, target_variants[0]).exists()
    )

    gallery_rows = list(getattr(stale, source_gallery[0]).order_by("sort_order", "pk")) if source_gallery else []
    if not copy_variants:
        for variant in variants:
            images = _child_relation(type(variant), ("images",))
            if images:
                gallery_rows.extend(getattr(variant, images[0]).order_by("sort_order", "pk"))

    new_gallery_rows = []
    if target_gallery:
        manager = getattr(target, target_gallery[0])
        existing = list(manager.all())
        seen = {_media_key(row) for row in existing}
        # Фото вариантов новой записи тоже уже есть на витрине (обратная смена типа).
        for variant in getattr(target, target_variants[0]).all() if target_variants else []:
            images = _child_relation(type(variant), ("images",))
            if images:
                seen.update(_media_key(row) for row in getattr(variant, images[0]).all())
        for row in gallery_rows:
            key = _media_key(row)
            if key and key not in seen:
                seen.add(key)
                new_gallery_rows.append(row)

    result = {"gallery": len(new_gallery_rows), "variants": len(variants) if copy_variants else 0}
    if dry_run:
        return result

    if new_gallery_rows:
        start = max((row.sort_order or 0 for row in existing), default=-1) + 1
        _copy_children(new_gallery_rows, target_gallery, target, sort_start=start)
        has_main_flag = any(f.name == "is_main" for f in target_gallery[1]._meta.concrete_fields)
        if has_main_flag and not any(row.is_main for row in existing):
            # Главная — картинка с адресом main_image записи, иначе первая перенесённая;
            # флаги is_main фото вариантов (по одному на цвет) не переносим.
            copied = list(manager.exclude(pk__in=[row.pk for row in existing]).order_by("sort_order", "pk"))
            main = next(
                (row for row in copied if target.main_image and row.image_url == target.main_image),
                copied[0],
            )
            manager.filter(pk__in=[row.pk for row in copied]).exclude(pk=main.pk).update(is_main=False)
            manager.filter(pk=main.pk).update(is_main=True)

    if copy_variants:
        _name, variant_model, parent_field = target_variants
        for variant in variants:
            values = _copied_values(variant, variant_model, {parent_field, "created_at", "updated_at"})
            if values.get("slug") and variant_model.objects.filter(slug=values["slug"]).exists():
                values["slug"] = ""
            copy = variant_model(**values, **{parent_field: target})
            copy.save()
            for names in (("images",), ("sizes",)):
                source = _child_relation(type(variant), names)
                destination = _child_relation(variant_model, names)
                if source and destination:
                    _copy_children(
                        list(getattr(variant, source[0]).order_by("pk")), destination, copy,
                    )
    return result


def retire_stale_domain_records(product, *, dry_run: bool = False) -> list:
    """Переносит медиа доменных записей прежнего типа в запись текущего и снимает их с публикации.

    Базовый Product не меняется. Пока записи текущего типа нет (тип без
    доменной модели в _get_domain_map), прежние записи не трогаем. Повторный
    вызов безопасен: уже перенесённые картинки повторно не копируются.
    """
    if not product or not product.pk:
        return []
    models = domain_models()
    target_model = models.get(str(product.product_type or "").replace("-", "_"))
    target = target_model.objects.filter(base_product_id=product.pk).first() if target_model else None
    stale_rows = [
        row
        for model in models.values()
        if model is not target_model
        for row in model.objects.filter(base_product_id=product.pk)
    ]
    if not stale_rows:
        return []
    if target is None:
        logger.warning(
            "Product pk=%s (%s): нет доменной записи текущего типа, прежние %s не сняты",
            product.pk,
            product.product_type,
            [f"{type(row).__name__}:{row.pk}" for row in stale_rows],
        )
        return []

    report = []
    for stale in stale_rows:
        with transaction.atomic():
            moved = _move_domain_media(stale, target, dry_run=dry_run)
            if not dry_run:
                type(stale).objects.filter(pk=stale.pk).update(is_active=False)
        report.append({
            "model": type(stale).__name__,
            "pk": stale.pk,
            "was_active": stale.is_active,
            "target": f"{type(target).__name__}:{target.pk}",
            **moved,
        })
        logger.info("Product pk=%s: прежняя доменная запись снята %s", product.pk, report[-1])
    return report
