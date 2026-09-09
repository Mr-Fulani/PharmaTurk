"""Compact storefront taxonomy and a pure, conservative ATC proposal engine.

Not a clinical recommendation or an ATC-code assignment service. Categories are
navigation groups. Reference: https://atcddd.fhi.no/atc_ddd_index/ (2026 index).
Local antiinfectives stay in their organ group (D/G/S); antibiotics means J01.
One primary category is proposed. Uncertainty must not become a forced match.
"""

from dataclasses import dataclass
import re


MEDICINE_TAXONOMY_VERSION = "2026-09-v2"

# Same tuple contract as the other seed trees; deliberately no L3 dosage nodes.
MEDICINES_SUBCATEGORIES = [
    ("Антибиотики", "Antibiotics", "antibiotics", "Антибактериальные препараты системного действия", "Systemic antibacterial medicines", []),
    ("Другие противоинфекционные средства и вакцины", "Other Antiinfectives & Vaccines", "antiinfectives-vaccines", "Противовирусные, противогрибковые, противопаразитарные средства и вакцины", "Other antiinfectives, antiparasitic medicines and vaccines", []),
    ("Обезболивающие и противовоспалительные", "Pain & Inflammation", "painkillers", "Анальгетики и противовоспалительные препараты", "Analgesics and antiinflammatory medicines", []),
    ("Сердечно-сосудистые препараты", "Cardiovascular", "cardio", "Препараты для сердечно-сосудистой системы", "Cardiovascular medicines", []),
    ("Кровь и кроветворение", "Blood & Blood Formation", "blood-hematology", "Препараты крови, кроветворения и инфузионные растворы", "Blood, hematological medicines and infusion solutions", []),
    ("Пищеварение и обмен веществ", "Digestion & Metabolism", "gastro", "Препараты пищеварительного тракта и обмена веществ, кроме диабета", "Alimentary tract and metabolism medicines, excluding diabetes", []),
    ("Гормоны и диабет", "Hormones & Diabetes", "endocrinology-diabetes", "Препараты при диабете и системные гормоны, кроме половых", "Diabetes medicines and systemic hormones excluding sex hormones", []),
    ("Кожа", "Dermatology", "dermatology", "Дерматологические лекарственные препараты", "Dermatological medicines", []),
    ("Дыхательная система и ЛОР", "Respiratory & ENT", "respiratory-ent", "Препараты для дыхательной системы, горла, носа и ушей", "Respiratory, throat, nasal and ear medicines", []),
    ("Аллергия", "Allergy", "allergy", "Системные антигистаминные препараты и аллергены", "Systemic antihistamines and allergens", []),
    ("Нервная система", "Nervous System", "nervous-system", "Препараты нервной системы, кроме анальгетиков", "Nervous system medicines excluding analgesics", []),
    ("Онкология и иммунология", "Oncology & Immunology", "oncology-immunology", "Противоопухолевые и иммуномодулирующие препараты", "Antineoplastic and immunomodulating medicines", []),
    ("Урология и гинекология", "Urology & Gynecology", "urology-gynecology", "Препараты мочеполовой системы и половые гормоны", "Genitourinary medicines and sex hormones", []),
    ("Глаза", "Ophthalmology", "ophthalmology", "Офтальмологические лекарственные препараты", "Ophthalmological medicines", []),
    ("Кости, суставы и мышцы", "Bones, Joints & Muscles", "musculoskeletal", "Препараты опорно-двигательной системы, кроме выделенных средств от боли", "Musculoskeletal medicines excluding the separate pain group", []),
    ("Диагностика и другие препараты", "Diagnostics & Other Medicines", "other-medicines", "Диагностические и прочие препараты группы ATC V, кроме аллергенов", "Diagnostics and other ATC V products excluding allergens", []),
]

MEDICINE_CATEGORY_SLUGS = frozenset(item[2] for item in MEDICINES_SUBCATEGORIES)

# Only obsolete nodes owned by this seed. Never infer retirement from absence.
RETIRED_MEDICINE_CATEGORY_SLUGS = frozenset({
    "heart-cardiovascular", "sleep-stress", "cold-flu", "ent", "orthopedics",
    "pain-tablets", "pain-gels", "pain-patches", "cold-tablets", "cough-syrups",
    "throat-lozenges", "nasal-sprays", "antihistamines", "allergy-nasal",
    "allergy-eye-drops", "omega-3-heart", "coq10-heart", "cholesterol-support",
    "melatonin", "calming-supplements", "magnesium-sleep", "stress-relief",
})

