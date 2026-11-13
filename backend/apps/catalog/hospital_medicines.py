"""Больничные препараты: справочная карточка «Больничный препарат · цена по запросу».

Решение владельца 13.11.2026: больничные препараты (растворы для капельниц, диализ, кожные пробы,
радиофармпрепараты и препараты только с госценой) не скрываются — у нас справочник лекарств.
Отметка — ``MedicineProduct.is_hospital``. Цена у такого товара в базе остаётся (её обновляет парсер),
но на сайте не показывается и не считается: в API цена пустая, в «Списке заявки» позиция без суммы,
в фиды ВК/Яндекса, хиты и подборки не попадает. Подробно — docs/HOSPITAL_MEDICINES.md.
"""
from django.db.models import Q

# Поля цены в ответах API товара, которые у больничного препарата пустые.
HOSPITAL_HIDDEN_PRICE_FIELDS = (
    "price", "price_formatted", "old_price", "old_price_formatted",
    "converted_price_rub", "converted_price_usd", "final_price_rub", "final_price_usd",
    "margin_percent_applied", "prices_in_currencies", "current_price", "price_breakdown",
    "active_variant_price", "active_variant_old_price_formatted",
)

# Для запросов по базовому товару (Product): исключить больничные.
HOSPITAL_PRODUCT_Q = Q(medicine_item__is_hospital=True)


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


def hide_hospital_price(data: dict) -> dict:
    """Ответ API больничного препарата: цены пустые, ``is_hospital: true``."""
    for field in HOSPITAL_HIDDEN_PRICE_FIELDS:
        if field in data:
            data[field] = None
    data["is_hospital"] = True
    return data
