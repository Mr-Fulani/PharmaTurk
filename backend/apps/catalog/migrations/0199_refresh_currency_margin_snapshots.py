from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations


CURRENCIES = ("RUB", "USD", "KZT", "EUR", "TRY", "USDT")


def refresh_snapshots(apps, schema_editor):
    MarginSettings = apps.get_model("catalog", "MarginSettings")
    ProductPrice = apps.get_model("catalog", "ProductPrice")
    ProductVariantPrice = apps.get_model("catalog", "ProductVariantPrice")
    ServicePrice = apps.get_model("catalog", "ServicePrice")
    Product = apps.get_model("catalog", "Product")

    margins = dict(
        MarginSettings.objects.filter(is_active=True).values_list(
            "currency_pair", "margin_percentage"
        )
    )

    for model in (ProductPrice, ProductVariantPrice, ServicePrice):
        fields = [f"{currency.lower()}_price_with_margin" for currency in CURRENCIES]
        pending = []
        for row in model.objects.all().iterator(chunk_size=500):
            for currency in CURRENCIES:
                raw = getattr(row, f"{currency.lower()}_price")
                if raw is None:
                    value = None
                else:
                    pair = f"{(row.base_currency or '').upper()}-{currency}"
                    margin = Decimal(str(margins.get(pair, 0)))
                    value = (Decimal(str(raw)) * (Decimal("1") + margin / Decimal("100"))).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                setattr(row, f"{currency.lower()}_price_with_margin", value)
            pending.append(row)
            if len(pending) >= 500:
                model.objects.bulk_update(pending, fields, batch_size=500)
                pending.clear()
        if pending:
            model.objects.bulk_update(pending, fields, batch_size=500)

    products = [
        Product(
            pk=price.product_id,
            final_price_rub=price.rub_price_with_margin,
            final_price_usd=price.usd_price_with_margin,
        )
        for price in ProductPrice.objects.only(
            "product_id", "rub_price_with_margin", "usd_price_with_margin"
        ).iterator(chunk_size=500)
    ]
    Product.objects.bulk_update(
        products, ["final_price_rub", "final_price_usd"], batch_size=500
    )


class Migration(migrations.Migration):
    dependencies = [("catalog", "0198_split_shipping_admin")]

    operations = [migrations.RunPython(refresh_snapshots, migrations.RunPython.noop)]
