import os
import sys
from pathlib import Path

import django
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction


sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.catalog.models import (
    Category,
    GlobalAttributeKey,
    GlobalAttributeKeyTranslation,
    Service,
    ServiceAttribute,
    ServiceImage,
    ServicePrice,
    ServicePortfolioItem,
    ServicePortfolioMedia,
    ServiceTranslation,
)


ASSET_DIR = Path("/app/tmp_service_moving")


ATTRIBUTE_LABELS = {
    "service-area": ("Районы работы", "Service areas", "Hizmet bölgeleri"),
    "language": ("Язык общения", "Communication language", "İletişim dili"),
    "format": ("Формат услуги", "Service format", "Hizmet formatı"),
    "includes": ("Что входит", "Includes", "Dahil olanlar"),
    "moving-services": ("Помощь при переезде", "Moving assistance", "Taşınma yardımı"),
    "price-note": ("Цена", "Price", "Fiyat"),
}


SERVICE = {
    "name": "Переезд",
    "name_en": "Moving Service",
    "slug": "pereezd",
    "category_slugs": ["svc-other", "uslugi"],
    "asset": "pereezd-og.png",
    "gallery": [
        ("pereezd-reels-1.png", "Разборка и упаковка мебели при переезде"),
        ("pereezd-reels-2.png", "Погрузка и выгрузка мебели и техники при переезде"),
    ],
    "description": (
        "Помощь с переездом в Стамбуле и по Турции: аккуратная упаковка вещей, разборка и сборка "
        "мебели, погрузка, выгрузка, расстановка и установка мебели и бытовой техники после переезда. "
        "Услуга подходит для квартир, домов, офисов, небольших складов и коммерческих помещений.\n\n"
        "Что можно заказать:\n"
        "• Упаковку вещей, мебели, техники и хрупких предметов\n"
        "• Разборку шкафов, кроватей, столов, диванов и другой мебели\n"
        "• Погрузку, перенос и выгрузку коробок, мебели и техники\n"
        "• Сборку мебели на новом месте\n"
        "• Установку и расстановку мебели и бытовой техники после переезда\n"
        "• Помощь с квартирным, офисным и межгородним переездом\n\n"
        "Работаем по Стамбулу и в других городах Турции по договоренности. Объем, маршрут, количество "
        "предметов, этажность, наличие лифта и дополнительные задачи согласуются индивидуально. Цена "
        "выставляется вручную после оценки переезда."
    ),
    "description_en": (
        "Moving assistance in Istanbul and across Turkey: careful packing, furniture disassembly and "
        "assembly, loading, unloading, placement and setup of furniture and household appliances after "
        "the move. The service is suitable for apartments, houses, offices, small storage spaces and "
        "commercial premises.\n\n"
        "The scope can include packing belongings, furniture and fragile items, disassembling wardrobes, "
        "beds, tables and sofas, carrying boxes, furniture and appliances, assembling furniture at the "
        "new location and helping with local or intercity moves. Route, floors, elevator access, item "
        "quantity and extra tasks are agreed individually."
    ),
    "seo_ru": {
        "meta_title": "Переезд в Стамбуле и Турции | Упаковка, погрузка, сборка мебели",
        "meta_description": (
            "Помощь с переездом в Стамбуле и по Турции: упаковка вещей, разборка и сборка мебели, "
            "погрузка, выгрузка, расстановка и установка мебели и техники."
        ),
        "keywords": (
            "переезд Стамбул, переезд Турция, помощь с переездом, упаковка вещей при переезде, "
            "разборка мебели переезд, сборка мебели после переезда, погрузка выгрузка, квартирный переезд, "
            "офисный переезд, перевозка мебели и техники"
        ),
        "og_title": "Переезд в Стамбуле и по Турции",
        "og_description": "Упаковка, разборка, сборка, погрузка, выгрузка и установка мебели и техники.",
    },
    "seo_en": {
        "meta_title": "Moving Service in Istanbul and Turkey | Packing, Loading, Furniture Assembly",
        "meta_description": (
            "Moving assistance in Istanbul and across Turkey: packing, furniture disassembly and assembly, "
            "loading, unloading, placement and setup of furniture and appliances."
        ),
        "keywords": (
            "moving service Istanbul, moving service Turkey, relocation assistance, packing for moving, "
            "furniture disassembly, furniture assembly, loading unloading, apartment move, office move, "
            "furniture and appliance moving"
        ),
        "og_title": "Moving Service in Istanbul and Turkey",
        "og_description": "Packing, disassembly, assembly, loading, unloading and appliance setup.",
    },
    "alt_text": "Переезд в Стамбуле и Турции: упаковка, погрузка и сборка мебели",
    "attributes": [
        ("service-area", "Стамбул и Турция по договоренности", "Istanbul and Turkey by agreement"),
        ("language", "русский", "Russian"),
        ("format", "выезд на объект", "on-site service"),
        ("moving-services", "упаковка, разборка, сборка, погрузка, выгрузка", "packing, disassembly, assembly, loading, unloading"),
        ("includes", "мебель, техника, коробки, расстановка на новом месте", "furniture, appliances, boxes, placement at the new location"),
        ("price-note", "цена выставляется вручную", "price is set manually"),
    ],
    "case": {
        "title": "Квартирный переезд с разборкой мебели",
        "title_en": "Apartment move with furniture disassembly",
        "summary": "Вещи упакованы, мебель разобрана, перевезена, выгружена и собрана на новом месте.",
        "summary_en": "Items were packed, furniture disassembled, moved, unloaded and assembled at the new location.",
        "description": (
            "Команда помогла подготовить квартиру к переезду: вещи и мебель были упакованы, крупные предметы "
            "аккуратно разобраны, загружены и выгружены. На новом месте мебель собрали и расставили, а технику "
            "подготовили к дальнейшей установке по договоренности."
        ),
        "description_en": (
            "The team helped prepare the apartment for relocation: belongings and furniture were packed, large "
            "items were carefully disassembled, loaded and unloaded. At the new location, furniture was assembled "
            "and placed, with appliances prepared for setup by agreement."
        ),
        "city": "Стамбул",
    },
}


