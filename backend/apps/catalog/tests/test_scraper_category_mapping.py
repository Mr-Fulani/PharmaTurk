import pytest

from apps.catalog.scraper_category_mapping import resolve_category_and_product_type


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
