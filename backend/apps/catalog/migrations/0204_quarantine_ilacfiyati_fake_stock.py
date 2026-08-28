from django.db import migrations, models


def quarantine_ilacfiyati_fake_stock(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    ProductSourceOffer = apps.get_model("catalog", "ProductSourceOffer")
    SupplementProduct = apps.get_model("catalog", "SupplementProduct")

    supplement_qs = SupplementProduct.objects.filter(
        models.Q(external_url__startswith="https://ilacfiyati.com/takviye-edici-gida/")
        | models.Q(external_url__startswith="https://www.ilacfiyati.com/takviye-edici-gida/")
        | models.Q(
            base_product__external_url__startswith=("https://ilacfiyati.com/takviye-edici-gida/")
        )
        | models.Q(
            base_product__external_url__startswith=(
                "https://www.ilacfiyati.com/takviye-edici-gida/"
            )
        )
        | models.Q(external_data__source__iexact="ilacfiyati")
        | models.Q(base_product__external_data__source__iexact="ilacfiyati")
    )
    base_product_ids = list(
        supplement_qs.exclude(base_product_id=None).values_list(
            "base_product_id",
            flat=True,
        )
    )
    supplement_qs.update(is_available=False, stock_quantity=None)
    if base_product_ids:
        Product.objects.filter(pk__in=base_product_ids).update(
            is_available=False,
            stock_quantity=None,
        )

    ProductSourceOffer.objects.filter(parser_key__iexact="ilacfiyati").update(
        availability_status="unknown",
        stock_precision="unknown",
        stock_quantity=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0203_productmarketcheck_medicineanalog_market_fields"),
    ]

    operations = [
        migrations.RunPython(
            quarantine_ilacfiyati_fake_stock,
            migrations.RunPython.noop,
        ),
    ]
