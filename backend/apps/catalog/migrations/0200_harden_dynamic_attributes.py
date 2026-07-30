from django.db import migrations, models
from django.db.models import Count


LEGACY_ATTRIBUTE_KEYS = {
    "area_sqm": ("area-sqm", 172),
    "rooms_count": ("rooms-count", 179),
}


def canonicalize_legacy_attribute_keys(apps, schema_editor):
    GlobalAttributeKey = apps.get_model("catalog", "GlobalAttributeKey")
    GlobalAttributeKeyTranslation = apps.get_model(
        "catalog",
        "GlobalAttributeKeyTranslation",
    )
    ProductAttributeValue = apps.get_model("catalog", "ProductAttributeValue")
    ServiceAttribute = apps.get_model("catalog", "ServiceAttribute")

    for legacy_slug, (canonical_slug, sort_order) in LEGACY_ATTRIBUTE_KEYS.items():
        legacy = GlobalAttributeKey.objects.filter(slug=legacy_slug).first()
        if legacy is None:
            continue

        canonical = GlobalAttributeKey.objects.filter(slug=canonical_slug).first()
        if canonical is None:
            legacy.slug = canonical_slug
            legacy.sort_order = sort_order
            legacy.save(update_fields=["slug", "sort_order"])
            continue

        category_ids = list(legacy.categories.values_list("pk", flat=True))
        if category_ids:
            canonical.categories.add(*category_ids)

        for translation in GlobalAttributeKeyTranslation.objects.filter(key_obj=legacy):
            existing = GlobalAttributeKeyTranslation.objects.filter(
                key_obj=canonical,
                locale=translation.locale,
            ).first()
            if existing is None:
                translation.key_obj = canonical
                translation.save(update_fields=["key_obj"])
            elif not existing.name and translation.name:
                existing.name = translation.name
                existing.save(update_fields=["name"])

        ProductAttributeValue.objects.filter(attribute_key=legacy).update(
            attribute_key=canonical
        )
        ServiceAttribute.objects.filter(attribute_key=legacy).update(
            attribute_key=canonical
        )
        if canonical.sort_order != sort_order:
            canonical.sort_order = sort_order
            canonical.save(update_fields=["sort_order"])
        legacy.delete()


def deduplicate_product_attribute_values(apps, schema_editor):
    ProductAttributeValue = apps.get_model("catalog", "ProductAttributeValue")
    duplicate_groups = (
        ProductAttributeValue.objects.values(
            "content_type_id",
            "object_id",
            "attribute_key_id",
        )
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )

    for group in duplicate_groups.iterator(chunk_size=500):
        rows = list(
            ProductAttributeValue.objects.filter(
                content_type_id=group["content_type_id"],
                object_id=group["object_id"],
                attribute_key_id=group["attribute_key_id"],
            ).order_by("pk")
        )
        # Новейшая строка лучше отражает последнее фактически применённое
        # значение. Пустые локали безопасно дополняем из более старых строк.
        survivor = rows[-1]
        updates = {}
        for field in ("value", "value_ru", "value_en"):
            if getattr(survivor, field):
                continue
            fallback = next(
                (
                    getattr(row, field)
                    for row in reversed(rows[:-1])
                    if getattr(row, field)
                ),
                None,
            )
            if fallback:
                updates[field] = fallback
        if updates:
            ProductAttributeValue.objects.filter(pk=survivor.pk).update(**updates)
        ProductAttributeValue.objects.filter(
            pk__in=[row.pk for row in rows[:-1]]
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0199_refresh_currency_margin_snapshots"),
    ]

    operations = [
        migrations.RunPython(
            canonicalize_legacy_attribute_keys,
            migrations.RunPython.noop,
        ),
        migrations.RunPython(
            deduplicate_product_attribute_values,
            migrations.RunPython.noop,
        ),
        migrations.RemoveIndex(
            model_name="productattributevalue",
            name="catalog_pro_content_841dfa_idx",
        ),
        migrations.AddConstraint(
            model_name="productattributevalue",
            constraint=models.UniqueConstraint(
                fields=("content_type", "object_id", "attribute_key"),
                name="catalog_pav_object_key_uniq",
            ),
        ),
    ]
