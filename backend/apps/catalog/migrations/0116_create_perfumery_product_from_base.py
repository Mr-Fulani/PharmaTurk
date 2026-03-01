# Data migration: create PerfumeryProduct for existing Product with product_type='perfumery'
# so they appear in admin "Товары — Парфюмерия"

from django.db import migrations


def create_perfumery_products_from_base(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    PerfumeryProduct = apps.get_model("catalog", "PerfumeryProduct")

    for product in Product.objects.filter(product_type="perfumery"):
        if PerfumeryProduct.objects.filter(base_product_id=product.pk).exists():
            continue

        kwargs = {
            "name": product.name or "",
            "slug": product.slug,
            "description": product.description or "",
            "category_id": product.category_id,
            "brand_id": product.brand_id,
            "price": product.price,
            "old_price": product.old_price,
            "currency": product.currency or "RUB",
            "main_image": product.main_image or "",
            "external_id": getattr(product, "external_id", "") or "",
            "external_url": getattr(product, "external_url", "") or "",
            "external_data": getattr(product, "external_data", {}) or {},
            "is_active": getattr(product, "is_active", True),
            "is_new": getattr(product, "is_new", False),
            "is_featured": getattr(product, "is_featured", False),
            "base_product_id": product.pk,
        }
        if hasattr(PerfumeryProduct, "is_available"):
            kwargs["is_available"] = getattr(product, "is_available", True)
        PerfumeryProduct.objects.create(**kwargs)


def noop_reverse(apps, schema_editor):
    # Optional: could delete PerfumeryProduct created by this migration.
    # We don't delete to avoid data loss; run forward again is idempotent.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0115_add_category_incense_proxy"),
    ]

    operations = [
        migrations.RunPython(create_perfumery_products_from_base, noop_reverse),
    ]
