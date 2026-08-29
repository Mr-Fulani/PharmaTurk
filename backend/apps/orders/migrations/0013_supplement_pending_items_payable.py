from django.db import migrations


def make_supplement_cart_items_payable(apps, schema_editor):
    CartItem = apps.get_model("orders", "CartItem")
    CartItem.objects.filter(
        product__product_type="supplements",
        source_offer__isnull=True,
        verification_status="pending_confirmation",
    ).update(
        verification_status="not_checked",
        verification_issues=[],
    )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0012_cartitem_pending_confirmation"),
    ]

    operations = [
        migrations.RunPython(
            make_supplement_cart_items_payable,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
