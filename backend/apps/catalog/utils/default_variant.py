"""Цвет, чья цена — цена товара с цветами (одежда, обувь, головные уборы, бельё).

Одно правило для импорта, обновления карточки при открытии, пересчёта дублей
FLO ↔ SuperStep и витрины: иначе витрина показывала цену одного цвета, а
сортировка и фильтр шли по цене другого (Nautica K35052T, 04.11.2026).
"""


def default_fashion_variant(variants):
    """Первый по порядку цвет в наличии с ценой, иначе первый с ценой, иначе первый.

    ``variants`` — активные цвета, уже по порядку сайта (``sort_order``, ``id``).
    Распроданный цвет не задаёт цену, пока продаётся другой; выбор не зависит
    от того, с какого цвета начали разбор, — цена не «прыгает» между проходами.
    Пустой список — ``None``.
    """
    variants = list(variants)
    if not variants:
        return None
    priced = [row for row in variants if row.price is not None]
    return next(
        (row for row in priced if row.is_available),
        priced[0] if priced else variants[0],
    )
