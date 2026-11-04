"""Пути фото и видео товаров длиннее 100 символов (путь раздела + slug)."""

from django.apps import apps
from django.db.models import FileField

PRODUCT_MEDIA_SUFFIXES = ("Product", "ProductImage", "Variant", "VariantImage")


def test_product_media_paths_fit_long_category_paths():
    """С max_length по умолчанию (100) путь products/headwear/hw-caps/
    hw-baseball-caps/… не помещался: «Storage can not find an available
    filename», файл пустой, фото качались заново при каждом проходе."""
    short = [
        f"{model.__name__}.{field.name}"
        for model in apps.get_app_config("catalog").get_models()
        if model.__name__.endswith(PRODUCT_MEDIA_SUFFIXES)
        for field in model._meta.fields
        if isinstance(field, FileField) and field.max_length < 500
    ]

    assert short == []
