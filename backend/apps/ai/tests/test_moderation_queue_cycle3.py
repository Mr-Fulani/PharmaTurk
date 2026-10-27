"""Очередь модерации лекарств и БАДов, круг 3 (27.10.2026): ложные причины на примерах прода.

Перевод абзацев модели был верным, но отклонялся сверкой чисел из-за опечаток распознанного
PDF в турецком исходнике; бренд шаблона названия включал слова описания и вкус; фасовка БАДа
из двух частей не разбиралась.
"""

import pytest

from apps.ai.models import AIProcessingLog
from apps.ai.services.medicine_fact_check import doses_match, strip_proper_name_lines
from apps.ai.services.medicine_memory import paragraph_problems, section_paragraph_problems
from apps.ai.services.medicine_paragraph_check import _frequency, item_problems
from apps.ai.services.medicine_title import build_medicine_title
from apps.ai.services.semantic_validator import (
    _alias_in_source,
    _medicine_identity_lost,
    _medicine_ru_title_untranslated,
)
from apps.ai.services.supplement_content import (
    _brand,
    _restore_lost_numbers,
    is_baby_food,
    parse_pack,
    title_problems,
    unsourced_numbers,
)
from apps.ai.services.supplement_glossary import missing_terms


@pytest.mark.parametrize(
    "source, ru, en",
    [
        # «частота» — не «часто».
        ("Seyrek (görülme sıklığı <1/1.000)", "Редкие (частота <1/1000)", "Rare (frequency <1/1,000)"),
        ("Çok seyrek (görülme sıklığı:<1/10.000)", "Очень редко (частота <1/10 000)", "Very rare (frequency <1/10,000)"),
        # «Yaygın (sistemik)» — «системный», а не частота.
        (
            "Yaygın (sistemik) etkili kortikosteroid uygulaması gerektiren durumlarda kas içine,",
            "В случаях, требующих применения кортикостероидов с системным (общим) действием, внутримышечно,",
            "In cases requiring the use of corticosteroids with systemic (general) effect, intramuscularly,",
        ),
        # Время «8.00'de», «0400'den».
        (
            "Doktorunuz size günlük dozu tek seferde almanızı ya da gün aşırı sabah saat 8.00'de almanızı söyleyebilir.",
            "Ваш врач может сказать вам принимать суточную дозу однократно или через день в 8:00 утра.",
            "Your doctor may tell you to take the daily dose all at once or every other day at 8:00 a.m.",
        ),
        (
            "Yatmadan önce {BRAND} almayı unutursanız, unutulan dozu ancak en geç sabaha karşı 0400'den önce alabilirsiniz.",
            "Если вы забыли принять {BRAND} перед сном, пропущенную дозу можно принять только до 04:00 утра.",
            "If you forget to take {BRAND} before bedtime, you may take the missed dose only before 4:00 a.m.",
        ),
        # Опечатки распознанного PDF: «0.,4 ml», «10. 000», «200 Lig», «390 C», «1 buçuk», «%l».
        (
            "{BRAND}, 0.,4 ml de 40 mg enoksaparin sodyum içerir.",
            "{BRAND} содержит 40 мг эноксапарина натрия в 0,4 мл.",
            "{BRAND} contains 40 mg enoxaparin sodium in 0.4 ml.",
        ),
        (
            "Çok seyrek: 10. 000 hastanın birinden az görülebilir.",
            "Очень редко: может наблюдаться менее чем у 1 из 10 000 пациентов.",
            "Very rare: may occur in less than 1 in 10,000 patients.",
        ),
        (
            "Her flakonda etkin madde olarak 200 Lig deksmedetomidin içerir.",
            "Каждый флакон содержит 200 мкг дексмедетомидина в качестве действующего вещества.",
            "Each vial contains 200 mcg dexmedetomidine as the active substance.",
        ),
        (
            "Eğer 48 saatten uzun süren grip benzeri şikâyetlerin eşlik ettiği 390 C üzeri ateşiniz olursa doktorunuzu bilgilendiriniz.",
            "Если у вас температура выше 39 °C с симптомами гриппа более 48 часов, сообщите врачу.",
            "If you have a fever above 39 °C with flu-like complaints lasting longer than 48 hours, inform your doctor.",
        ),
        (
            "Genel doz 5 spreydir. Gerekirse her 1 buçuk-3 saatte bir tekrarlanır.",
            "Обычная доза — 5 распылений. При необходимости повторять каждые 1,5–3 часа.",
            "The usual dose is 5 sprays. If necessary, repeat every 1.5–3 hours.",
        ),
        ("Yaygın yan etkiler (%l'den fazla)", "Частые побочные реакции (более 1%)", "Common side effects (more than 1%)"),
        # «%0,3 mg/ml» — знак процента или единица, «1000 U./gün» — МЕ.
        (
            "Bimatoprost 0,1 mg/ml ile görülen yan etkilere ilave olarak %0,3 mg/ml bimatoprost içeren göz damlası ile görülenler.",
            "Помимо реакций при биматопросте 0,1 мг/мл, реакции при глазных каплях с биматопростом 0,3 мг/мл.",
            "In addition to reactions with bimatoprost 0.1 mg/ml, reactions with eye drops containing bimatoprost 0.3 mg/ml.",
        ),
        (
            "D vitamini içeren ilaçların gebelikte kullanımında maksimum doz 1000 U./gün'ü geçmemelidir.",
            "При применении препаратов витамина D во время беременности максимальная доза не должна превышать 1000 МЕ/сутки.",
            "When vitamin D preparations are used during pregnancy, the maximum dose must not exceed 1000 IU/day.",
        ),
        # Строка частоты: «en az» — определение частоты, а не граница; ссылка на раздел — не заголовок.
        (
            "Yaygın (En az 10 kişide birinden fazla, fakat 100 kişide birden az kişiyi etkiler)",
            "Распространенные (влияет на менее чем 1 из 10 человек, но более чем на 1 из 100 человек)",
            "Common (affects less than 1 in 10 people but more than 1 in 100 people)",
        ),
        (
            "4. bölümde listelenen belirtilere ek olarak çok fazla tablet alırsanız doktorunuza başvurunuz.",
            "Помимо симптомов, перечисленных в разделе 4, если вы примете слишком много таблеток, обратитесь к врачу.",
            "In addition to the symptoms listed in section 4, if you take too many tablets, contact your doctor.",
        ),
    ],
)
def test_correct_paragraph_translations_pass(source, ru, en):
    assert paragraph_problems(source, ru, en) == []


