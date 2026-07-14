from apps.catalog.constants import ACCESSORIES_SUBCATEGORIES
from apps.catalog.management.commands.seed_catalog_data import SUBCAT_TO_ROOT


def test_accessories_seed_excludes_categories_with_dedicated_roots():
    top_level_slugs = {item[2] for item in ACCESSORIES_SUBCATEGORIES}

    assert top_level_slugs.isdisjoint(
        {"acc-jewelry", "fashion-jewelry", "acc-headwear"}
    )
    assert not {
        "acc-jewelry",
        "fashion-jewelry",
        "acc-headwear",
    }.intersection(SUBCAT_TO_ROOT)
