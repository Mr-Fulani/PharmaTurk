from django.db import migrations
from django.db.models import Q


DOMAIN_PRODUCT_MODELS = (
    "ClothingProduct",
    "ShoeProduct",
    "JewelryProduct",
    "ElectronicsProduct",
    "FurnitureProduct",
    "BookProduct",
    "PerfumeryProduct",
    "MedicineProduct",
    "SupplementProduct",
    "MedicalEquipmentProduct",
    "TablewareProduct",
    "AccessoryProduct",
    "IncenseProduct",
    "SportsProduct",
    "AutoPartProduct",
    "HeadwearProduct",
    "UnderwearProduct",
    "IslamicClothingProduct",
)


def canonicalize_favorite_product_identity(apps, schema_editor):
    """Move legacy domain favorites onto the same Product identity as CartItem."""
    db_alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Favorite = apps.get_model("catalog", "Favorite")

    if not Favorite.objects.using(db_alias).exists():
        return

    product_content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="catalog",
        model="product",
    )

    for model_name in DOMAIN_PRODUCT_MODELS:
        domain_model = apps.get_model("catalog", model_name)
        domain_content_type = ContentType.objects.using(db_alias).filter(
            app_label="catalog",
            model=model_name.lower(),
        ).first()
        if domain_content_type is None:
            continue

        last_pk = 0
        while True:
            batch = list(
                Favorite.objects.using(db_alias)
                .filter(content_type_id=domain_content_type.pk, pk__gt=last_pk)
                .order_by("pk")[:500]
            )
            if not batch:
                break
            last_pk = batch[-1].pk

            base_product_ids = dict(
                domain_model.objects.using(db_alias)
                .filter(pk__in=[favorite.object_id for favorite in batch])
                .exclude(base_product_id__isnull=True)
                .values_list("pk", "base_product_id")
            )
            candidates = [
                (favorite, base_product_ids.get(favorite.object_id))
                for favorite in batch
                if base_product_ids.get(favorite.object_id)
            ]
            if not candidates:
                continue

            user_ids = {favorite.user_id for favorite, _ in candidates if favorite.user_id}
            session_keys = {
                favorite.session_key
                for favorite, _ in candidates
                if not favorite.user_id and favorite.session_key
            }
            owner_query = Q()
            if user_ids:
                owner_query |= Q(user_id__in=user_ids)
            if session_keys:
                owner_query |= Q(session_key__in=session_keys)

            existing_keys = set()
            if user_ids or session_keys:
                existing_rows = (
                    Favorite.objects.using(db_alias)
                    .filter(
                        owner_query,
                        content_type_id=product_content_type.pk,
                        object_id__in=[base_id for _, base_id in candidates],
                    )
                    .values_list("user_id", "session_key", "object_id", "chosen_size")
                )
                existing_keys.update(existing_rows)

            for favorite, base_product_id in candidates:
                identity_key = (
                    favorite.user_id,
                    favorite.session_key,
                    base_product_id,
                    favorite.chosen_size or "",
                )
                if identity_key in existing_keys:
                    Favorite.objects.using(db_alias).filter(pk=favorite.pk).delete()
                    continue

                Favorite.objects.using(db_alias).filter(pk=favorite.pk).update(
                    content_type_id=product_content_type.pk,
                    object_id=base_product_id,
                )
                existing_keys.add(identity_key)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0200_harden_dynamic_attributes"),
    ]

    operations = [
        migrations.RunPython(
            canonicalize_favorite_product_identity,
            migrations.RunPython.noop,
        ),
    ]