def test_wrong_paragraph_translations_still_rejected():
    # «Çok seyrek: 000 hastanın…» — очень редко = 1 из 10 000, а модель написала «1 из 1000».
    assert paragraph_problems(
        "Çok seyrek:000 hastanın birinden az görülebilir.",
        "Очень редко: может наблюдаться менее чем у 1 из 1000 пациентов.",
        "Very rare: may occur in less than 1 in 1,000 patients.",
    )
    # Пропущено время и единица — по-прежнему расхождение.
    assert item_problems("Sabah 8.00'de alınız.", "Принимайте утром в 9:00.", "Take at 9:00 in the morning.")
    assert not doses_match("0,6 ml de 60 mg içerir", "0,6 мл содержит 6 мг")
    assert not doses_match("200 Lig deksmedetomidin", "200 мг дексмедетомидина")


def test_frequency_is_the_first_label_in_the_line():
    assert _frequency("Редко: некроз (локальный, в редких случаях распространяющийся на ткани)", "ru") == "rare"
    assert _frequency("Нечасто: головная боль", "ru") == "uncommon"
    assert _frequency("Частота неизвестна: сыпь", "ru") == "unknown"
    assert _frequency("Очень часто: тошнота", "ru") == "very_common"


def test_table_cells_are_not_glued_doses():
    """PEDIASURE: «Vitamin B6\\nmg\\n0.10» — ячейки таблицы, а не «6 mg»."""
    source = "Vitamin B6\nmg\n0.10\n0.22\nVitamin B12\nmcg\n0.20\n0.44"
    assert doses_match(source, "Витамин B6\nмг\n0.10\n0.22\nВитамин B12\nмкг\n0.20\n0.44")
    assert not doses_match("VORELBAN15mg'dır", "VORELBAN 1,5 мг")


def test_section_fact_check_ignores_numbers_of_the_brand():
    from apps.ai.services.content_generator import ContentGenerator

    content = {
        "ru": {"side_effects": "Как и все лекарства, GLUKOFEN RET.850 MG может вызывать побочные эффекты."},
        "en": {"side_effects": "Like all medicines, GLUKOFEN RET.850 MG can cause side effects."},
        "attributes": {"medicine_translation_quality": {"side_effects": {"complete": True}}},
    }
    ContentGenerator._apply_medicine_fact_checks(
        content,
        {"name": "GLUKOFEN RET.850 MG 100 TABLET", "active_ingredient": "metformin"},
        {"side_effects": "Tüm ilaçlar gibi, GLUKOFEN'in içeriğinde bulunan maddelere duyarlı kişilerde yan etkiler olabilir."},
    )
    assert content["attributes"]["medicine_translation_quality"]["side_effects"]["complete"] is True


