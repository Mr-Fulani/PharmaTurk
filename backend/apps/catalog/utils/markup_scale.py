"""Шкала наценки: процент зависит от цены источника в лирах.

Ступень задаётся парой «от скольких лир — процент». На границе действует правило
«не дешевле предыдущей ступени»: цена с наценкой не может быть ниже самой дорогой
цены предыдущих ступеней. Поэтому товар дороже в источнике никогда не выходит
покупателю дешевле, а вдали от порога процент равен заданному в ступени.

Модуль не зависит от Django и к ценам сайта пока не подключён.
"""

from dataclasses import dataclass
from decimal import Decimal


HUNDRED = Decimal("100")


@dataclass(frozen=True)
class ScaleResult:
    price_with_markup: Decimal  # в лирах, без округления
    percent: Decimal  # итоговый процент с учётом нижней планки
    step_from: Decimal  # начало сработавшей ступени
    step_percent: Decimal  # процент, записанный в ступени
    floor_applied: bool  # сработало правило «не дешевле предыдущей ступени»


def apply_scale(steps, price):
    """Считает цену с наценкой по шкале.

    steps — пары (от, процент) в любом порядке; price — цена источника в лирах.
    Возвращает None, если шкала пуста или цена не положительна.
    """
    if price is None:
        return None
    price = Decimal(str(price))
    ordered = sorted((Decimal(str(start)), Decimal(str(percent))) for start, percent in steps)
    if not ordered or price <= 0:
        return None

    floor = Decimal("0")
    step_from, step_percent = ordered[0]
    for index, (start, percent) in enumerate(ordered):
        if index and start > price:
            break
        if index:
            previous_percent = ordered[index - 1][1]
            floor = max(floor, start * (1 + previous_percent / HUNDRED))
        step_from, step_percent = start, percent

    nominal = price * (1 + step_percent / HUNDRED)
    final = max(nominal, floor)
    return ScaleResult(
        price_with_markup=final,
        percent=(final / price - 1) * HUNDRED,
        step_from=step_from,
        step_percent=step_percent,
        floor_applied=final > nominal,
    )


def scale_examples(steps):
    """Цены источника для таблицы примеров: середина каждой ступени и обе стороны порогов."""
    starts = sorted(Decimal(str(start)) for start, _percent in steps)
    if not starts:
        return []
    points = set()
    for index, start in enumerate(starts):
        if index + 1 < len(starts):
            points.add((start + starts[index + 1]) / 2)
        else:
            points.add(start * 2 if start > 0 else Decimal("1000"))
        if start > 0:
            points.update({start - 10, start + 10})
    return sorted(point for point in points if point > 0)


def scale_floors(steps):
    """Ступени с нижней планкой: [(от, процент, планка цены с наценкой в лирах)].

    То же правило, что в apply_scale, в виде таблицы — для расчёта в SQL (фильтр по цене).
    """
    ordered = sorted((Decimal(str(start)), Decimal(str(percent))) for start, percent in steps)
    result, floor = [], Decimal("0")
    for index, (start, percent) in enumerate(ordered):
        if index:
            floor = max(floor, start * (1 + ordered[index - 1][1] / HUNDRED))
        result.append((start, percent, floor))
    return result
