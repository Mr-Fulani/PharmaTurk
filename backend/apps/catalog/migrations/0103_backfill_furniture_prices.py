from django.db import migrations


def backfill_furniture_prices(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    FurnitureProduct = apps.get_model("catalog", "FurnitureProduct")
    for furniture in FurnitureProduct.objects.all():
        product_id = getattr(furniture, "base_product_id", None)
        if not product_id:
            base_slug = furniture.slug
            slug = base_slug
            i = 2
            while Product.objects.filter(slug=slug).exists():
                suffix = f"-{i}"
                slug = f"{base_slug[:580 - len(suffix)]}{suffix}"
                i += 1
            product = Product.objects.create(
                name=furniture.name,
                slug=slug,
                description=furniture.description,
                category=furniture.category,
                brand=furniture.brand,
                price=furniture.price,
                currency=furniture.currency,
                old_price=furniture.old_price,
                product_type="furniture",
                external_id=furniture.external_id,
                external_url=furniture.external_url,
                external_data=furniture.external_data,
                is_active=furniture.is_active,
                is_new=furniture.is_new,
                is_featured=furniture.is_featured,
            )
            product_id = product.pk
            FurnitureProduct.objects.filter(pk=furniture.pk).update(base_product=product)
        if furniture.price is None or not furniture.currency:
            continue
        from apps.catalog.models import Product as LiveProduct
        live_product = LiveProduct.objects.filter(pk=product_id).first()
        if live_product:
            live_product.update_currency_prices()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0102_add_furniture_base_product"),
    ]

    operations = [
        migrations.RunPython(backfill_furniture_prices, migrations.RunPython.noop),
    ]