def test_cyrillic_brand_counts_as_the_brand_label():
    problems = section_paragraph_problems(
        "MİCLAST tırnak cilasının, 1 gramında 80 mg siklopiroks etkin maddesi bulunur.",
        "МИКЛАСТ содержит 80 мг активного вещества циклопирокса в 1 грамме лака для ногтей.",
        "MICLAST contains 80 mg of the active substance ciclopirox in 1 gram of nail polish.",
        brand="MİCLAST",
    )
    assert problems == []


def test_requisites_and_list_markers_are_not_untranslated_text():
    text = (
        "5. ХРАНЕНИЕ REGINON\nХраните при температуре ниже 25°C.\nВладелец регистрационного удостоверения:\n"
        "Bağcılar\nМесто производства:\nDilovası/Kocaeli\nğ\nç) Пемфигус вулгарис\nв блистерах Alü/Alü"
    )
    cleaned = strip_proper_name_lines(text)
    assert "Bağcılar" not in cleaned and "Dilovası" not in cleaned and "ğ" not in cleaned and "Alü" not in cleaned
    assert "Пемфигус" in cleaned
    # Непереведённый пункт списка — не топоним.
    assert "Bulantı" in strip_proper_name_lines("Побочные эффекты:\n- тошнота\nBulantı")


@pytest.mark.parametrize(
    "source, title",
    [
        ("DIPROMED ENJ. ICIN SUS. ICEREN AMPUL", "DIPROMED 5 мг + 2 мг/мл, суспензия для инъекций, ампулы"),
        ("OPILOX TIRNAK CILASI SETI", "OPILOX набор лака для ногтей"),
        ("XAVRON SOLUTION FOR INJECTION 1,5 MG/ML 20 ML 10 VIALS", "XAVRON раствор для инъекций 1,5 мг/мл, 20 мл, 10 флаконов"),
        ("TURKTIPSAN NORADRENALIN 4 MG/4 ML IV INFUZYON ICIN ENJEKSIYONLUK COZELTI", "TURKTIPSAN Норадреналин 4 мг/4 мл раствор для инфузий"),
        ("MAGNEZYUM SULFAT 1500 MG /10 ML ENJEKSIYONLUK COZELTI (10 AMP)", "Магния сульфат 1500 мг/10 мл раствор для инъекций, 10 ампул"),
        ("PROFENID %2,5 MG 60 GR JEL", "PROFENID 2,5 мг гель 60 г"),
        ("ALCAINE %0,5 MG GOZ DAMLASI, COZELTI (15 ML)", "ALCAINE 0,5% глазные капли, раствор (15 мл)"),
        ("COMETRIQ 4 ADET 140 MG (7X80 MG CAPSULES ve 21X20 MG CAPSULES )", "COMETRIQ 140 мг, 4 упаковки (7×80 мг капсулы и 21×20 мг капсулы)"),
        ("SEVOFLURANE- BAXTER %100 INHALASYON BUHARI SIVISI", "SEVOFLURANE-BAXTER 100% жидкость для ингаляций"),
        ("TRIKAFTA (ELEXACAFTOR, TEZACAFTOR, IVACAFTOR) ORAL GRANULES 80 MG/40 MG/60 MG",
         "TRIKAFTA (элексакафтор, тезакафтор, ивакафтор) гранулы для приёма внутрь 80 мг/40 мг/60 мг"),
        ("MOVICOL JUNIOR PWDR FOR ORAL SOL 6,9GX30 SACHT", "MOVICOL JUNIOR порошок для приготовления раствора 6,9 г, 30 саше"),
    ],
)
def test_medicine_title_identity_false_losses(source, title):
    assert _medicine_identity_lost(source, title) == set()


def test_medicine_title_identity_real_losses():
    assert _medicine_identity_lost("MOUNJARO 7,5 MG/0,6 ML ENJEKTOR", "Тирзепатид 7,5 мг/0,6 мл") == {"BRAND:MOUNJARO"}
    assert "DOSE:2:%" in _medicine_identity_lost(
        "DORMOFOL %2 1000 MG/50 ML IV INFUZYONLUK EMULSIYON", "DORMOFOL 1000 мг/50 мл эмульсия"
    )
    assert "DOSE:1.5:MG" in _medicine_identity_lost("OCTOSTIM 1,5 MG/ML 2,5 NASAL SPRAY", "OCTOSTIM 1,5 мкг/мл, спрей")


def test_flavour_is_translated_by_the_title_template():
    assert build_medicine_title("PEDIASURE CILEK AROMALI 220 ML")["ru"] == "PEDIASURE, со вкусом клубники, 220 мл"
    assert build_medicine_title("RESOURCE ENERGY MUZ 200 ML")["en"] == "RESOURCE ENERGY, banana flavour, 200 ml"


