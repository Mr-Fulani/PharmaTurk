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


ASSET_DIR = Path("/app/tmp_service_cleaning_ac")


ATTRIBUTE_LABELS = {
    "service-area": ("Районы работы", "Service areas", "Hizmet bölgeleri"),
    "language": ("Язык общения", "Communication language", "İletişim dili"),
    "format": ("Формат услуги", "Service format", "Hizmet formatı"),
    "includes": ("Что входит", "Includes", "Dahil olanlar"),
    "price-note": ("Цена", "Price", "Fiyat"),
}


SERVICE = {
    "name": "Мытье окон",
    "slug": "myte-okon",
    "category_slugs": ["svc-other", "uslugi"],
    "asset": "myte-okon-og.png",
    "description": (
        "Аккуратное мытье окон в квартирах, виллах и офисах Стамбула. Услуга подходит для регулярной "
        "уборки, подготовки жилья к заселению, сезонного обновления квартиры и комплексного клининга.\n\n"
        "Что входит в услугу:\n"
        "• Мытье стекол снаружи и изнутри до прозрачности\n"
        "• Снятие занавесок, стирка и развешивание обратно по договоренности\n"
        "• Чистка подоконников, откосов, рам, ручек и створок\n"
        "• Протирка оконных решеток и доступных элементов\n"
        "• Удаление пятен, пыли и бытовых загрязнений\n"
        "• Индивидуальный подход к большим и нестандартным окнам\n\n"
        "Работаем по Каяшехиру, Башакшехиру, Мавере, Эсенюрту, Бейликдюзю, Каваклы и другим районам. "
        "Финальный объем зависит от размера, количества и состояния окон, особенно для больших квартир, "
        "вилл, офисов и нестандартного остекления."
    ),
    "description_en": (
        "Careful window washing for apartments, villas and offices in Istanbul. The service includes "
        "inside and outside glass cleaning, frames, handles, sills, slopes and an individual approach "
        "for large or non-standard windows."
    ),
    "meta_title": "Мытье окон в Стамбуле | Окна внутри и снаружи",
    "meta_description": (
        "Мытье окон в Стамбуле: стекла внутри и снаружи, рамы, ручки, подоконники, откосы, решетки "
        "и занавески по договоренности. Каяшехир, Башакшехир, Мавера, Эсенюрт, Бейликдюзю."
    ),
    "keywords": (
        "мытье окон Стамбул, мойка окон Стамбул, чистка окон, мытье окон Башакшехир, "
        "мытье окон Каяшехир, мытье окон Мавера, мытье окон Эсенюрт, мытье окон Бейликдюзю, "
        "клининг окон, мытье стекол"
    ),
    "og_title": "Мытье окон в Стамбуле",
    "og_description": "Стекла, рамы, подоконники и откосы: аккуратное мытье окон внутри и снаружи.",
    "alt_text": "Мытье окон в квартирах и офисах Стамбула",
    "attributes": [
        (
            "service-area",
            "Каяшехир, Башакшехир, Мавера, Эсенюрт, Бейликдюзю, Каваклы",
            "Kayasehir, Basaksehir, Mavera, Esenyurt, Beylikduzu, Kavakli",
        ),
        ("language", "русский", "Russian"),
        ("format", "квартиры, виллы, офисы", "apartments, villas, offices"),
        (
            "includes",
            "стекла, рамы, ручки, подоконники, откосы, решетки",
            "glass, frames, handles, sills, slopes, grilles",
        ),
        ("price-note", "цена выставляется вручную", "price is set manually"),
    ],
    "case": {
        "title": "Мытье окон в квартире",
        "summary": "Окна очищены внутри и снаружи, рамы и подоконники приведены в порядок.",
        "description": (
            "Выполнено комплексное мытье окон: стекла очищены с двух сторон, протерты рамы, ручки, "
            "створки, подоконники и откосы. Для больших или нестандартных окон объем работ согласуется "
            "индивидуально."
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


def upload_main_image(service, asset_name, alt_text):
    data = (ASSET_DIR / asset_name).read_bytes()
    service.main_image_file.save(asset_name, ContentFile(data), save=False)
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


def set_portfolio(service, spec):
    case_spec = spec["case"]
    case, _ = ServicePortfolioItem.objects.update_or_create(
        service=service,
        title=case_spec["title"],
        defaults={
            "category": service.category,
            "title_en": case_spec["title"],
            "result_summary": case_spec["summary"],
            "result_summary_en": case_spec["summary"],
            "description": case_spec["description"],
            "description_en": case_spec["description"],
            "city": case_spec["city"],
            "city_en": "Istanbul",
            "alt_text": spec["alt_text"],
            "alt_text_en": spec["alt_text"],
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
    service.meta_title = spec["meta_title"]
    service.meta_description = spec["meta_description"]
    service.meta_keywords = spec["keywords"]
    service.og_title = spec["og_title"]
    service.og_description = spec["og_description"]
    service.save()

    service.translations.filter(locale="en").delete()
    ServiceTranslation.objects.update_or_create(
        service=service,
        locale="en",
        defaults={"name": spec["name"], "description": spec["description_en"]},
    )

    upload_main_image(service, spec["asset"], spec["alt_text"])
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
        }
    )
