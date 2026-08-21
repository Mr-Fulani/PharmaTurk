import json

from django.core.files import File
from django.db import transaction

from apps.catalog.models import (
    Brand,
    BrandTranslation,
    Category,
    IslamicClothingProduct,
    Product,
)


LOGO_PATH = "/tmp/tasnim-logo.png"

DESCRIPTION_RU = (
    "Tasnim — бренд качественных буркини для мусульманок. Модели сочетают "
    "скромный крой, комфорт при плавании и практичные материалы для пляжа и бассейна."
)
DESCRIPTION_EN = (
    "Tasnim is a quality burkini brand for Muslim women, combining modest coverage, "
    "freedom of movement and practical fabrics for the beach and pool."
)

SEO_TRANSLATIONS = {
    "ru": {
        "meta_title": "Буркини Tasnim для мусульманок — купить на Mudaroba",
        "meta_description": (
            "Качественные буркини Tasnim для мусульманок: скромный крой, "
            "комфортная посадка и практичные материалы для плавания, пляжа и бассейна."
        ),
        "meta_keywords": (
            "Tasnim, буркини Tasnim, буркини для мусульманок, "
            "мусульманские купальники, скромная одежда для плавания"
        ),
        "og_title": "Буркини Tasnim для мусульманок — Mudaroba",
        "og_description": DESCRIPTION_RU,
    },
    "en": {
        "meta_title": "Tasnim Burkinis for Muslim Women — Shop on Mudaroba",
        "meta_description": (
            "Shop quality Tasnim burkinis for Muslim women, with modest coverage, "
            "a comfortable fit and practical fabrics for swimming, the beach and the pool."
        ),
        "meta_keywords": (
            "Tasnim, Tasnim burkinis, burkinis for Muslim women, "
            "modest swimwear, Islamic swimwear"
        ),
        "og_title": "Tasnim Burkinis for Muslim Women — Mudaroba",
        "og_description": DESCRIPTION_EN,
    },
}


with transaction.atomic():
    category = Category.objects.select_for_update().get(
        slug="burkini",
        parent__slug="islamic-clothing",
    )

    brand, created = Brand.objects.select_for_update().get_or_create(
        slug="tasnim",
        defaults={"name": "Tasnim"},
    )
    external_data = dict(brand.external_data or {})
    external_data["seo_translations"] = SEO_TRANSLATIONS
    external_data["brand_positioning"] = {
        "specialization": "quality burkinis for Muslim women",
        "locales": ["ru", "en"],
    }

    brand.name = "Tasnim"
    brand.description = DESCRIPTION_RU
    brand.external_data = external_data
    brand.is_active = True
    brand.primary_category_slug = "islamic-clothing"
    brand.category_slugs = ["islamic-clothing"]

    logo_uploaded = False
    if not brand.card_media:
        with open(LOGO_PATH, "rb") as logo_file:
            brand.card_media.save("tasnim-logo.png", File(logo_file), save=False)
        logo_uploaded = True
    brand.save()

    BrandTranslation.objects.update_or_create(
        brand=brand,
        locale="ru",
        defaults={"name": "Tasnim", "description": DESCRIPTION_RU},
    )
    BrandTranslation.objects.update_or_create(
        brand=brand,
        locale="en",
        defaults={"name": "Tasnim", "description": DESCRIPTION_EN},
    )

    domain_products = IslamicClothingProduct.objects.filter(category=category)
    base_product_ids = list(
        domain_products.exclude(base_product_id__isnull=True).values_list(
            "base_product_id",
            flat=True,
        )
    )
    domain_updated = domain_products.exclude(brand=brand).update(brand=brand)
    linked_base_updated = Product.objects.filter(id__in=base_product_ids).exclude(
        brand=brand
    ).update(brand=brand)
    direct_base_updated = Product.objects.filter(category=category).exclude(
        brand=brand
    ).update(brand=brand)

    result = {
        "brand_created": created,
        "brand_id": brand.id,
        "brand_slug": brand.slug,
        "category_id": category.id,
        "category_slug": category.slug,
        "logo_uploaded": logo_uploaded,
        "card_media": brand.card_media.name,
        "card_media_url": brand.card_media.url,
        "domain_products_updated": domain_updated,
        "linked_base_products_updated": linked_base_updated,
        "direct_base_products_updated": direct_base_updated,
        "final_domain_products": domain_products.count(),
        "final_domain_products_with_brand": domain_products.filter(brand=brand).count(),
        "final_base_products": Product.objects.filter(category=category).count(),
        "final_base_products_with_brand": Product.objects.filter(
            category=category,
            brand=brand,
        ).count(),
        "translations": list(
            brand.translations.order_by("locale").values(
                "locale",
                "name",
                "description",
            )
        ),
        "seo_translations": brand.external_data.get("seo_translations", {}),
    }

print(json.dumps(result, ensure_ascii=False, indent=2))
