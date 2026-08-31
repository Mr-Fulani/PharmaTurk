from django.db import migrations, models


def restore_instagram_catalog_availability(apps, schema_editor):
    """Instagram posts are manual stock, so missing caption prices are not absence."""

    Product = apps.get_model("catalog", "Product")
    ProductSourceOffer = apps.get_model("catalog", "ProductSourceOffer")

    offer_product_ids = ProductSourceOffer.objects.filter(
        parser_key__iexact="instagram"
    ).values_list("product_id", flat=True)
    products = Product.objects.filter(
        models.Q(pk__in=offer_product_ids)
        | models.Q(external_url__icontains="instagram.com")
        | models.Q(external_data__source__iexact="instagram")
    )
    product_ids = list(products.values_list("pk", flat=True))

    if product_ids:
        products.update(
            is_available=True,
            availability_status="in_stock",
        )
        for model_name in (
            "BookProduct",
            "ClothingProduct",
            "ShoeProduct",
            "JewelryProduct",
            "ElectronicsProduct",
            "FurnitureProduct",
            "PerfumeryProduct",
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
        ):
            model = apps.get_model("catalog", model_name)
            model.objects.filter(base_product_id__in=product_ids).update(is_available=True)

    ProductSourceOffer.objects.filter(parser_key__iexact="instagram").update(
        availability_status="in_stock",
        stock_precision="unknown",
        stock_quantity=None,
        last_error_code="",
        last_error_message="",
        consecutive_failures=0,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0205_media_enrichment_manual_moderation"),
    ]

    operations = [
        migrations.RunPython(
            restore_instagram_catalog_availability,
            migrations.RunPython.noop,
        ),
    ]
