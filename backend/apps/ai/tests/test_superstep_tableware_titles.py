"""Партия 9 SuperStep 12.11.2026: термосы Stanley и спорттовары идут мимо правил.

Примеры — товары прода (pid в комментарии).
"""

import pytest

from apps.ai.services.semantic_validator import SemanticValidator
from apps.catalog.models import Brand, Category, Product


def _reasons(name, titles, product_type, brand_name, slug):
    # Разделы как на проде: «drinkware» (Стаканы и бокалы) и «sports» (Спорттовары).
    slug, ru_name = ("drinkware", "Стаканы и бокалы") if product_type == "tableware" else ("sports", "Спорттовары")
    category, _ = Category.objects.update_or_create(slug=slug, defaults={"name": ru_name, "is_active": True})
    brand, _ = Brand.objects.get_or_create(name=brand_name, defaults={"slug": brand_name.lower()})
    product = Product.objects.create(
        name=name, slug=slug, product_type=product_type, category=category, brand=brand
    )
    return SemanticValidator().validate(product, generated_titles=titles, dynamic_attributes=[]).reasons


@pytest.mark.django_db
@pytest.mark.parametrize(
    "name, ru",
    [
        # 31007: «0.89L» токенизатор резал на «89L» — в «0.89 л» его нет.
        ("Stanley The IceFlow Flip Straw 2.0 Tumbler 0.89L Mor Termos", "Термос Stanley The IceFlow Flip Straw 2.0 0.89 л"),
        # 31093: унции «20oz» — тоже объём, не модель.
        ("Stanley The Vitalize 0.59L 20oz Siyah Shaker", "Шейкер Stanley The Vitalize 0,59 л, чёрный"),
    ],
)
def test_volume_in_litres_and_ounces_is_not_model(name, ru):
    reasons = _reasons(name, {"ru": ru}, "tableware", "Stanley", f"s-{abs(hash(name))}")
    assert "title_identity_lost" not in reasons


@pytest.mark.django_db
def test_model_is_still_required():
    # Модель «IceFlow» по-прежнему нужна в названии.
    reasons = _reasons(
        "Stanley The IceFlow Flip Straw 2.0 Tumbler 0.89L Mor Termos", {"ru": "Термос Stanley 0,89 л"},
        "tableware", "Stanley", "s-model",
    )
    assert "title_identity_lost" in reasons


@pytest.mark.django_db
@pytest.mark.parametrize(
    "pid, name, ru, product_type, brand",
    [
        (31044, "Stanley Quencher Pipetli 1.18 L Yeşil Termos", "Термос Stanley Quencher Pipetli 1.18 L", "tableware", "Stanley"),
        (31101, "Stanley Klasik Vakumlu 0.75 L Gri Termos", "Термос Stanley Klasik Vakumlu 0.75 L", "tableware", "Stanley"),
        (31111, "UNITED4 Mor Havlu", "Спортивное полотенце UNITED4 Mor", "sports", "United4"),
        (31122, "Sunnylife Köpek Balığı Çocuk Renkli Su Tabancası", "Детский водный пистолет Sunnylife Köpek Balığı", "sports", "Sunnylife"),
        (31050, "Stanley The Quencher ProTour Flip Straw Tumbler 1.18L Unisex Krem Termos",
         "Stanley The Quencher ProTour Flip Straw Tumbler 1.18L", "tableware", "Stanley"),
    ],
)
def test_untranslated_title_goes_to_moderation(pid, name, ru, product_type, brand):
    assert "title_untranslated" in _reasons(name, {"ru": ru}, product_type, brand, f"u-{pid}")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "pid, name, titles, product_type, brand",
    [
        (31027, "Stanley The All Day Slim 0.60L Unisex Yeşil Termos",
         {"ru": "Термос Stanley The All Day Slim 0.60L", "en": "Stanley The All Day Slim 0.60L Thermos"}, "tableware", "Stanley"),
        (31112, "McKinley Towel Microfiber Unisex Havlu",
         {"ru": "Полотенце McKinley из микрофибры унисекс", "en": "McKinley Microfiber Unisex Towel"}, "sports", "McKinley"),
        # Турецкая буква в бренде — не перевод названия.
        (0, "Paşabahçe Bardak Seti", {"ru": "Набор стаканов Paşabahçe"}, "tableware", "Paşabahçe"),
    ],
)
def test_translated_title_passes(pid, name, titles, product_type, brand):
    assert "title_untranslated" not in _reasons(name, titles, product_type, brand, f"ok-{pid}-{abs(hash(name))}")
