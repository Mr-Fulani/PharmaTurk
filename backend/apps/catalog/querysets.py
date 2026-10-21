"""Общие условия публичных queryset каталога."""

from django.db import models


def non_public_shadow_product_q(prefix: str = '') -> models.Q:
    """Служебные Product-записи вне публичной витрины."""
    def field(name: str) -> str:
        return f'{prefix}{name}'

    return (
        models.Q(**{field('external_data__has_key'): 'source_variant_id'})
        | models.Q(**{field('external_data__has_key'): 'source_variant_slug'})
        | (
            models.Q(**{field('product_type'): 'medicines'})
            & models.Q(**{field('external_data__has_key'): 'is_stub'})
            & models.Q(**{field('external_data__is_stub'): True})
        )
    )


def source_variant_q() -> models.Q:
    """Доменные строки — копии вариантов исходного товара, а не отдельные товары."""
    return (
        models.Q(external_data__has_key='source_variant_id')
        | models.Q(external_data__has_key='source_variant_slug')
    )