# Recognised second levels, not a claim that every syntactically valid leaf is
# present in the WHO index. Old leaf codes can still identify a broad group.
ATC_SECOND_LEVELS = frozenset("""
    A01 A02 A03 A04 A05 A06 A07 A08 A09 A10 A11 A12 A13 A14 A15 A16
    B01 B02 B03 B05 B06 C01 C02 C03 C04 C05 C07 C08 C09 C10
    D01 D02 D03 D04 D05 D06 D07 D08 D09 D10 D11
    G01 G02 G03 G04 H01 H02 H03 H04 H05 J01 J02 J04 J05 J06 J07
    L01 L02 L03 L04 M01 M02 M03 M04 M05 M09 N01 N02 N03 N04 N05 N06 N07
    P01 P02 P03 R01 R02 R03 R05 R06 R07 S01 S02 S03
    V01 V03 V04 V06 V07 V08 V09 V10 V20
""".split())

# WHO cumulative alterations 2005–2026, checked 2026-09-09. These old codes
# cross our storefront groups (or were deleted), so their old prefix is unsafe.
# Do not silently rewrite ATC or infer the replacement medicine/indication.
# https://atcddd.fhi.no/atc_ddd_alterations__cumulative/atc_alterations/
ATC_REQUIRING_REVIEW = frozenset("""
    A01AD02 A11CC07 A12AA12 B01AC14 B03AB06 B06AA11 C01EB19 C04AX13
    C10AX04 D03AX07 D03AX08 G04BE05 H01CA03 J05AB54 J07BX03 J07BX07
    L01XD02 L01XX09 L04AC06 N01AB03 N02AA09 N03AX12 N03AX16 N07XX09
    R03CA02 R05CB12
""".split())

ATC_CATEGORY_RULES = (
    ("M01A", "painkillers"), ("M01B", "painkillers"),
    ("M02", "painkillers"), ("N02", "painkillers"),
    ("A10", "endocrinology-diabetes"), ("J01", "antibiotics"),
    ("R06", "allergy"), ("V01", "allergy"),
    ("S01", "ophthalmology"), ("S02", "respiratory-ent"),
    ("A", "gastro"), ("B", "blood-hematology"), ("C", "cardio"),
    ("D", "dermatology"), ("G", "urology-gynecology"),
    ("H", "endocrinology-diabetes"), ("J", "antiinfectives-vaccines"),
    ("L", "oncology-immunology"), ("M", "musculoskeletal"),
    ("N", "nervous-system"), ("P", "antiinfectives-vaccines"),
    ("R", "respiratory-ent"), ("V", "other-medicines"),
)


@dataclass(frozen=True)
class MedicineCategoryProposal:
    status: str  # proposed / review / preserve / stub
    category_slug: str | None
    reason: str
    atc_codes: tuple[str, ...] = ()


def _parse_codes(value):
    if not value or not str(value).strip():
        return ()
    codes = tuple(sorted(set(re.split(r"\s*[/,;|+]\s*", str(value).strip().upper()))))
    if any(
        not re.fullmatch(r"[ABCDGHJLMNPRSV]\d{2}(?:[A-Z](?:[A-Z](?:\d{2})?)?)?", code)
        or code[:3] not in ATC_SECOND_LEVELS
        for code in codes
    ):
        return None
    return codes


def _category_for_code(code):
    if code.startswith("S03"):
        return None  # combined eye/ear preparations have no unique primary group
    matches = [(prefix, slug) for prefix, slug in ATC_CATEGORY_RULES if code.startswith(prefix)]
    if not matches:
        return None
    _, chosen = max(matches, key=lambda item: len(item[0]))
    if any(prefix.startswith(code) and slug != chosen for prefix, slug in ATC_CATEGORY_RULES):
        return None  # e.g. M01 includes both the pain and musculoskeletal groups
    return chosen


def propose_medicine_category(
    *, atc_code="", source_atc_code="", barcode="", source_barcode="",
    is_stub=False, current_category_slug="",
):
    """Suggest without ORM, I/O, mutation, name guessing or inherited stub data."""
    if is_stub:
        return MedicineCategoryProposal("stub", None, "incomplete_card")
    if current_category_slug and current_category_slug != "medicines":
        return MedicineCategoryProposal("preserve", current_category_slug, "existing_category")
    if barcode and source_barcode and str(barcode).strip() != str(source_barcode).strip():
        return MedicineCategoryProposal("review", None, "source_barcode_conflict")
    own = _parse_codes(atc_code)
    source = _parse_codes(source_atc_code)
    if own is None or source is None:
        return MedicineCategoryProposal("review", None, "invalid_atc")
    if own and source and own != source:
        return MedicineCategoryProposal("review", None, "source_atc_conflict", own + source)
    codes = own or source
    if not codes:
        return MedicineCategoryProposal("review", None, "missing_atc")
    if ATC_REQUIRING_REVIEW.intersection(codes):
        return MedicineCategoryProposal("review", None, "obsolete_atc_requires_review", codes)
    categories = {_category_for_code(code) for code in codes}
    if None in categories or len(categories) != 1:
        return MedicineCategoryProposal("review", None, "ambiguous_atc", codes)
    return MedicineCategoryProposal("proposed", categories.pop(), "atc_prefix", codes)
