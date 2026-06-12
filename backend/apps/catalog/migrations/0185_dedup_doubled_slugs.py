"""Схлопывает задвоенные слаги (X-X → X) во всех товарных моделях.

Источник задвоения — normalize_product: slug = slugify(name) + external_id,
где у ilacfiyati external_id равен слагу имени (починено в services.py).
Логика дедупликации зеркалит deduplicate_slug (product_resolve.py) и
deduplicateSlug (frontend/src/lib/urls.ts): минимум 4 части, равные половины.
Если дедуплицированный слаг уже занят в той же модели — строку не трогаем
(старый слаг продолжит работать через SmartSlugLookupMixin).
"""

from django.db import migrations

SLUG_MODELS = [
    "Product", "Service",
    "ClothingProduct", "ShoeProduct", "JewelryProduct", "ElectronicsProduct",
    "FurnitureProduct", "BookProduct", "PerfumeryProduct", "MedicineProduct",
    "SupplementProduct", "MedicalEquipmentProduct", "TablewareProduct",
    "AccessoryProduct", "IncenseProduct", "SportsProduct", "AutoPartProduct",
    "HeadwearProduct", "UnderwearProduct", "IslamicClothingProduct",
    "ClothingVariant", "ShoeVariant", "JewelryVariant", "FurnitureVariant",
    "PerfumeryVariant", "BookVariant", "HeadwearVariant", "UnderwearVariant",
    "IslamicClothingVariant",
]


def _deduplicate(slug: str) -> str:
    parts = (slug or "").split("-")
    if len(parts) >= 4 and len(parts) % 2 == 0:
        half = len(parts) // 2
        if parts[:half] == parts[half:]:
            return "-".join(parts[:half])
    return slug


def dedup_slugs(apps, schema_editor):
    for model_name in SLUG_MODELS:
        model = apps.get_model("catalog", model_name)
        taken = set(model.objects.values_list("slug", flat=True))
        for obj in model.objects.only("id", "slug").iterator():
            deduped = _deduplicate(obj.slug)
            if deduped == obj.slug or deduped in taken:
                continue
            taken.discard(obj.slug)
            taken.add(deduped)
            model.objects.filter(pk=obj.pk).update(slug=deduped)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0184_medicineproduct_manufacturer"),
    ]

    # Откат не нужен: исходные задвоенные слаги — мусор, обратные URL
    # продолжают работать через SmartSlugLookupMixin
    operations = [
        migrations.RunPython(dedup_slugs, migrations.RunPython.noop),
    ]
