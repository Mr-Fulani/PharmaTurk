"""Safe ownership transfer for orders created before account verification."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def link_guest_orders_for_verified_user(user) -> int:
    """Attach guest orders only after the user proved ownership of the email."""
    email = str(getattr(user, "email", "") or "").strip()
    if (
        not getattr(user, "is_verified", False)
        or not email
        or email.lower().endswith("@mudaroba.local")
    ):
        return 0

    from apps.orders.models import Order

    count = (
        Order.objects.filter(user__isnull=True, contact_email__iexact=email)
        .exclude(status="cancelled")
        .update(user=user)
    )
    if count:
        logger.info("Linked %s verified guest order(s) to user_id=%s", count, user.pk)
    return count