def first_category(slugs):
    for slug in slugs:
        category = Category.objects.filter(slug=slug, is_active=True).first()
        if category:
            return category
    return Category.objects.filter(slug="uslugi").first()


def ensure_attribute_key(slug, sort_order):
    key, _ = GlobalAttributeKey.objects.get_or_create(slug=slug, defaults={"sort_order": sort_order})
    ru, en, tr = ATTRIBUTE_LABELS[slug]
    for locale, name in (("ru", ru), ("en", en), ("tr", tr)):
        GlobalAttributeKeyTranslation.objects.update_or_create(
            key_obj=key,
            locale=locale,
            defaults={"name": name},
        )
    return key


def set_attributes(service, attributes):
    for sort_order, (slug, value_ru, value_en) in enumerate(attributes):
        key = ensure_attribute_key(slug, sort_order)
        if service.category_id:
            key.categories.add(service.category)
        ServiceAttribute.objects.update_or_create(
            service=service,
            attribute_key=key,
            defaults={
                "value": value_ru,
                "value_ru": value_ru,
                "value_en": value_en,
                "sort_order": sort_order,
            },
        )


def save_image_field(field, filename):
    field.save(filename, ContentFile((ASSET_DIR / filename).read_bytes()), save=False)


def upload_main_image(service, asset_name, alt_text):
    service.main_image_file.save(asset_name, ContentFile((ASSET_DIR / asset_name).read_bytes()), save=True)
    service.main_image = ""
    service.save(update_fields=["main_image", "updated_at"])
    service.og_image_url = default_storage.url(service.main_image_file.name)
    service.save(update_fields=["og_image_url", "updated_at"])
    service.images.update(is_main=False)
    ServiceImage.objects.update_or_create(
        service=service,
        image_file=service.main_image_file.name,
        defaults={"alt_text": alt_text, "sort_order": 0, "is_main": True},
    )


def upload_gallery(service, gallery):
    for index, (asset_name, alt_text) in enumerate(gallery, start=1):
        image = service.images.filter(alt_text=alt_text).first()
        if image is None:
            image = ServiceImage(service=service, alt_text=alt_text)
        save_image_field(image.image_file, asset_name)
        image.sort_order = index
        image.is_main = False
        image.save()


def set_portfolio(service, spec):
    case_spec = spec["case"]
    case, _ = ServicePortfolioItem.objects.update_or_create(
        service=service,
        title=case_spec["title"],
        defaults={
            "category": service.category,
            "title_en": case_spec["title_en"],
            "result_summary": case_spec["summary"],
            "result_summary_en": case_spec["summary_en"],
            "description": case_spec["description"],
            "description_en": case_spec["description_en"],
            "city": case_spec["city"],
            "city_en": "Istanbul",
            "alt_text": spec["alt_text"],
            "alt_text_en": "Moving service in Istanbul and Turkey",
            "sort_order": 0,
            "is_active": True,
        },
    )
    if not case.media_items.exists() and service.main_image_file:
        ServicePortfolioMedia.objects.create(
            portfolio_item=case,
            media_type="image",
            badge="none",
            media_file=service.main_image_file.name,
            sort_order=0,
        )


with transaction.atomic():
    spec = SERVICE
    category = first_category(spec["category_slugs"])
    service, _ = Service.objects.select_for_update().get_or_create(
        slug=spec["slug"],
        defaults={"name": spec["name"]},
    )
    service.name = spec["name"]
    service.description = spec["description"]
    service.category = category
    service.price = None
    service.currency = "TRY"
    service.is_active = True
    service.is_featured = True
    service.meta_title = spec["seo_ru"]["meta_title"]
    service.meta_description = spec["seo_ru"]["meta_description"]
    service.meta_keywords = spec["seo_ru"]["keywords"]
    service.og_title = spec["seo_ru"]["og_title"]
    service.og_description = spec["seo_ru"]["og_description"]
    external_data = dict(service.external_data or {})
    external_data["seo_en"] = spec["seo_en"]
    external_data["seo_ru"] = spec["seo_ru"]
    external_data["gallery_format"] = "reels_9_16_no_text"
    service.external_data = external_data
    service.save()
    ServicePrice.objects.filter(service=service).delete()

    service.translations.filter(locale="en").delete()
    ServiceTranslation.objects.update_or_create(
        service=service,
        locale="en",
        defaults={"name": spec["name_en"], "description": spec["description_en"]},
    )

    upload_main_image(service, spec["asset"], spec["alt_text"])
    upload_gallery(service, spec["gallery"])
    set_attributes(service, spec["attributes"])
    set_portfolio(service, spec)

    print(
        {
            "id": service.pk,
            "name": service.name,
            "slug": service.slug,
            "category": service.category.slug if service.category else None,
            "price": service.price,
            "attributes": service.service_attributes.count(),
            "images": service.images.count(),
            "cases": service.portfolio_items.count(),
            "og": service.og_image_url,
            "seo_en": bool(service.external_data.get("seo_en")),
            "gallery_format": service.external_data.get("gallery_format"),
        }
    )
