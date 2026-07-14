from apps.catalog.constants import BRANDS_DATA


def test_seed_excludes_manually_managed_brands():
    seeded_brands = {
        (category_slug, brand[0])
        for category_slug, brands in BRANDS_DATA.items()
        for brand in brands
    }

    assert seeded_brands.isdisjoint(
        {
            ("islamic-clothing", "Armine"),
            ("supplements", "Now Foods"),
            ("auto-parts", "Tofaş"),
        }
    )
