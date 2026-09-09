import pytest

from apps.catalog.medicine_taxonomy import (
    ATC_CATEGORY_RULES, ATC_REQUIRING_REVIEW, MEDICINE_CATEGORY_SLUGS, MEDICINES_SUBCATEGORIES,
    RETIRED_MEDICINE_CATEGORY_SLUGS, propose_medicine_category,
)


def test_flat_compact_taxonomy_has_no_duplicates_or_supplement_branches():
    assert len(MEDICINES_SUBCATEGORIES) == len(MEDICINE_CATEGORY_SLUGS) == 16
    assert all(not row[5] for row in MEDICINES_SUBCATEGORIES)
    assert not MEDICINE_CATEGORY_SLUGS & RETIRED_MEDICINE_CATEGORY_SLUGS
    assert {slug for _, slug in ATC_CATEGORY_RULES} == MEDICINE_CATEGORY_SLUGS


@pytest.mark.parametrize("code,slug", [
    ("J01CA04", "antibiotics"), ("J01DD", "antibiotics"),
    ("J05AB01", "antiinfectives-vaccines"), ("J07", "antiinfectives-vaccines"),
    ("P02", "antiinfectives-vaccines"),
    ("D06BB03", "dermatology"), ("G01AA10", "urology-gynecology"),
    ("S01AA01", "ophthalmology"), ("A07AA02", "gastro"),
    ("A10BA02", "endocrinology-diabetes"), ("H03AA01", "endocrinology-diabetes"),
    ("C09AA05", "cardio"), ("B03AC", "blood-hematology"),
    ("R06AX29", "allergy"), ("V01AA", "allergy"),
    ("R03AC02", "respiratory-ent"), ("R05X", "respiratory-ent"),
    ("S02AA15", "respiratory-ent"),
    ("N02BE01", "painkillers"), ("M01AE01", "painkillers"),
    ("M02AC", "painkillers"), ("M01CA", "musculoskeletal"),
    ("M05BA04", "musculoskeletal"), ("N05BA01", "nervous-system"),
    ("N02BF01", "painkillers"), ("N02BF02", "painkillers"),
    ("L04AA44", "oncology-immunology"), ("V06DB", "other-medicines"),
    (" r06ax29 ", "allergy"),
])
def test_atc_rules_preserve_organ_and_route_groups(code, slug):
    result = propose_medicine_category(atc_code=code)
    assert result.status == "proposed"
    assert result.category_slug == slug
    assert result == propose_medicine_category(atc_code=code)


@pytest.mark.parametrize("code", ["", "-", "antibiotic", "J", "A99ZZ99", "C06AA01", "J01CA0", "QJ01CA04", "J01CA04 (amoxicillin)"])
def test_invalid_or_missing_codes_are_not_guessed(code):
    result = propose_medicine_category(atc_code=code)
    assert result.status == "review"
    assert result.category_slug is None


@pytest.mark.parametrize("code", ["M01", "S03AA01", "J01CA04/D06AX01", "A10BA02; A02BC01"])
def test_ambiguous_groups_need_review(code):
    result = propose_medicine_category(atc_code=code)
    assert result.status == "review"
    assert result.reason == "ambiguous_atc"


def test_multiple_codes_in_one_group_are_supported():
    assert propose_medicine_category(atc_code="J01CA04 / J01CR02").category_slug == "antibiotics"


def test_source_conflicts_are_not_silently_overwritten():
    assert propose_medicine_category(atc_code="J01CA04", source_atc_code="D06AX01").reason == "source_atc_conflict"
    assert propose_medicine_category(atc_code="J01CA04", barcode="111", source_barcode="222").reason == "source_barcode_conflict"


def test_own_source_can_fill_missing_code_but_not_invalid_code():
    assert propose_medicine_category(source_atc_code="A10BA02").category_slug == "endocrinology-diabetes"
    assert propose_medicine_category(atc_code="?", source_atc_code="A10BA02").status == "review"


@pytest.mark.parametrize("slug", ["antibiotics", "cardio", "custom-manual-category", "heart-cardiovascular"])
def test_existing_specific_category_is_preserved_even_when_atc_disagrees(slug):
    result = propose_medicine_category(atc_code="J01CA04", current_category_slug=slug)
    assert result.status == "preserve"
    assert result.category_slug == slug


def test_root_is_only_a_fallback_and_stubs_are_not_classified():
    assert propose_medicine_category(atc_code="J01CA04", current_category_slug="medicines").status == "proposed"
    assert propose_medicine_category(atc_code="J01CA04", is_stub=True).status == "stub"


@pytest.mark.parametrize("code", sorted(ATC_REQUIRING_REVIEW))
def test_obsolete_cross_group_or_deleted_codes_need_review(code):
    assert propose_medicine_category(atc_code=code).reason == "obsolete_atc_requires_review"
