"""
Синхронизация Product с доменными моделями (PerfumeryProduct, MedicineProduct и т.д.).

При создании/обновлении Product через скраперы или импорт автоматически создаётся
соответствующая запись в доменной таблице (если её ещё нет) и копируются общие поля.
Так товары попадают в нужные разделы админки и в правильные API-эндпоинты.
"""

import logging

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
        "category_id": product.category_id,
        "brand_id": product.brand_id,
        "price": product.price,
        "old_price": product.old_price,
        "currency": product.currency or "RUB",
        "is_available": getattr(product, "is_available", True),
        "main_image": product.main_image or "",
        "external_id": getattr(product, "external_id", "") or "",
        "external_url": getattr(product, "external_url", "") or "",
        "external_data": getattr(product, "external_data", {}) or {},
        "is_active": product.is_active,
        "is_new": product.is_new,
        "is_featured": product.is_featured,
        "base_product_id": product.pk,
    }


def _enrich_domain_kwargs_from_product(kwargs, product, DomainModel):
    """Добавляет meta/og и stock_quantity в kwargs для доменной модели."""
    if hasattr(DomainModel, "stock_quantity"):
        kwargs["stock_quantity"] = getattr(product, "stock_quantity", None)
    for key in ("meta_title", "meta_description", "meta_keywords", "og_title", "og_description", "og_image_url"):
        if hasattr(DomainModel, key):
            if key == "meta_title" and hasattr(product, "seo_title"):
                kwargs[key] = getattr(product, "seo_title", "") or ""
            elif key == "meta_description" and hasattr(product, "seo_description"):
                kwargs[key] = getattr(product, "seo_description", "") or ""
            elif key == "meta_keywords" and hasattr(product, "keywords"):
                kw = product.keywords
                kwargs[key] = ", ".join(kw) if isinstance(kw, list) else (kw or "")
            else:
                kwargs[key] = getattr(product, key, "") or ""


# Поля, которые синхронизируем из Product в домен при создании и при обновлении
DOMAIN_SYNC_FIELDS = (
    "name", "slug", "description", "category_id", "brand_id",
    "price", "old_price", "currency", "is_available", "main_image",
    "external_id", "external_url", "external_data",
    "is_active", "is_new", "is_featured",
)


def ensure_domain_product_for_base(product):
    """
    Если у Product есть product_type с доменной моделью:
    - доменной записи нет → создаём и копируем данные из Product;
    - запись уже есть → обновляем её общие поля из Product (скрапер/импорт).
    """
    if not product or not product.pk or not product.product_type:
        return
    domain_map = _get_domain_map()
    if product.product_type not in domain_map:
        return
    DomainModel, _related_name = domain_map[product.product_type]
    domain = DomainModel.objects.filter(base_product_id=product.pk).first()
    kwargs = _base_product_to_domain_kwargs(product)
    _enrich_domain_kwargs_from_product(kwargs, product, DomainModel)

    if domain is None:
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
        if hasattr(DomainModel, "stock_quantity") and "stock_quantity" in kwargs:
            update_dict["stock_quantity"] = kwargs["stock_quantity"]
        for key in ("meta_title", "meta_description", "meta_keywords", "og_title", "og_description", "og_image_url"):
            if hasattr(DomainModel, key) and key in kwargs:
                update_dict[key] = kwargs[key]
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
