"""Ложные причины модерации лекарств и БАДов: разбор очереди 26.10.2026.

Примеры — логи прода, которые ждали модерации с верными названиями и текстами.
"""

import pytest

from apps.ai.models import AIProcessingLog
from apps.ai.services.medicine_reference import translate_special_notes
from apps.ai.services.semantic_validator import SemanticValidator
from apps.ai.services.supplement_content import unsourced_numbers
from apps.ai.services.supplement_glossary import missing_terms
from apps.catalog.models import Category, MedicineProduct, Product

pytestmark = pytest.mark.django_db


def _category(name, slug, parent=None, en=None):
    # В базе CI разделы «medicines», «supplements», «vitamins» и др. уже созданы миграциями.
    category, _ = Category.objects.update_or_create(slug=slug, defaults={"name": name, "parent": parent})
    if en:
        category.translations.update_or_create(locale="en", defaults={"name": en})
    return category


@pytest.fixture
def catalog():
    medicines = _category("Медицина", "medicines")
    supplements = _category("БАДы", "supplements")
    for name, slug, en in (
        ("Витамины", "vitamins", "Vitamins"),
        ("Минералы", "minerals", "Minerals"),
        ("Кальций", "calcium-q", "Calcium"),
        ("Витамин D", "vitamin-d-q", "Vitamin D"),
        ("Протеин", "protein-q", "Protein"),
    ):
        _category(name, slug, supplements, en)
    electronics = _category("Электроника", "electronics")
    _category("Компактные камеры", "compact-cameras", electronics, "Compact")
    underwear = _category("Бельё", "underwear")
    _category("Термобельё", "uw-thermal-heavy", underwear, "Heavy")
    return {"medicines": medicines, "minerals": Category.objects.get(slug="minerals")}


def _medicine_reasons(category, name, ru, en):
    medicine = MedicineProduct.objects.create(name=name, slug=f"mq-{abs(hash((name, ru)))}", category=category)
    medicine.refresh_from_db()
    return SemanticValidator().validate(
        medicine.base_product, generated_titles={"ru": ru, "en": en}, dynamic_attributes=[]
    ).reasons


def _supplement_reasons(category, name, ru, en):
    product = Product.objects.create(
        name=name, slug=f"sq-{abs(hash(name))}", product_type="supplements", category=category
    )
    log = AIProcessingLog.objects.create(
        product=product,
        processing_type="full",
        input_data={},
        generated_title=ru,
        extracted_attributes={"seo_translations": {"en": {"generated_title": en}}},
    )
    return SemanticValidator().validate_log(log).reasons


@pytest.mark.parametrize(
    "name, ru, en",
    [
        # Слово чужой категории есть в названии источника — латиницей или по-турецки.
        (
            "CALCIUM FOLINATE KOCAK 100 MG/10 ML IV/IM ENJEKTABL COZELTI ICEREN FLAKON",
            "CALCIUM FOLINATE KOCAK 100 мг/10 мл, раствор для инъекций, флакон",
            "CALCIUM FOLINATE KOCAK 100 mg/10 ml, solution for injection, vial",
        ),
        (
            "BALANCE %1,5 GLIKOZ 1,25 MMOL / 1 KALSIYUM 2000 ML BIOFIN TORBA",
            "BALANCE 1,5% глюкоза 1,25 ммоль/л кальций 2000 мл, мешок",
            "BALANCE 1.5% glucose 1.25 mmol/L calcium 2000 ml bag",
        ),
        (
            "MARCAINE SPINAL HEAVY %0,5 ENJEKSIYONLUK COZELTI",
            "MARCAINE SPINAL HEAVY (бупивакаин) 0,5%, раствор для инъекций",
            "MARCAINE SPINAL HEAVY (bupivacaine) 0.5%, solution for injection",
        ),
        (
            "NUTRISON PROTEIN PLUS 500 ML",
            "NUTRISON PROTEIN PLUS, 500 мл",
            "NUTRISON PROTEIN PLUS, 500 ml",
        ),
        # «10% 100 мг» — русская запись процента, «фактор VIII» — римское число, «1 ADET» — одна туба.
        (
            "RHEUMON %10 100 MG 50 ML SPREY",
            "RHEUMON (этофенамат) 10% 100 мг, спрей, 50 мл",
            "RHEUMON (etofenamate) 10% 100 mg, spray, 50 ml",
        ),
        (
            "FAKTOR VIII 8Y 500 IU IV INFUZYON ICIN LIYOFILIZE TOZ ICEREN 1 FLAKON",
            "FAKTOR VIII 8Y (фактор свёртывания крови VIII) 500 МЕ, лиофилизат для приготовления раствора для инфузий",
            "FAKTOR VIII 8Y (coagulation factor VIII) 500 IU, powder for solution for infusion",
        ),
        (
            "JETEX %5 1 ADET 5 G TUP",
            "JETEX 5% крем 5 г",
            "JETEX 5% cream 5 g",
        ),
    ],
)
def test_medicine_titles_from_the_queue_pass(catalog, name, ru, en):
    assert _medicine_reasons(catalog["medicines"], name, ru, en) == []


