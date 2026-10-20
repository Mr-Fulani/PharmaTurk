"""Зачёркнутая («старая») цена товара — только цена, которую показывает источник."""

from decimal import Decimal, InvalidOperation


def source_old_price(old_price, price):
    """Зачёркнутая цена источника, если она выше текущей; иначе ``None``.

    Прежняя наблюдённая цена — не скидка: после её записи в old_price любое
    снижение цены превращалось в бессрочную «скидку» на витрине, а рост цены
    и смена валюты оставляли бессмысленные значения.
    """
    try:
        old = Decimal(str(old_price)) if old_price not in (None, "") else None
        current = Decimal(str(price)) if price not in (None, "") else None
    except (InvalidOperation, ValueError, TypeError):
        return None
    if old is None or current is None or current <= 0 or old <= current:
        return None
    return old
