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
    ServicePortfolioItem,
    ServicePortfolioMedia,
    ServiceTranslation,
)


ASSET_DIR = Path("/app/tmp_service_upholstery")


ATTRIBUTE_LABELS = {
    "service-area": ("Районы работы", "Service areas", "Hizmet bölgeleri"),
    "language": ("Язык общения", "Communication language", "İletişim dili"),
    "format": ("Формат услуги", "Service format", "Hizmet formatı"),
    "includes": ("Что входит", "Includes", "Dahil olanlar"),
    "furniture-types": ("Типы мебели", "Furniture types", "Mobilya türleri"),
    "price-note": ("Цена", "Price", "Fiyat"),
}


SERVICE = {
    "name": "Химчистка мягкой мебели на дому",
    "name_en": "Home Upholstery Cleaning",
    "slug": "himchistka-myagkoj-mebeli-na-domu",
    "category_slugs": ["svc-other", "uslugi"],
    "asset": "himchistka-myagkoj-mebeli-og.png",
    "gallery": [
        (
            "himchistka-myagkoj-mebeli-reels-1.png",
            "Химчистка дивана на дому: удаление пятен и запахов",
        ),
        (
            "himchistka-myagkoj-mebeli-reels-2.png",
            "Химчистка кресел и мягкой мебели на дому",
        ),
    ],
    "description": (
        "Химчистка мягкой мебели на дому в Стамбуле — удобный способ вернуть диванам, креслам, "
        "стульям, пуфам и матрасам свежий вид без вывоза мебели. Специалист приезжает на объект "
        "с профессиональным оборудованием и подбирает аккуратный режим чистки под тип ткани и "
        "состояние обивки.\n\n"
        "Что входит в услугу:\n"
        "• Осмотр обивки и подбор подходящего способа чистки\n"
        "• Глубокая экстракторная чистка мягкой мебели\n"
        "• Обработка бытовых пятен, пыли и загрязнений\n"
        "• Уменьшение неприятных запахов после повседневного использования\n"
        "• Чистка диванов, кресел, стульев, пуфов, изголовий и матрасов\n"
        "• Аккуратная работа на дому без лишнего шума и беспорядка\n\n"
        "Услуга подходит для квартир, вилл, офисов, салонов и арендуемого жилья. Объем, время выезда, "
        "количество предметов и особенности ткани согласуются индивидуально. Цена выставляется вручную "
        "после оценки мебели и объема работ."
    ),
    "description_en": (
        "Home upholstery cleaning in Istanbul is a convenient way to refresh sofas, armchairs, chairs, "
        "poufs, headboards and mattresses without moving furniture out. A specialist arrives with "
        "professional extraction equipment and chooses a careful cleaning method based on the fabric "
        "type and upholstery condition.\n\n"
        "The service can include upholstery inspection, deep extractor cleaning, treatment of everyday "
        "stains, dust and dirt, odor reduction and careful on-site cleaning for apartments, villas, "
        "offices, salons and rental homes. The final scope and price are agreed individually after "
        "reviewing the furniture and amount of work."
    ),
    "seo_ru": {
        "meta_title": "Химчистка мягкой мебели на дому в Стамбуле | Диваны и кресла",
        "meta_description": (
            "Химчистка мягкой мебели на дому в Стамбуле: диваны, кресла, стулья, пуфы, изголовья и "
            "матрасы. Глубокая чистка ткани, пятен, пыли и запахов без вывоза мебели."
        ),
        "keywords": (
            "химчистка мягкой мебели Стамбул, химчистка дивана на дому, химчистка кресел, "
            "чистка дивана Стамбул, чистка мягкой мебели, химчистка матраса, экстракторная чистка, "
            "удаление пятен с дивана, чистка обивки"
        ),
        "og_title": "Химчистка мягкой мебели на дому",
        "og_description": "Диваны, кресла, стулья и матрасы: глубокая чистка ткани, пятен, пыли и запахов.",
    },
    "seo_en": {
        "meta_title": "Home Upholstery Cleaning in Istanbul | Sofas and Armchairs",
        "meta_description": (
            "Home upholstery cleaning in Istanbul for sofas, armchairs, chairs, poufs, headboards and "
            "mattresses. Deep fabric cleaning, stain treatment, dust and odor reduction without moving furniture."
        ),
        "keywords": (
            "upholstery cleaning Istanbul, sofa cleaning at home, armchair cleaning, mattress cleaning, "
            "fabric cleaning, extractor upholstery cleaning, stain removal sofa, home furniture cleaning"
        ),
        "og_title": "Home Upholstery Cleaning",
        "og_description": "Deep on-site cleaning for sofas, armchairs, chairs and mattresses in Istanbul.",
    },
    "alt_text": "Химчистка мягкой мебели на дому в Стамбуле",
    "attributes": [
        ("service-area", "Стамбул и ближайшие районы по договоренности", "Istanbul and nearby districts by agreement"),
        ("language", "русский", "Russian"),
        ("format", "выезд на дом", "home visit"),
        ("furniture-types", "диваны, кресла, стулья, пуфы, матрасы", "sofas, armchairs, chairs, poufs, mattresses"),
        ("includes", "экстракторная чистка, пятна, пыль, запахи", "extractor cleaning, stains, dust, odors"),
        ("price-note", "цена выставляется вручную", "price is set manually"),
    ],
    "case": {
        "title": "Химчистка дивана на дому",
        "title_en": "Home sofa upholstery cleaning",
        "summary": "Диван очищен на дому: ткань освежена, пыль и бытовые загрязнения обработаны.",
        "summary_en": "The sofa was cleaned on-site: fabric refreshed and everyday dirt treated.",
        "description": (
            "Выполнена выездная химчистка мягкой мебели: обивка осмотрена, выбран щадящий режим, "
            "проведена глубокая экстракторная чистка дивана и обработка зон повседневного загрязнения. "
            "Мебель осталась на месте, работа проведена аккуратно в квартире клиента."
        ),
        "description_en": (
            "On-site upholstery cleaning was completed: the fabric was inspected, a gentle cleaning mode "
            "was selected and the sofa was deep-cleaned with extraction equipment. The furniture stayed in "
            "place and the work was carried out carefully in the client's home."
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
    save_image_field(service.main_image_file, asset_name)
    service.main_image = ""
    service.save(update_fields=["main_image_file", "main_image", "updated_at"])
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
            "alt_text_en": "Home upholstery cleaning in Istanbul",
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
    external_data["gallery_format"] = "reels_9_16"
    service.external_data = external_data
    service.save()

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
        }
    )