def test_medicine_title_still_catches_invented_kind_and_turkish_flavour(catalog):
    # Вещество не из источника — конфликт, как раньше (EISEFERON в test_semantic_validator).
    assert "title_category_mismatch" in _medicine_reasons(
        catalog["medicines"],
        "EISEFERON 40 MG/5 ML ORAL COZELTI 10 KASIK",
        "EISEFERON кальций 40 мг/5 мл, раствор для приёма внутрь",
        "EISEFERON calcium 40 mg/5 ml, oral solution",
    )
    # Вкус лечебного питания — перевести, а бренд без него не теряется.
    name = "FORTINI COMPACT MULTI FIBRE CILEK AROMALI 125 ML"
    assert "title_untranslated" in _medicine_reasons(
        catalog["medicines"], name, "FORTINI COMPACT MULTI FIBRE CILEK AROMALI, 125 мл",
        "FORTINI COMPACT MULTI FIBRE CILEK AROMALI, 125 ml",
    )
    assert _medicine_reasons(
        catalog["medicines"], name, "FORTINI COMPACT MULTI FIBRE со вкусом клубники, 125 мл",
        "FORTINI COMPACT MULTI FIBRE Strawberry Flavour, 125 ml",
    ) == []
    # Турецкая запись «%2,5» по-прежнему ловится.
    assert "title_untranslated" in _medicine_reasons(
        catalog["medicines"], "ARTROCOL %2,5 JEL (45 G)", "ARTROCOL %2,5 гель 45 г", "ARTROCOL 2.5% gel 45 g"
    )


def test_supplement_sibling_subcategory_and_short_brand_are_not_problems(catalog):
    assert _supplement_reasons(
        catalog["minerals"],
        "KALSI-D KALSIYUM VE VITAMIN D ICEREN TAKVIYE EDICI GIDA 30 saşe",
        "KALSI-D Кальций и витамин D, 30 саше",
        "KALSI-D Calcium and Vitamin D, 30 sachets",
    ) == []
    assert _supplement_reasons(
        catalog["minerals"],
        "HP BIOTIN SURUP 1250 mcg/5 ml 150 ml şişe",
        "HP Биотин 1250 мкг/5 мл, сироп, 150 мл",
        "HP Biotin 1250 mcg/5 ml, Syrup, 150 ml",
    ) == []


def test_supplement_glossary_accepts_usual_translations():
    assert missing_terms("ZADE VITAL KETEN TOHUMU YAGI", "Масло семян льна", "Flaxseed Oil") == []
    assert missing_terms("FLAVOXAN IZOFLAVON KETEN TOHUMU YAGI", "Изофлавоны и льняное масло", "Isoflavones and Flaxseed Oil") == []
    assert missing_terms("COOLPAST MEYAN KOKU", "Пастилки с корнем солодки", "Lozenges with Licorice Root") == []
    assert missing_terms("SENDHE PROPOLISLI PASTIL", "Пастилки с прополисом", "Propolis Lozenges") == []
    # «SAKIZ KABAGI», «BAL KABAGI» — кабачок и тыква, а не мастика и мёд.
    assert missing_terms("FORPROST SAKIZ KABAGI", "Экстракт мастикового дерева", "Mastic Gum") == ["sakiz kabagi"]
    assert missing_terms("SILVERSHELL BAL KABAGI", "Экстракт тыквы", "Pumpkin Extract") == []


def test_substance_designations_are_not_unsourced_numbers():
    source = "OTABIOTIN BIOTIN ICEREN TAKVIYE EDICI GIDA 60 tablet"
    text = "OTABIOTIN — пищевая добавка с биотином, 60 таблеток. Биотин — водорастворимый витамин группы B (витамин B7)."
    assert unsourced_numbers(text, source) == []
    assert unsourced_numbers("Коэнзим Q10 и омега-3, 500 мг.", "EASYFISHOIL Q 30 tablet") == ["500"]


def test_special_notes_badges_are_translated_by_code():
    assert translate_special_notes("Ek izlemeye tabi ilaç! Alternatif Geri Ödeme Kapsamındadır.") == (
        "Препарат подлежит дополнительному мониторингу. Входит в альтернативную схему возмещения SGK.",
        "This medicine is subject to additional monitoring. Covered by the SGK alternative reimbursement scheme.",
    )
    assert translate_special_notes(
        "Hastanelerce Temini Zorunlu Kemoterapi İlacı Tedavi sırasında ve tedaviden sonraki en az 1 hafta boyunca emzirilmemelidir."
    )[0] == (
        "Химиотерапевтический препарат, поставляется только через больницы. "
        "Не кормить грудью во время лечения и не менее 1 недели после него."
    )
    assert translate_special_notes("Uygulamadan sonra 24 saat süreyle emzirilmemelidir.")[1] == (
        "Do not breastfeed for 24 hours after administration."
    )
    # Незнакомая фраза — перевод остаётся модели.
    assert translate_special_notes("Tedavi sırasında ve sonrasında en az altı ay emzirmemelidir.") is None


