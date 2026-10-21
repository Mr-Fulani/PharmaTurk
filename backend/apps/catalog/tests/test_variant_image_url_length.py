"""Адреса фото вариантов от парсеров длиннее 200 символов (проба на проде 21.10).

LCW: «https://cdn.mudaroba.com/products/clothing/<длинный slug>/…gallery-….jpg» —
208 символов. URLField вариантов по умолчанию 200, и товар не сохранялся:
«value too long for type character varying(200)».
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from apps.catalog import models as catalog_models

LONG_CDN_URL = (
    "https://cdn.mudaroba.com/products/clothing/"
    "top-model-renksiz-sesli-ve-kilitli-mucevher-kutusu-413578-s000608385-10231-lcw-5600150/"
    "lcw-lc-waikiki-s000608385-beden-sec-standart-beden-rehb-gallery-5eeb5a404e.jpg"
)

PARSER_MEDIA_URL_FIELDS = [
    ("ClothingVariant", "main_image"),
    ("ShoeVariant", "main_image"),
    ("JewelryVariant", "main_image"),
    ("FurnitureVariant", "main_image"),
    ("FurnitureVariantImage", "image_url"),
    ("PerfumeryVariant", "main_image"),
    ("PerfumeryVariantImage", "image_url"),
    ("BookVariant", "main_image"),
    ("BookVariantImage", "image_url"),
    ("HeadwearVariant", "main_image"),
    ("UnderwearVariant", "main_image"),
    ("IslamicClothingVariant", "main_image"),
]


@pytest.mark.parametrize(("model_name", "field_name"), PARSER_MEDIA_URL_FIELDS)
def test_parser_media_url_fields_fit_long_cdn_paths(model_name, field_name):
    field = getattr(catalog_models, model_name)._meta.get_field(field_name)
    assert field.max_length >= 2000


@pytest.mark.django_db
def test_clothing_variant_saves_long_cdn_main_image():
    assert len(LONG_CDN_URL) > 200
    product = catalog_models.ClothingProduct.objects.create(
        name="Mücevher Kutusu",
        slug=f"mucevher-kutusu-{uuid4().hex}",
        price=Decimal("1989.93"),
        currency="TRY",
    )

    variant = catalog_models.ClothingVariant.objects.create(
        product=product,
        name="Mücevher Kutusu — Renksiz",
        color="Renksiz",
        sku=f"lcw-{uuid4().hex[:8]}",
        external_id=f"lcw-var-{uuid4().hex[:8]}",
        price=Decimal("1989.93"),
        currency="TRY",
        main_image=LONG_CDN_URL,
    )

    variant.refresh_from_db()
    assert variant.main_image == LONG_CDN_URL
