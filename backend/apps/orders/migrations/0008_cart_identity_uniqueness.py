from django.db import migrations
from django.db.models import Count


MAX_POSITIVE_INTEGER = 2_147_483_647


def _merge_cart_group(Cart, CartItem, database_alias, lookup):
    carts = list(
        Cart.objects.using(database_alias)
        .filter(**lookup)
        .order_by("id")
    )
    if len(carts) < 2:
        return

    canonical = carts[0]
    promo_code_id = canonical.promo_code_id
    latest_update = canonical.updated_at

    for duplicate in carts[1:]:
        if promo_code_id is None and duplicate.promo_code_id is not None:
            promo_code_id = duplicate.promo_code_id
        if duplicate.updated_at and (
            latest_update is None or duplicate.updated_at > latest_update
        ):
            latest_update = duplicate.updated_at

        items = (
            CartItem.objects.using(database_alias)
            .filter(cart_id=duplicate.id)
            .order_by("id")
        )
        for item in items.iterator(chunk_size=500):
            existing = (
                CartItem.objects.using(database_alias)
                .filter(
                    cart_id=canonical.id,
                    product_id=item.product_id,
                    chosen_size=item.chosen_size,
                )
                .first()
            )
            if existing is None:
                CartItem.objects.using(database_alias).filter(pk=item.pk).update(
                    cart_id=canonical.id
                )
                continue

            quantity = min(
                int(existing.quantity) + int(item.quantity),
                MAX_POSITIVE_INTEGER,
            )
            CartItem.objects.using(database_alias).filter(pk=existing.pk).update(
                quantity=quantity
            )
            CartItem.objects.using(database_alias).filter(pk=item.pk).delete()

        Cart.objects.using(database_alias).filter(pk=duplicate.pk).delete()

    Cart.objects.using(database_alias).filter(pk=canonical.pk).update(
        promo_code_id=promo_code_id,
        updated_at=latest_update,
    )


def merge_duplicate_cart_identities(apps, schema_editor):
    Cart = apps.get_model("orders", "Cart")
    CartItem = apps.get_model("orders", "CartItem")
    database_alias = schema_editor.connection.alias

    duplicate_users = (
        Cart.objects.using(database_alias)
        .filter(user__isnull=False)
        .values("user_id")
        .annotate(cart_count=Count("id"))
        .filter(cart_count__gt=1)
        .order_by("user_id")
    )
    for group in duplicate_users.iterator(chunk_size=500):
        _merge_cart_group(
            Cart,
            CartItem,
            database_alias,
            {"user_id": group["user_id"]},
        )

    duplicate_sessions = (
        Cart.objects.using(database_alias)
        .filter(user__isnull=True)
        .exclude(session_key="")
        .values("session_key")
        .annotate(cart_count=Count("id"))
        .filter(cart_count__gt=1)
        .order_by("session_key")
    )
    for group in duplicate_sessions.iterator(chunk_size=500):
        _merge_cart_group(
            Cart,
            CartItem,
            database_alias,
            {"user__isnull": True, "session_key": group["session_key"]},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0007_update_currency_max_length"),
    ]

    operations = [
        migrations.RunPython(
            merge_duplicate_cart_identities,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