@pytest.mark.parametrize(
    "source, brand, product, expected_brand, expected_ru",
    [
        ("HIPP 2 ORGANIK DEVAM SUTU 300 g toz", "HIPP", "Органическая последующая молочная смесь", "HIPP 2",
         "Органическая последующая молочная смесь"),
        ("BEBIVITA DEVAM SUTU 3 500 gr toz", "BEBIVITA", "Последующая молочная смесь", "BEBIVITA 3",
         "Последующая молочная смесь"),
        ("PROMEGA KAPSUL 1000 mg 30 kapsül", "PROMEGA", "пищевая добавка", "PROMEGA", "пищевая добавка 1000 мг"),
        # Ничего не потеряно — без изменений; возраст «1 YASINDAN» — не ступень.
        ("SIMILAC 3 DEVAM SUTU 1 YASINDAN ITIBAREN 360 g toz", "SIMILAC 3", "Последующая молочная смесь с 1 года",
         "SIMILAC 3", "Последующая молочная смесь с 1 года"),
    ],
)
def test_supplement_title_keeps_formula_stage_and_dose(source, brand, product, expected_brand, expected_ru):
    from apps.ai.services.supplement_content import _restore_lost_numbers, is_baby_food, parse_pack

    pack = parse_pack(source)
    title_brand, text = _restore_lost_numbers(brand, {"ru": product, "en": "x"}, pack, source, is_baby_food(source))
    assert (title_brand, text["ru"]) == (expected_brand, expected_ru)


def test_million_units_are_kept_in_medicine_title(catalog):
    """Пилот 27.10.2026: «ROVAMYCINE 3 MIU» модель записала как «3 МЕ» — ошибка в миллион раз."""
    from apps.ai.services.medicine_title import build_medicine_title

    name = "ROVAMYCINE 3 MIU 10 FILM KAPLI TABLET"
    title = build_medicine_title(name)
    assert title["ru"].startswith("ROVAMYCINE 3 млн МЕ, таблетки, покрытые плёночной оболочкой")
    assert title["en"].startswith("ROVAMYCINE 3 MIU")
    assert "title_identity_lost" in _medicine_reasons(
        catalog["medicines"], name, "ROVAMYCINE 3 МЕ, таблетки, покрытые плёночной оболочкой, 10 шт.",
        "ROVAMYCINE 3 IU, film-coated tablets, 10 pcs",
    )
    assert _medicine_reasons(catalog["medicines"], name, title["ru"], title["en"]) == []


def test_medicine_ru_title_units_and_brand_after_digits(catalog):
    from apps.ai.services.medicine_title import ru_title_units

    assert ru_title_units("CLUSTOID 10000 TU/ML суспензия для инъекций") == "CLUSTOID 10000 ТЕ/мл суспензия для инъекций"
    assert ru_title_units("SPRAMAX 1.5 MIU таблетки") == "SPRAMAX 1.5 млн МЕ таблетки"
    # Часть бренда после цифры — не брак; латинская единица и английская форма — брак.
    assert _medicine_reasons(
        catalog["medicines"], "MILUPA UCD 2 PRIMA (500 G)", "MILUPA UCD 2 PRIMA, 500 г", "MILUPA UCD 2 PRIMA, 500 g"
    ) == []
    assert "title_untranslated" in _medicine_reasons(
        catalog["medicines"], "CLUSTOID 10000 TU/ML ENJEKSIYONLUK SUSPANSIYON (BETULA)",
        "CLUSTOID 10000 TU/мл, суспензия для инъекций (Betula)", "CLUSTOID 10000 TU/ml suspension for injection (Betula)",
    )
    assert "title_untranslated" in _medicine_reasons(
        catalog["medicines"], "MELPHALAN 50 MG 1 INJECTION", "MELPHALAN 50 мг 1 INJECTION", "MELPHALAN 50 mg 1 injection"
    )


def test_supplement_thousands_with_space_match_source():
    from apps.ai.services.supplement_content import title_problems

    assert title_problems("OSENDE Коллаген 10 000 Плюс, жидкость, 30 туб по 40 мл",
                          "OSENDE COLLAGEN 10.000 PLUS TAKVIYE EDICI GIDA 30x40 ml tüp") == []
    assert title_problems("NAME 30 капсул", "NAME 500 mg 30 kapsül") == ["supplement_title_number_lost"]
