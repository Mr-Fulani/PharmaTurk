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


SERVICES = [
    {
        "name": "Русскоязычный клининг",
        "slug": "russkoyazychnyj-klining",
        "category_slugs": ["svc-other", "uslugi"],
        "asset": "russkoyazychnyj-klining-og.png",
        "description": (
            "Русскоязычный клининг квартир, вилл и офисов в Стамбуле для тех, кто хочет заказать уборку "
            "понятно, спокойно и без лишних объяснений. Команда аккуратно работает с кухней, санузлом, "
            "мебелью, техникой, окнами и труднодоступными зонами, уделяя внимание деталям и состоянию жилья.\n\n"
            "Что можно заказать:\n"
            "• Генеральную уборку квартир 1+1, 2+1, 3+1, 4+1 и 5+1\n"
            "• Полную уборку кухни: фасады, шкафы, холодильник, плита, духовка, вытяжка и мойка\n"
            "• Уборку санузла: ванна, душ, раковина, унитаз, плитка, зеркала и углы\n"
            "• Мытье плинтусов, дверей, ручек, выключателей и коридора\n"
            "• Мытье окон внутри и снаружи, чистку рам, подоконников, откосов и решеток\n"
            "• Уборку вилл и офисов по индивидуальной договоренности\n\n"
            "Работаем по Каяшехиру, Башакшехиру, Мавере, Эсенюрту, Бейликдюзю, Каваклы и другим районам. "
            "Объем, время и дополнительные задачи можно согласовать индивидуально."
        ),
        "description_en": (
            "Russian-speaking apartment, villa and office cleaning in Istanbul with clear communication, "
            "careful work and attention to detail. General cleaning, kitchen and bathroom cleaning, window "
            "washing and custom tasks are available by agreement."
        ),
        "meta_title": "Русскоязычный клининг в Стамбуле | Уборка квартир и офисов",
        "meta_description": (
            "Русскоязычный клининг квартир, вилл и офисов в Стамбуле: генеральная уборка, кухня, санузел, "
            "окна, плинтусы и детали. Каяшехир, Башакшехир, Мавера, Эсенюрт, Бейликдюзю."
        ),
        "keywords": (
            "русскоязычный клининг Стамбул, уборка квартир Стамбул, генеральная уборка Стамбул, "
            "уборка Башакшехир, уборка Каяшехир, уборка Мавера, уборка Эсенюрт, уборка Бейликдюзю, "
            "мытье окон Стамбул, клининг квартир"
        ),
        "og_title": "Русскоязычный клининг в Стамбуле",
        "og_description": "Генеральная уборка квартир, вилл и офисов с вниманием к деталям и понятным общением.",
        "alt_text": "Русскоязычный клининг квартир в Стамбуле",
        "attributes": [
            ("service-area", "Каяшехир, Башакшехир, Мавера, Эсенюрт, Бейликдюзю, Каваклы", "Kayasehir, Basaksehir, Mavera, Esenyurt, Beylikduzu, Kavakli"),
            ("language", "русский", "Russian"),
            ("format", "квартиры, виллы, офисы", "apartments, villas, offices"),
            ("includes", "генеральная уборка, кухня, санузел, окна", "deep cleaning, kitchen, bathroom, windows"),
            ("price-note", "цена выставляется вручную", "price is set manually"),
        ],
        "case": {
            "title": "Генеральная уборка квартиры",
            "summary": "Квартира подготовлена к комфортному проживанию: кухня, санузел, поверхности и окна приведены в порядок.",
            "description": (
                "Выполнена комплексная уборка квартиры с фокусом на кухню, санузел, горизонтальные поверхности, "
                "плинтусы, двери, ручки и стекла. Дополнительный объем согласуется заранее, чтобы результат "
                "соответствовал состоянию помещения и ожиданиям клиента."
            ),
            "city": "Стамбул",
        },
    },
    {
        "name": "Мытье кондиционеров",
        "slug": "myte-kondicionerov",
        "category_slugs": ["svc-ac-cleaning", "uslugi"],
        "asset": "myte-kondicionerov-og.png",
        "description": (
            "Профессиональное мытье и обслуживание бытовых кондиционеров в Стамбуле. Чистый кондиционер "
            "лучше охлаждает, тише работает, экономнее расходует электричество и помогает поддерживать "
            "свежий воздух дома или в офисе.\n\n"
            "Что входит в услугу:\n"
            "• Аккуратный осмотр внутреннего блока\n"
            "• Снятие и промывка фильтров\n"
            "• Очистка доступных внутренних элементов от пыли и загрязнений\n"
            "• Бережная мойка корпуса и жалюзи\n"
            "• Проверка работы после обслуживания\n"
            "• Рекомендации по дальнейшему уходу\n\n"
            "Услуга подходит для квартир, офисов и небольших коммерческих помещений. Время, район выезда "
            "и количество кондиционеров согласуются индивидуально."
        ),
        "description_en": (
            "Professional washing and maintenance of household air conditioners in Istanbul. The service "
            "includes filter washing, careful cleaning of accessible indoor-unit parts, housing cleaning and "
            "a functional check after service."
        ),
        "meta_title": "Мытье кондиционеров в Стамбуле | Чистка и обслуживание",
        "meta_description": (
            "Мытье и обслуживание кондиционеров в Стамбуле: промывка фильтров, очистка внутреннего блока, "
            "мойка корпуса и проверка работы. Для квартир, офисов и коммерческих помещений."
        ),
        "keywords": (
            "мытье кондиционеров Стамбул, чистка кондиционера Стамбул, обслуживание кондиционеров, "
            "промывка фильтров кондиционера, чистка сплит системы, кондиционер Башакшехир, "
            "кондиционер Эсенюрт, кондиционер Бейликдюзю"
        ),
        "og_title": "Мытье кондиционеров в Стамбуле",
        "og_description": "Чистка фильтров и внутреннего блока для свежего воздуха и стабильной работы кондиционера.",
        "alt_text": "Мытье и обслуживание кондиционеров в Стамбуле",
        "attributes": [
            ("service-area", "Стамбул и ближайшие районы по договоренности", "Istanbul and nearby districts by agreement"),
            ("language", "русский", "Russian"),
            ("format", "выезд на объект", "on-site service"),
            ("includes", "фильтры, внутренний блок, корпус, проверка работы", "filters, indoor unit, housing, function check"),
            ("price-note", "цена выставляется вручную", "price is set manually"),
        ],
        "case": {
            "title": "Плановое обслуживание кондиционера",
            "summary": "Фильтры и внутренний блок очищены, кондиционер проверен после обслуживания.",
            "description": (
                "Проведена аккуратная чистка внутреннего блока: фильтры промыты, доступные элементы очищены "
                "от пыли, корпус и жалюзи приведены в порядок. После обслуживания проверена стабильная работа "
                "кондиционера."
            ),
            "city": "Стамбул",
        },
    },
]


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
    results = []
    for spec in SERVICES:
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
            defaults={
                "name": spec["name"],
                "description": spec["description_en"],
            },
        )

        upload_main_image(service, spec["asset"], spec["alt_text"])
        set_attributes(service, spec["attributes"])
        set_portfolio(service, spec)

        results.append(
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

print(results)
