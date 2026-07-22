from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from apps.catalog.models import Service, ServiceImage


ASSET_DIR = Path("/app/tmp_service_photos")

MEDIA = {
    9: {
        "og": "sites-portrait-og-v2.png",
        "og_alt": "Разработка сайтов под ключ на Django и React",
        "gallery": [
            ("portrait-smile.jpeg", "Разработчик сайтов на Python, Django и React"),
            ("portrait-suit.jpeg", "Full-stack разработчик сайтов под ключ"),
        ],
    },
    10: {
        "og": "mini-apps-portrait-og-v2.png",
        "og_alt": "Разработка Telegram Mini Apps под ключ",
        "gallery": [
            ("portrait-suit-side.jpeg", "Разработчик Telegram Mini Apps на Python и React"),
            ("portrait-smile.jpeg", "Создание Telegram Mini Apps для бизнеса"),
        ],
    },
    11: {
        "og": "bots-portrait-og-v2.png",
        "og_alt": "Разработка Telegram-ботов на Python",
        "gallery": [
            ("portrait-headshot.jpeg", "Python-разработчик Telegram-ботов"),
            ("portrait-casual.jpeg", "Создание Telegram-ботов для бизнеса"),
        ],
    },
    12: {
        "og": "automation-portrait-og-v2.png",
        "og_alt": "Автоматизация бизнеса на Python",
        "gallery": [
            ("portrait-casual.jpeg", "Специалист по автоматизации бизнеса на Python"),
            ("portrait-headshot.jpeg", "Интеграция CRM и API на Python"),
        ],
    },
}


with transaction.atomic():
    results = []
    for service_id, spec in MEDIA.items():
        service = Service.objects.select_for_update().get(pk=service_id)
        old_main_name = service.main_image_file.name

        service.main_image_file.save(
            spec["og"], ContentFile((ASSET_DIR / spec["og"]).read_bytes()), save=False
        )
        service.main_image = ""
        service.og_image_url = default_storage.url(service.main_image_file.name)
        service.save(
            update_fields=["main_image_file", "main_image", "og_image_url", "updated_at"]
        )

        service.images.update(is_main=False)
        if old_main_name:
            service.images.filter(image_file=old_main_name).delete()
        ServiceImage.objects.update_or_create(
            service=service,
            image_file=service.main_image_file.name,
            defaults={
                "alt_text": spec["og_alt"],
                "sort_order": 0,
                "is_main": True,
            },
        )

        existing = list(service.images.exclude(is_main=True).order_by("id")[:2])
        existing_alts = [
            f"Визитка разработчика: {service.name}",
            f"Рабочее место разработчика: {service.name}",
        ]
        for image, alt in zip(existing, existing_alts):
            image.alt_text = alt
            image.save(update_fields=["alt_text"])

        for order, (filename, alt_text) in enumerate(spec["gallery"], start=3):
            image = service.images.filter(alt_text=alt_text).first()
            if not image:
                image = ServiceImage(
                    service=service,
                    alt_text=alt_text,
                    sort_order=order,
                    is_main=False,
                )
                image.image_file.save(
                    filename, ContentFile((ASSET_DIR / filename).read_bytes()), save=False
                )
                image.save()

        results.append(
            {
                "id": service.pk,
                "og": service.og_image_url,
                "images": service.images.count(),
                "main": service.images.filter(is_main=True).count(),
            }
        )

print(results)
