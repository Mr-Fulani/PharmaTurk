"""Ссылка «товар в админке»: страница доменной записи (лекарство, БАД, обувь…), иначе общая карточка.

Только на странице доменной записи есть свои панели раздела — например, у лекарства
«Наличие и цена: проверка по источникам» (docs/DRUG_CHECK.md).
"""
from django.db.models import Prefetch
from django.urls import NoReverseMatch, reverse

from .domain_sync import domain_models


def _accessor(model) -> str:
    return model._meta.get_field("base_product").remote_field.get_accessor_name()


def domain_record_prefetches(product_path: str = "") -> list:
    """Предзагрузка доменных записей для product_admin_url: по запросу на тип, а не на строку списка.

    product_path — путь до товара от модели списка («product» для позиции заказа).
    """
    prefix = f"{product_path}__" if product_path else ""
    return [
        Prefetch(f"{prefix}{_accessor(model)}", queryset=model.objects.only("pk", "base_product_id"))
        for model in domain_models().values()
    ]


def product_admin_url(product) -> str:
    """Адрес страницы доменной записи товара (по его текущему типу); если её нет — общей карточки."""
    model = domain_models().get(str(product.product_type or "").replace("-", "_"))
    record = getattr(product, _accessor(model), None) if model else None
    if record is not None:
        try:
            return reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_change", args=[record.pk])
        except NoReverseMatch:  # у типа нет своего раздела в админке
            pass
    return reverse("admin:catalog_product_change", args=[product.pk])