def test_russian_percent_with_space_is_not_turkish():
    source = "READI-CAT 2 BARIUM 2,1 % 1X(24X450 ML)"
    assert not _medicine_ru_title_untranslated("READI-CAT 2 Barium 2,1 % 1x(24x450 мл)", source)
    assert _medicine_ru_title_untranslated("%8 АМИНОКИСЛОТ раствор, 500 мл", "%8 AMINOPLASMAL 500 ML")
    assert not _medicine_ru_title_untranslated(
        "ROXSIT 1000 TSU/мл суспензия для инъекций (Phleum)", "ROXSIT 1000 TSU/ML ENJEKSIYONLUK SUSPANSIYON (PHLEUM)"
    )


@pytest.mark.django_db
def test_medicine_description_checks():
    from apps.ai.services.quality_checker import get_moderation_reasons
    from apps.catalog.models import Product

    product = Product.objects.create(name="CABOZANIX 20 KAPSUL", slug="mq3-cabozanix", product_type="medicines")

    def reasons(description):
        log = AIProcessingLog.objects.create(
            product=product, processing_type="full", generated_title="CABOZANIX, капсулы, 20 шт.",
            generated_description=description,
            input_data={"attributes": {"source_tabs": {"equivalents": "X 20 KAPSUL", "ilac_bilgileri": "Reçete: Kırmızı"}}},
        )
        return get_moderation_reasons(log)

    # Только вкладки аналогов — инструкции нет, описание из фактов короткое.
    assert "short_description" not in reasons("CABOZANIX — капсулы, 20 шт. Действующее вещество: кабозантиниб.")
    assert "description_meta_text" in reasons("Лекарственная форма и дозировка в исходных данных не указаны.")
    assert "garbled_text" in reasons("Рufинамид, таблетки 400 мг для приёма внутрь. Рецептурный препарат.")


@pytest.mark.parametrize(
    "source, ru",
    [
        ("ORBIVITA PLUS KOENZIM Q-10 TABLET 42 g 60 tablet", "60 таблеток, 42 г"),
        ("COSVIA COLLAGEN AHUDUDU AROMALI TAKVIYE EDICI GIDA 10 g 14 saşe", "14 саше по 10 г"),
        ("MARNYS COLLAGEN BEAUTY IN&OUT FLAKON 25 ml x 14 flakon", "14 флаконов по 25 мл"),
        ("VENATURA METILKOBALAMIN SPREY TAKVIYE EDICI GIDA 255 puf 20 ml şişe", "20 мл, 255 доз"),
        ("DR HENRI PHYTOPHARMA OPTIFERT TAKVIYE EDICI GIDA 60 kapsül + 30 saşe", "60 капсул + 30 саше"),
        ("PHYTO DUO PHYTOPHANERE KAPSUL 2x120 kapsül", "2 уп. по 120 капсул"),
        # Доза на штуку — не фасовка: её добавляет _restore_lost_numbers в «что это».
        ("PROMEGA KAPSUL 1000 mg 30 kapsül", "30 капсул"),
    ],
)
def test_supplement_two_part_packs(source, ru):
    assert parse_pack(source).ru == ru


def test_supplement_number_designations():
    assert title_problems(
        "MAGNIMORE ALL DAY Магний и витамин B6, 60 таблеток",
        "MAGNIMORE ALL DAY MAGNEZYUM VE P5P (VITAMIN B6) ICEREN TAKVIYE EDICI GIDA TABLET 60 tablet",
    ) == []
    assert title_problems("FEIRON Железо и витамин C, капли, 20 мл", "FEIRON +2 DEMIR VE VITAMIN C ICEREN DAMLA 20 ml şişe") == []
    assert title_problems("MINOX Биотин, 5000 мкг, 90 таблеток", "MINOX BIOTIN TAKVIYE EDICI GI9DA 5000 mcg 90 tablet") == []
    assert title_problems("X Омега-3, 90 капсул", "X OMEGA 3 1000 KAPSUL 90 kapsül") == ["supplement_title_number_lost"]
    assert unsourced_numbers("Витамин D 62 500 МЕ в 20 мл.", "VITARIO VITAMIN D 62.500 IU/20 ml 20 ml şişe") == []


