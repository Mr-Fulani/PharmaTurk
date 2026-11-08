"""Отметка «Обработка» заявки в админке: статус для менеджеров, ответственный и журнал.

Клиентский «Статус» заказа здесь не меняется, клиенту ничего не уходит.
Описание — docs/ORDER_PROCESSING.md.
"""

from django.db import transaction

from .models import Order, OrderProcessingEvent


def auto_assign(order: Order, *, actor, old_status: str) -> None:
    """Заявку, которую двигают дальше «Новой» без ответственного, берёт на себя тот, кто двигает."""
    if (
        order.processing_status != old_status
        and order.processing_status != Order.ProcessingStatus.NEW
        and order.assigned_to_id is None
        and actor is not None
    ):
        order.assigned_to = actor


def log_processing_change(order: Order, *, actor, old_status: str, old_assigned_to_id) -> OrderProcessingEvent | None:
    """Запись в журнал, если отметка или ответственный изменились; иначе None."""
    if (order.processing_status, order.assigned_to_id) == (old_status, old_assigned_to_id):
        return None
    return OrderProcessingEvent.objects.create(
        order=order,
        actor=actor,
        old_status=old_status,
        new_status=order.processing_status,
        old_assigned_to_id=old_assigned_to_id,
        new_assigned_to_id=order.assigned_to_id,
    )


def change_processing(order_ids, *, actor, status: str, take: bool = False) -> int:
    """Действие списком: ставит отметку (take — ещё и делает actor ответственным). Возвращает число изменённых."""
    changed = 0
    with transaction.atomic():
        for order in Order.objects.select_for_update().filter(pk__in=list(order_ids)).order_by("pk"):
            old_status, old_assigned_to_id = order.processing_status, order.assigned_to_id
            order.processing_status = status
            if take:
                order.assigned_to = actor
            auto_assign(order, actor=actor, old_status=old_status)
            if log_processing_change(order, actor=actor, old_status=old_status, old_assigned_to_id=old_assigned_to_id):
                order.save(update_fields=["processing_status", "assigned_to", "updated_at"])
                changed += 1
    return changed
