"""Заявка «Найдём товар» ведётся в общем списке «Заказы» (docs/ORDER_PROCESSING.md).

Ссылка, фото и комментарий клиента остаются в SourcingRequest; рядом создаётся Order
типа «Найти товар» с одной позицией — по нему менеджер ведёт те же шаги обработки.
"""

import uuid

from django.db import transaction
from django.utils.text import Truncator

from .models import Order, OrderItem, SourcingRequest

ITEM_NAME_LIMIT = 120


def _item_name(req: SourcingRequest) -> str:
    """Название позиции до того, как менеджер нашёл товар: слова клиента, иначе «по ссылке/фото»."""
    comment = " ".join((req.comment or "").split())
    if comment:
        return Truncator(comment).chars(ITEM_NAME_LIMIT)
    return "Товар по ссылке" if req.source_url else "Товар по фото"


@transaction.atomic
def create_order_for_sourcing_request(req: SourcingRequest) -> Order:
    """Создаёт заявку в «Заказах» для заявки на поиск; повторный вызов возвращает уже созданную."""
    if req.order_id:
        return req.order
    order = Order.objects.create(
        user=req.user,
        number=uuid.uuid4().hex[:12].upper(),
        kind=Order.Kind.SOURCING,
        contact_name=req.contact_name,
        contact_phone=req.contact_phone,
        contact_email=req.contact_email,
        contact_channel=req.contact_channel,
        contact_username=req.contact_username,
        comment=req.comment,
        locale=req.locale if req.locale in ("ru", "en") else "",
    )
    # Цена неизвестна, пока товар не нашли: менеджер вписывает её в позицию на странице заявки
    OrderItem.objects.create(
        order=order,
        product_name=_item_name(req),
        price=0,
        quantity=req.quantity,
        total=0,
        source_url=req.source_url,
    )
    req.order = order
    req.save(update_fields=["order", "updated_at"])
    return order