@pytest.mark.parametrize(
    "source, brand, product, expected_brand, expected_ru",
    [
        ("ELENATAL 2 KAPSUL MULTIVITAMIN ICEREN TAKVIYE EDICI GIDA 30 kapsül", "ELENATAL", "Мультивитамины",
         "ELENATAL 2", "Мультивитамины"),
        ("APTAMIL PRONUTRA 3 9-12 AY DEVAM SUTU 350 g toz", "APTAMIL PRONUTRA 3", "Последующая молочная смесь",
         "APTAMIL PRONUTRA 3", "Последующая молочная смесь для детей 9–12 месяцев"),
        ("EVOLVIA NUTRIPRO 3 800 g toz", "EVOLVIA NUTRIPRO", "Молочная смесь", "EVOLVIA NUTRIPRO 3", "Молочная смесь"),
    ],
)
def test_supplement_line_number_and_age(source, brand, product, expected_brand, expected_ru):
    pack = parse_pack(source)
    title_brand, text = _restore_lost_numbers(brand, {"ru": product, "en": "x"}, pack, source, is_baby_food(source))
    assert (title_brand, text["ru"]) == (expected_brand, expected_ru)


def test_supplement_brand_without_form_word():
    assert _brand("PROMENK SASE", "PROMENK SASE 30 saşe") == ("PROMENK", True)
    assert _brand("GYNOLAC CIGNEME", "GYNOLAC CIGNEME TABLET 15 tablet") == ("GYNOLAC", True)


def test_supplement_category_words_from_source():
    assert _alias_in_source("эвкалиптовое", "STONCARE MENENGIC YAGI, ZENCEFIL YAGI VE OKALIPTUS YAGI ICEREN", "ru")
    assert _alias_in_source("tea tree oil", "PHYTOIL TEA TREE 10 ML", "en")
    assert _alias_in_source("rose oil", "PHYTOIL ROSA DAMASCENA 5 ML", "en")
    assert _alias_in_source("для энергии", "ENERGIZER ENERJI VE PERFORMANS TAKVIYE EDICI GIDA KAPSUL", "ru")
    assert _alias_in_source("peppermint", "GOODDAY DISPEPTA TIBBI NANE VE FRENK KIMYONU ICEREN", "en")
    # Вещество не из источника — по-прежнему конфликт.
    assert not _alias_in_source("железо", "EISEFERON 30 KAPSUL", "ru")


def test_supplement_glossary_variants():
    assert missing_terms("AHCC SHIITAKE MANTARI ICEREN", "Экстракт шиитаке", "Shiitake Extract") == []
    assert missing_terms("ALINOX DEMIR SULFAT", "Сульфат железа", "Ferrous Sulfate") == []


def test_cocoa_flavour_and_millicurie():
    """Пилот круга 3: «PEDIASURE KAKAOLU, 220 мл» применилось с турецким словом, «50 mCi» латиницей."""
    from apps.ai.services.medicine_title import ru_title_units
    from apps.ai.services.semantic_validator import _medicine_flavour_lost, _title_has_turkish_words

    assert build_medicine_title("PEDIASURE KAKAOLU 220 ML")["ru"] == "PEDIASURE, со вкусом какао, 220 мл"
    assert _title_has_turkish_words("PEDIASURE KAKAOLU, 220 мл")
    assert _medicine_flavour_lost("ENSURE PLUS FIBER, со вкусом ванили, 200 мл", "ENSURE PLUS FIBER KAKAOLU 200 ML")
    assert ru_title_units("Y-90 CITRATE THERAPEUTIC 50 mCi") == "Y-90 CITRATE THERAPEUTIC 50 мКи"


@pytest.mark.django_db
def test_medicine_description_with_foreign_flavour_or_cut_off_is_blocked():
    """Пилот круга 3: у ENSURE COMPACT «MUZ» описание «…с ванильным и банановым вкусом...» применилось."""
    from apps.ai.services.quality_checker import get_moderation_reasons
    from apps.catalog.models import Product

    product = Product.objects.create(name="ENSURE COMPACT MUZ AROMALI 4x125 ML", slug="mq3-ensure", product_type="medicines")

    def reasons(description):
        log = AIProcessingLog.objects.create(
            product=product, processing_type="full", generated_title="ENSURE COMPACT, со вкусом банана, 4 шт. по 125 мл",
            generated_description=description, input_data={"name": "ENSURE COMPACT MUZ AROMALI 4x125 ML"},
        )
        return get_moderation_reasons(log)

    assert "garbled_text" in reasons("ENSURE COMPACT — оральный питательный раствор с ванильным и банановым вкусом...")
    assert "garbled_text" in reasons("ENSURE COMPACT — питательный раствор с ванильным вкусом, 4 шт. по 125 мл.")
    assert "garbled_text" not in reasons("ENSURE COMPACT — питательный раствор со вкусом банана, 4 шт. по 125 мл.")
