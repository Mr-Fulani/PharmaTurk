from apps.catalog.attribute_specs import (
    canonicalize_dynamic_attribute_value,
    extract_dynamic_attribute_candidates,
    is_facet_attribute_allowed,
)


def test_closure_type_is_canonicalized():
    assert canonicalize_dynamic_attribute_value("closure-type", "шнурки", product_type="shoes") == "Шнуровка"
    assert canonicalize_dynamic_attribute_value("closure-type", "Bağcık", product_type="shoes") == "Шнуровка"


def test_extract_dynamic_attribute_candidates_uses_whitelist_only():
    candidates = extract_dynamic_attribute_candidates(
        "shoes",
        {
            "malzeme": "Suni deri",
            "baglama_sekli": "Bağcık",
            "taban_malzeme": "Kauçuk",
            "unexpected_internal_note": "do not show this",
        },
    )

    assert [(item.slug, item.value_ru) for item in candidates] == [
        ("material", "Искусственная кожа"),
        ("sole-material", "Каучук"),
        ("closure-type", "Шнуровка"),
    ]


def test_unknown_facet_slug_is_blocked_for_product_type():
    assert is_facet_attribute_allowed("shoes", "closure-type") is True
    assert is_facet_attribute_allowed("shoes", "unexpected_internal_note") is False
