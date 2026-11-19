"""Больничные препараты: справочная отметка «Больничный препарат».

Отметка — ``MedicineProduct.is_hospital`` (растворы для капельниц, диализ, кожные пробы,
радиофармпрепараты и препараты только с госценой). Решение владельца 19.11.2026: сайт — справочник,
цену не скрываем. Больничный препарат с ценой ведёт себя как обычное лекарство (цена в API, в
«Списке заявки» и в сумме), отметка — только подпись рядом с ценой. Без цены — «Больничный
препарат · цена по запросу»: в сумму не входит, в справочный блок главной и рекомендации не
попадает. Подробно — docs/HOSPITAL_MEDICINES.md.
"""
from django.db.models import Q

# Для запросов по базовому товару (Product): больничный препарат без цены.
HOSPITAL_WITHOUT_PRICE_Q = Q(medicine_item__is_hospital=True) & (Q(price__isnull=True) | Q(price__lte=0))


def is_hospital_product(product) -> bool:
    """Базовый товар (Product) или лекарство (MedicineProduct) отмечен как больничный препарат."""
    if product is None:
        return False
    if hasattr(product, "is_hospital"):
        return bool(product.is_hospital)
    if getattr(product, "product_type", "") != "medicines":
        return False
    from django.core.exceptions import ObjectDoesNotExist

    try:
        return bool(product.medicine_item.is_hospital)
    except ObjectDoesNotExist:
        return False
