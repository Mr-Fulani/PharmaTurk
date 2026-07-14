import pytest

from apps.catalog.scraper_category_mapping import resolve_category_and_product_type
from apps.catalog.models import Category, CategoryType


@pytest.mark.django_db
def test_exact_subcategory_slug_has_priority_over_root_term_alias():
    shoes_type = CategoryType.objects.filter(slug="shoes").first()
    if shoes_type is None:
        shoes_type = CategoryType.objects.create(name="Test shoes", slug="shoes")

    shoes = Category.objects.filter(slug="shoes").first()
    if shoes is None:
        shoes = Category.objects.create(
            name="Test shoes root", slug="shoes", category_type=shoes_type
        )

    sandals = Category.objects.filter(slug="sandals").first()
    if sandals is None:
        sandals = Category.objects.create(
            name="Test sandals",
            slug="sandals",
            category_type=shoes_type,
            parent=shoes,
        )

    category, product_type = resolve_category_and_product_type("sandals")

    assert category == sandals
    assert product_type == "shoes"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("category_value", "expected_slug", "expected_product_type"),
    [
        ("AKSESUAR", "accessories", "accessories"),
        ("Çanta", "accessories", "accessories"),
        ("Kemer", "accessories", "accessories"),
        ("Cüzdan", "accessories", "accessories"),
        ("Saat", "accessories", "accessories"),
        ("Seyahat", "accessories", "accessories"),
        ("Takı", "jewelry", "jewelry"),
        ("KOZMETİK | KİŞİSEL BAKIM", "perfumery", "perfumery"),
        ("Makyaj", "perfumery", "perfumery"),
        ("Cilt Bakım", "perfumery", "perfumery"),
        ("Güneş Bakım", "perfumery", "perfumery"),
        ("Vücut Bakım", "perfumery", "perfumery"),
        ("Parfüm", "perfumery", "perfumery"),
        ("Şapka", "headwear", "headwear"),
        ("Kep Şapka", "headwear", "headwear"),
        ("Bere", "headwear", "headwear"),
        ("Boxer", "underwear", "underwear"),
        ("Sütyen", "underwear", "underwear"),
    ],
)
def test_resolve_category_and_product_type_supports_lcw_turkish_aliases(
    category_value,
    expected_slug,
    expected_product_type,
):
    category, product_type = resolve_category_and_product_type(category_value)

    assert category is not None
    assert category.slug == expected_slug
    assert product_type == expected_product_type
