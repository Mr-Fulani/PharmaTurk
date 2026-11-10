"""БАДы: состав, способ применения, предупреждения и хранение — из памяти переводов."""

import json
from types import SimpleNamespace
from unittest import mock
from unittest.mock import Mock

import pytest

from apps.ai.models import AIProcessingLog, AIProcessingStatus, AITranslationMemory
from apps.ai.services import supplement_content as sc
from apps.ai.services import supplement_glossary
from apps.ai.services import supplement_memory as sm
from apps.ai.services.translation_memory import remember
from apps.catalog.models import Product

# Фрагмент «Ürün Bilgisi» настоящей карточки (HERBALAND SAMBUZINC, ilacfiyati 05.11.2026), сокращён.
PRODUCT_INFO = """Herbaland SambuZinC Gummies 60 Tablet
Ürün Adı:
Herbaland Gummies SambuZinC 60 Tablet
Özet Bilgi:
Kara Mürver, Çinko, C Vitamini İçeren Takviye Edici Gıda
Uyarılar:
Tavsiye edilen günlük porsiyonu aşmayın.
Takviye edici gıdalar normal beslenmenin yerine geçmez.
İlaç Değildir: Hastalıkların önlenmesi veya tedavi edilmesi amacıyla kullanılmaz.
Muhafaza Koşulları:
Direkt güneş ışığından uzak, serin ve kuru yerde muhafaza ediniz.
Kullanım Şekli:
Günde 1 tane çiğneyerek tüketilebilir.
Form
Tablet
Menşe Ülke:
Kanada"""
INGREDIENTS = """Ürün Bileşimi:
Su, Tatlandırıcı (Eritrol, Ksilitol), L-Askorbik asit (C Vitamini), Doğal Ahududu (%0,91) Aroma Vericisi, 270 mg"""

TRANSLATIONS = {
    "Su": ("вода", "water"),
    "Tatlandırıcı (Eritrol, Ksilitol)": ("подсластитель (эритрит, ксилит)", "sweetener (erythritol, xylitol)"),
    "L-Askorbik asit (C Vitamini)": ("L-аскорбиновая кислота (витамин C)", "L-ascorbic acid (vitamin C)"),
    "Doğal Ahududu (%0,91) Aroma Vericisi": ("натуральный малиновый ароматизатор (0,91 %)", "natural raspberry flavouring (0.91%)"),
    "Günde 1 tane çiğneyerek tüketilebilir.": ("По 1 штуке в день, разжёвывая.", "1 piece a day, chewed."),
    "Tavsiye edilen günlük porsiyonu aşmayın.": (
        "Не превышайте рекомендуемую суточную порцию.", "Do not exceed the recommended daily portion."
    ),
    "Takviye edici gıdalar normal beslenmenin yerine geçmez.": (
        "БАД не заменяет полноценное питание.", "Food supplements are not a substitute for a normal diet."
    ),
    "Direkt güneş ışığından uzak, serin ve kuru yerde muhafaza ediniz.": (
        "Хранить в прохладном сухом месте, защищённом от прямых солнечных лучей.",
        "Store in a cool, dry place away from direct sunlight.",
    ),
}


def _answer_for(user_prompt):
    """Ответ «модели» на нумерованный запрос: переводы из TRANSLATIONS по номерам."""
    items = json.loads(user_prompt.split("\n\n", 1)[1])
    return {key: {"ru": TRANSLATIONS[text][0], "en": TRANSLATIONS[text][1]} for key, text in items.items()}


def _translator_llm(answer=_answer_for):
    def generate_content(**kwargs):
        assert kwargs["system_prompt"].startswith(sm.LINE_SYSTEM_PROMPT)
        return {"content": answer(kwargs["user_prompt"]), "tokens": {"prompt": 100, "completion": 80}, "cost_usd": 0.0002}

    return SimpleNamespace(generate_content=Mock(side_effect=generate_content))


def test_blocks_are_found_by_labels_and_standard_phrases():
    parts = sm.section_parts({"product_info": PRODUCT_INFO, "ingredients": INGREDIENTS})

    assert parts["composition"] == [
        "Su",
        "Tatlandırıcı (Eritrol, Ksilitol)",
        "L-Askorbik asit (C Vitamini)",
        "Doğal Ahududu (%0,91) Aroma Vericisi",  # десятичная запятая не делит компонент, «270 mg» — не компонент
    ]
    # «İlaç Değildir» повторяет дисклеймер карточки; «Form / Tablet» — таблица, не способ применения.
    assert parts["warnings"] == [
        "Tavsiye edilen günlük porsiyonu aşmayın.",
        "Takviye edici gıdalar normal beslenmenin yerine geçmez.",
    ]
    assert parts["storage"] == ["Direkt güneş ışığından uzak, serin ve kuru yerde muhafaza ediniz."]
    assert parts["usage"] == ["Günde 1 tane çiğneyerek tüketilebilir."]


def test_standard_phrases_without_label_and_substance_names():
    text = (
        "Fosfotidilserin, Fosfotidilkolin ve Taurin içeren sıvı takviye edici gıda.\n"
        "Çocukların ulaşamayacağı yerde saklayınız. 25°C altında, kuru ve serin bir yerde saklayınız.\n"
        "Gıda Takviyesidir."
    )
    parts = sm.section_parts({"product_info": text})

    # «Fosfotidil-serin» — вещество, а не «serin» (прохладное место).
    assert parts == {
        "warnings": ["Çocukların ulaşamayacağı yerde saklayınız."],
        "storage": ["25°C altında, kuru ve serin bir yerde saklayınız."],
    }


def test_composition_stops_at_dose_table_and_broken_lines_are_joined():
    # Фрагменты карточек OSENDE D3K2, XPECIA, VELAVIT D3K2 (ilacfiyati 05.11.2026), сокращены.
    text = (
        "İçindekiler:\n"
        "Zeytinyağı, Kolekalsiferol (Vitamin D3), 2 tablet için, 25 µg(1000 UI)\n"
        "Etken Madde\n"
        "Miktar / 10ml\n"
        "Demir\n"
        "Uyarılar:\n"
        "Tavsiye edilen\n"
        "günlük alım dozunu aşmayınız. Takviye edici gıdalar normal beslenmenin yerine geçemez. Çocukların\n"
        "ulaşamayacağı yerde saklayınız.\n"
        "Raf Ömrü Bilgisi\n"
        "BiGaia Damla Nasıl Kullanılır?"
    )
    parts = sm.section_parts({"product_info": text})

    assert parts == {
        "composition": ["Zeytinyağı", "Kolekalsiferol (Vitamin D3)"],
        "warnings": [
            "Tavsiye edilen günlük alım dozunu aşmayınız.",
            "Takviye edici gıdalar normal beslenmenin yerine geçemez.",
            "Çocukların ulaşamayacağı yerde saklayınız.",
        ],
    }


def test_list_of_only_excipients_is_not_called_composition_and_package_data_is_dropped():
    # SOLGAR PSYLLIUM HUSKS: действующее вещество — в таблице доз, список — вспомогательные вещества.
    text = (
        "İçindekiler:\n"
        "Kapsül (hidroksipropilmetil selüloz), topaklanmayı önleyici (yağ asitlerinin magnezyum tuzları)\n"
        "ETKEN MADDELER\n"
        "Karnıyarık otu lifi ( Plantago ovata )\n"
        "Uyarılar:\n"
        "Serin ve kuru yerde muhafaza ediniz. Tavsiye Edilen Tüketim Tarihinden (TETT) önce tüketiniz.\n"
        "Maya, buğday, glüten, soya ve süt ürünleri gibi potansiyel alerjenleri içermez.\n"
        "Parti No ve Tavsiye Edilen Tüketim Tarihi (TETT) kutunun alt yüzündedir."
    )
    parts = sm.section_parts({"product_info": text})

    assert parts == {
        "excipients": ["Kapsül (hidroksipropilmetil selüloz)", "topaklanmayı önleyici (yağ asitlerinin magnezyum tuzları)"],
        "warnings": ["Serin ve kuru yerde muhafaza ediniz."],
    }


@pytest.mark.parametrize(
    "source, ru, en, problems",
    [
        # Ошибки пилота 05.11.2026 на сервере (Haiku 5.5).
        ("Rezene Tohum Ekstraktı", "Экстракт семян укропа", "Fennel seed extract", ["supplement_ingredient_mistranslated"]),
        ("Mine Çiçeği Toprak Üstü Ekstraktı", "Экстракт надземной части мяты", "Mint aerial part extract",
         ["supplement_ingredient_mistranslated"]),
        ("Dul Avrat Otu", "Дул Аврат Оту", "Dul Avrat Otu", ["supplement_ingredient_mistranslated"]),
        ("Dokosahekzaenoik asit (DHA)", "Docosahexaenoic acid (DHA)", "Docosahexaenoic acid (DHA)", ["ru_latin_not_in_source"]),
        # Пилот 3: «tok karnına» (после еды) — «натощак»; «Passiflora» — «маракуйя».
        ("Yetişkinler için tok karnına günde 1-2 tablet.", "Взрослым принимать 1-2 таблетки в день натощак.",
         "For adults, take 1-2 tablets per day on an empty stomach.", ["meal_timing_mistranslated"]),
        ("Passiflora toprak üstü ekstresi (Passiflora incarnata)", "Экстракт надземной части маракуйи (Passiflora incarnata)",
         "Passionflower aerial part extract (Passiflora incarnata)", ["supplement_ingredient_mistranslated"]),
        # Верные: латиница из источника допустима.
        ("Hayıt Tohum Ekstraktı", "Экстракт семян авраамова дерева", "Chaste tree seed extract", []),
        ("Saw Palmetto Meyve Ekstresi", "Экстракт плодов Saw Palmetto", "Saw Palmetto fruit extract", []),
        ("Gün içinde aç ya da tok karnına kullanılabilir.", "Можно принимать натощак или после еды.",
         "Can be taken on an empty stomach or after a meal.", []),
        # Ревью PR #313: перевороты смысла, которые проходили проверки чисел и сдвига.
        ("Yetişkinler için günde 3 kez aç karnına 1'er kapsül alınması önerilir.",
         "Взрослым рекомендуется по 1 капсуле 3 раза в день после еды.",
         "Adults: 1 capsule 3 times a day after a meal.", ["meal_timing_mistranslated"]),
        ("Kronik hastalığı olanlar ve ilaç kullananlar doktora danışmadan kullanmamalıdır.",
         "Лицам с хроническими заболеваниями и принимающим лекарства можно применять после консультации с врачом.",
         "People with chronic diseases and those taking medicines may use it after consulting a doctor.", ["negation_lost"]),
        ("12 yaş altı çocuklarda kullanılmamalıdır.", "Не применять у детей старше 12 лет.",
         "Do not use in children over 12 years.", ["age_mistranslated"]),
        ("11 yaş ve üzeri yetişkinlerde günde 1 kapsül kullanılması önerilir.", "Детям младше 11 лет: 1 капсула в день.",
         "Children under 11: 1 capsule a day.", ["age_mistranslated"]),
        # Верные переводы запрета, возраста и «не заменяют».
        ("Takviye edici gıdalar normal beslenmenin yerine geçemez.", "Пищевые добавки не могут заменить нормальное питание.",
         "Food supplements cannot replace a normal diet.", []),
        ("12 yaş altı çocuklarda kullanılmamalıdır.", "Не применять у детей младше 12 лет.",
         "Do not use in children under 12 years of age.", []),
        ("Keçiboynuzu pekmezi", "Патока рожкового дерева", "Carob molasses", []),
        # Пилот 4: подсказка словаря целиком, турецкое слово в переводе; бренд и латынь с опечаткой источника — верно.
        ("Propolis", "прополис | propolis", "propolis", ["ru_untranslated"]),
        # Пилот на проде 06.11: латинские единицы в русском, «сафлор» без масла, «Убиквинол».
        # Волна 1в: «ölçek» — мерная ложка по словарю.
        ("Günde 2 ölçek 10 ml kullanılır.", "По 2 мерные ёмкости по 10 ml в день.", "2 scoops of 10 ml a day.",
         ["supplement_ingredient_mistranslated", "ru_untranslated"]),
        ("Aspir yağı", "сафлор", "safflower", ["supplement_ingredient_mistranslated"]),
        ("Ubikinol (Koenzim Q10) 200 mg", "Убиквинол (Коэнзим Q10) 200 мг", "Ubiquinol (Coenzyme Q10) 200 mg",
         ["supplement_ingredient_mistranslated"]),
        ("Aspir yağı", "сафлоровое масло", "safflower oil", []),
        # Пилот 2 на проде 06.11.2026: турецкое слово в скобках, слово дважды, турецкий процент, обрывок,
        # диапазон дважды, целлюлаза, саше.
        ("Menthol (mentol)%0.26", "Ментол (mentol) 0,26 %", "Menthol 0.26%", ["ru_untranslated"]),
        ("Thymol (timol)%0.0002", "Тимол (тимол)%0.0002", "Thymol 0.0002%", ["ru_untranslated"]),
        ("in lin", "in lin", "in lin", ["ru_untranslated"]),
        ("ADI", "ADI", "ADI", ["ru_untranslated"]),
        ("Yetişkinler için, tercihen yemek zamanı, günde bir-üç (1-3) kapsül.",
         "Для взрослых, предпочтительно во время еды, 1–3 (1-3) капсулы в день.",
         "For adults, preferably with meals, 1–3 capsules a day.", ["number_repeated"]),
        ("Selülaz", "Целлюлоза", "Cellulose", ["supplement_ingredient_mistranslated"]),
        ("bitkisel kapsül (hidroksipropil metil selülaz) (E464)", "растительная капсула (гидроксипропилметилцеллюлоза) (E464)",
         "vegetable capsule (hydroxypropyl methylcellulose) (E464)", []),
        ("Yetişkinler için günde 1 Şase (5000mg)'nin 300 ml su ile karıştırılarak tüketilmesi tavsiye edilir.",
         "Взрослым рекомендуется по 1 шасе (5000 мг) в день, смешав с 300 мл воды.",
         "Adults: 1 sachet (5000 mg) a day mixed with 300 ml of water.", ["supplement_ingredient_mistranslated"]),
        ("Menthol (mentol)%0.26", "Ментол 0,26 %", "Menthol 0.26%", []),
        # Ревью #328: опечатки «selülaz» в целлюлозах, сноска «(1)», коды как есть.
        ("Mikrokristalin selülaz", "Микрокристаллическая целлюлоза", "Microcrystalline cellulose", []),
        ("Hidroksipropil selülaz", "Гидроксипропилцеллюлоза", "Hydroxypropyl cellulose", []),
        ("D3 Vitamini (1)", "Витамин D3 (1)", "Vitamin D3 (1)", []),
        ("Omega-3 (3)", "Омега-3 (3)", "Omega-3 (3)", []),
        # Пилот 3 на проде 07.11.2026: растения и вещества словаря, возраст-опечатка источника.
        ("Tribulus Terrestris Extract", "Экстракт пузырника", "Tribulus extract", ["supplement_ingredient_mistranslated"]),
        # Пилот 4 на проде 07.11.2026.
        ("parlatıcı (sarı balmumu)", "подсластитель (жёлтый воск)", "sweetener (yellow beeswax)",
         ["supplement_ingredient_mistranslated"]),
        ("parlatıcı (sarı balmumu)", "глазирователь (жёлтый воск)", "glazing agent (yellow beeswax)", []),
        ("Akgünlük Ekstraktı (%19,06)", "Экстракт акгюнлюк (19,06 %)", "Akgunluk extract (19.06%)",
         ["supplement_ingredient_mistranslated", "ru_untranslated"]),
        ("Dilaltına günde 1-2 puf kullanılması tavsiye edilir.", "Дилатационно 1–2 пуфа в день.", "1–2 puffs a day.",
         ["supplement_ingredient_mistranslated", "ru_untranslated"]),
        ("Magnezyum Taurat", "Тауррат магния", "Magnesium taurate", ["ru_untranslated"]),
        ("kcenzim 010", "kcenzim 010", "kcenzim 010", ["ru_untranslated"]),
        ("11 yaş üzeri yetişkinler için günde 1 tablet tüketilmesi tavsiye edilir",
         "Взрослым и детям от 11 лет рекомендуется принимать 1 таблетка в день",
         "Adults and children over 11: 1 tablet a day", ["ru_grammar"]),
        # Перевод, который подсказывает словарь, в родительном падеже — верен (ревью #331).
        ("Tribulus Terrestris Extract", "Экстракт якорцев стелющихся", "Tribulus terrestris extract", []),
        ("Honry Goat Weed Extract", "Экстракт травы Honry Goat Weed", "Honry Goat Weed extract",
         ["supplement_ingredient_mistranslated"]),
        ("Menakuino 7", "Menakuino 7", "Menakuino 7", ["supplement_ingredient_mistranslated"]),
        ("Kapsül: Balık Jelatini", "Капсула: рыбий желатин", "Capsule: fish gelatin", []),
        ("1 yaş ve üzeri yetişkinlerin günde 1 saşe kullanması önerilir.", "Взрослым и детям от 1 года — 1 саше в день.",
         "Adults and children aged 1 year and older: 1 sachet a day.", ["age_suspicious"]),
        ("11 yaş ve üzeri yetişkinlerin günde 1 saşe kullanması önerilir.", "Взрослым и детям от 11 лет — 1 саше в день.",
         "Adults and children aged 11 and over: 1 sachet a day.", []),
        ("Q10", "Q10", "Q10", []),
        ("B6", "B6", "B6", []),
        # Штамм латиницей с «GR-1» — не единица (ревью #327).
        ("Lactobacillus rhamnosus GR-1", "Lactobacillus rhamnosus GR-1", "Lactobacillus rhamnosus GR-1", []),
        # Повторное ревью: «не» при деепричастии — не запрет.
        ("Doktora danışmadan kullanmamalıdır.", "Могут применять, не превышая дозу.", "May use, not exceeding the dose.",
         ["negation_lost"]),
        ("Melaloyka Yaği", "Мелалойка Ягы (Melaloyka Yağı)", "Melaloyka Yağı (Melaloyka Oil)",
         ["supplement_ingredient_mistranslated", "ru_untranslated"]),
        ("METİLMAX B12 vitamini", "METİLMAX с витамином B12", "METİLMAX with vitamin B12", []),
        ("Valerian (Valeriana off icinalis, kök)", "Валериана (Valeriana officinalis, корень)",
         "Valerian (Valeriana officinalis, root)", []),
    ],
)
def test_line_problems_catch_wrong_plants_and_english_words(source, ru, en, problems):
    assert sm.line_problems(source, ru, en) == problems


def test_usage_keeps_only_dosing_sentences_and_source_escapes_are_fixed():
    text = (
        "Kullanım Şekli:\n"
        "Yetişkinler için günde 3 defa 1u2019er tablet. Sprey formu ile kolay kullanım avantajı sağlar. "
        "Hücresel enerjisi artan cilt hücreleri daha hızlı yenilenir."
    )
    assert sm.section_parts({"product_info": text}) == {"usage": ["Yetişkinler için günde 3 defa 1’er tablet."]}


def test_dose_table_is_not_composition_and_storage_keeps_only_storage():
    # PHARMATON VITALITY и NBTLIFE MULTILIFE (пилот 2, 05.11.2026), сокращены.
    text = (
        "İçerik:\n"
        "Vitaminler\n"
        "Vitamin A\n"
        "640 μg RE\n"
        "Muhafaza Koşulları:\n"
        "Oda sıcaklığında, serin ve kuru yerde muhafaza ediniz. Şeker, tuz, nişasta içermez.\n"
        "Vegan ve vejetaryen bireylerin kullanımına da uygundur. Takviye edici gıdalar normal beslenmenin yerine geçemez.\n"
        "Uyarılar:\n"
        "Soya, buğday ve balık gibi potansiyel alerjenleri içermez. Tavsiye edilen günlük porsiyonu aşmayın.\n"
        "*** Takviye edici gıdalar normal beslenmenin yerine geçemez."
    )
    assert sm.section_parts({"product_info": text}) == {
        "storage": ["Oda sıcaklığında, serin ve kuru yerde muhafaza ediniz."],
        "warnings": ["Takviye edici gıdalar normal beslenmenin yerine geçemez.", "Tavsiye edilen günlük porsiyonu aşmayın."],
    }


def test_attribute_table_label_warnings_and_dose_rows_are_not_composition():
    # PHARMATON 50 PLUS, ANTI NATURAL, PHYTORELIEF, VELAVIT, BEE & YOU (пилот 3, 05.11.2026), сокращены.
    pharmaton = (
        "İçerik Bilgisi:\n"
        "Takviye edici gıdalar normal beslenmenin yerine geçemez.\n"
        "Çocukların ulaşamayacağı yerde saklayınız.\n"
        "Form\nKapsül\nİçerik\nBakır B Vitaminleri C Vitamini Çinko"
    )
    assert sm.section_parts({"product_info": pharmaton}) == {
        "warnings": ["Takviye edici gıdalar normal beslenmenin yerine geçemez.", "Çocukların ulaşamayacağı yerde saklayınız."],
    }
    dotted = "İçerik: Her 1 Kapsül İçin;\nMagnezyum Bisglisinat.......125 mg\nVitamin C.............................40 mg"
    assert sm.section_parts({"product_info": dotted}) == {"composition": ["Magnezyum Bisglisinat", "Vitamin C"]}
    columns = "Ürün Bileşimi:\nAktif Bileşenler Bir Pastil Bir Günlük Turmeric ( Zerdeçal ) 50 Mg 150 Mg\nGinger ( Zencefil ) 5 Mg 15 Mg"
    assert sm.section_parts({"product_info": columns}) == {}
    usage = (
        "Kullanım Şekli\n30 Tablet\nKullanım Önerisi: Günde 3 defa 2 puf kullanılması önerilir. "
        "Pratik sprey formu sayesinde ürünü doğrudan boğaza uygulayarak kolayca tüketebilirsiniz."
    )
    assert sm.section_parts({"product_info": usage}) == {"usage": ["Günde 3 defa 2 puf kullanılması önerilir."]}


def test_tablet_coating_is_excipients_but_active_substances_with_e_codes_are_not():
    coating = "İçindekiler: Mikrokristalin Selüloz, Polivinil Alkol, Talk, Silikon Dioksit (E 551)"
    assert list(sm.section_parts({"product_info": coating})) == ["excipients"]
    vitamin = "İçindekiler: L-Askorbik Asit (Vitomin C, Hacim Artırıcı Mikrokristalin Selüloz, Talk"
    assert list(sm.section_parts({"product_info": vitamin})) == ["composition"]
    # Ревью PR #313: кальций в БАДе с кальцием и витамин E — действующие вещества.
    calcium = "İçindekiler: Kalsiyum karbonat (E170), Mikrokristalin selüloz"
    assert list(sm.section_parts({"product_info": calcium})) == ["composition"]
    assert list(sm.section_parts({"product_info": "İçindekiler: Vitamin E 400 IU, Jelatin"})) == ["composition"]


def test_contraindications_wrapped_lines_and_unlabeled_descriptions():
    # Ревью PR #313: «Aşağıdaki … kullanmayınız:» — противопоказание, а не подпись другого раздела.
    text = "Uyarılar:\nAşağıdaki durumlarda kullanmayınız: kalp hastalığı."
    assert sm.section_parts({"product_info": text}) == {"warnings": ["Aşağıdaki durumlarda kullanmayınız: kalp hastalığı."]}
    unlabeled = "Aşağıdaki durumlarda kullanmayınız: kalp hastalığı."
    assert sm.section_parts({"product_info": unlabeled}) == {"warnings": [unlabeled]}
    # Перенос после запятой со строки с заглавной буквы — одна фраза.
    wrapped = "Uyarılar:\nHamile ve emziren kadınlar,\nDoktora danışmadan kullanmamalıdır."
    assert sm.section_parts({"product_info": wrapped}) == {
        "warnings": ["Hamile ve emziren kadınlar, Doktora danışmadan kullanmamalıdır."]
    }
    # Строки описания без подписи — не предупреждения, хотя в них «hamile», «doktor».
    indications = (
        "Hamilelik ve emzirme döneminde ihtiyaç duyulan vitamin ve mineralleri içerir.\n"
        "Doktorlar tarafından önerilen formül."
    )
    assert sm.section_parts({"supplement_indications": indications}) == {}
    # «Aşağıdaki örnek beslenme tablosunu …» — ссылка на таблицу, которой в карточке нет.
    table = "Kullanım Şekli:\nAşağıdaki örnek beslenme tablosunu doktorunuza danışarak kullanabilirsiniz."
    assert sm.section_parts({"product_info": table}) == {}


TREATMENT_CLAIMS = {
    # Повторное ревью PR #313: обещания лечения в способе применения проходили модерацию.
    "Soğuk algınlığı tedavisinde günde 2 tablet kullanılır.": (
        "При лечении простуды — 2 таблетки в день.", "For treating colds: 2 tablets a day."
    ),
    "Bağışıklığı korumak için günde 1 tablet kullanılır.": (
        "Для защиты иммунитета — 1 таблетка в день.", "To protect immunity: 1 tablet a day."
    ),
    "Kolesterolü düşürmek için günde 1 kapsül kullanılır.": (
        "Для снижения холестерина — 1 капсула в день.", "To lower cholesterol: 1 capsule a day."
    ),
}


@pytest.mark.django_db
@pytest.mark.parametrize("source", list(TREATMENT_CLAIMS))
def test_treatment_claim_in_usage_hides_block_and_goes_to_moderation(source):
    ru, en = TREATMENT_CLAIMS[source]
    remember(sm.LINE_NAMESPACE, {source: {"ru": ru, "en": en}})

    blocks, _usage = sm.translate_blocks({"product_info": f"Kullanım Şekli: {source}"}, None)

    assert blocks.ru == {} and blocks.stats["claim_blocks"] == ["usage"]
    # Если такой абзац всё же в описании (старый лог, правка), модерация его ловит, а числа в нём не проверяет.
    text = f"Способ применения: {ru}"
    description = f"<p>SOLGAR — пищевая добавка.</p><p>{text}</p>"
    assert sc.description_problems(description, "SOLGAR", [text]) == ["supplement_health_claim"]


def test_treatment_words_in_warnings_and_composition_names_are_not_claims():
    assert not sm.memory_text_claim("Предупреждения: При заболеваниях сердца не применять без консультации врача.")
    assert not sm.memory_text_claim("Состав: экстракт лечебной ромашки, вода.")
    assert sm.memory_text_claim("Способ применения: При лечении простуды — 2 таблетки в день.")


def test_warning_about_table_dose_is_kept():
    # Повторное ревью: «tablo» выбрасывал предупреждение, и блок выглядел полным.
    text = "Uyarılar:\nTabloda belirtilen günlük dozu aşmayınız."
    assert sm.section_parts({"product_info": text}) == {"warnings": ["Tabloda belirtilen günlük dozu aşmayınız."]}


def test_health_claims_are_not_taken_into_blocks():
    # VITAGLUCAN (пилот 4): заявления о пользе под подписью способа применения.
    text = (
        "Kullanım Önerisi: Yetişkinler için günde 1 tablet.\n"
        "Ürünün içeriğinde bulunan C vitamini;\n"
        "- Yorgunluk ve bitkinliğin azalmasına katkıda bulunur.\n"
        "Uyarılar:\nTedavi gören kişiler doktoruna danışarak kullanmalıdır."
    )
    assert sm.section_parts({"product_info": text}) == {
        "usage": ["Yetişkinler için günde 1 tablet."],
        "warnings": ["Tedavi gören kişiler doktoruna danışarak kullanmalıdır."],
    }


@pytest.mark.django_db
def test_block_with_benefit_claim_in_translation_is_not_shown():
    usage = "Günde 1 tablet su ile alınır."
    remember(sm.LINE_NAMESPACE, {usage: {"ru": "1 таблетка в день, способствует бодрости.", "en": "1 tablet a day."}})

    blocks, _usage = sm.translate_blocks({"product_info": f"Kullanım Şekli:\n{usage}"}, None)

    assert blocks.ru == {} and blocks.stats["claim_blocks"] == ["usage"]


@pytest.mark.django_db
def test_fragment_keeps_block_out():
    text = "Uyarılar:\nTavsiye edilen günlük porsiyonu aşmayın.\nHamile ve emziren kadınlar,\nMuhafaza Koşulları:"
    blocks, _usage = sm.translate_blocks({"product_info": text}, _translator_llm())

    assert blocks.ru == {} and blocks.stats["fragments"] == ["Hamile ve emziren kadınlar,"]
    assert blocks.stats["incomplete_blocks"] == ["warnings"]


@pytest.mark.django_db
def test_short_parts_go_one_per_request():
    # Ревью PR #313: «Jelatin» ↔ «Gliserin» в одном запросе переставлялись без пропуска и проходили проверки.
    translations = {"Jelatin": ("желатин", "gelatin"), "Gliserin": ("глицерин", "glycerol"), "Su": ("вода", "water")}
    requests = []

    def answer(user_prompt):
        items = json.loads(user_prompt.split("\n\n", 1)[1])
        requests.append(list(items.values()))
        return {key: {"ru": translations[text][0], "en": translations[text][1]} for key, text in items.items()}

    blocks, _usage = sm.translate_blocks({"ingredients": "İçeriği: Jelatin, Gliserin, Su"}, _translator_llm(answer))

    assert requests == [["Jelatin"], ["Gliserin"], ["Su"]]
    assert blocks.ru == {"composition": ["желатин", "глицерин", "вода"]}


@pytest.mark.django_db
def test_lines_of_rejected_card_are_not_reused_and_give_way_to_new_translation():
    product = Product.objects.create(name="X", slug="sup-line-log")
    log = AIProcessingLog.objects.create(product=product, status=AIProcessingStatus.MODERATION, input_data={})
    remember(sm.LINE_NAMESPACE, {"Tavsiye edilen günlük porsiyonu aşmayın.": {"ru": "Плохо", "en": "Bad"}}, log=log)
    text = "Uyarılar:\nTavsiye edilen günlük porsiyonu aşmayın."
    fresh = AIProcessingLog.objects.create(product=product, status=AIProcessingStatus.PROCESSING, input_data={})

    blocks, _usage = sm.translate_blocks({"product_info": text}, _translator_llm(), log=fresh)

    assert blocks.ru == {"warnings": ["Не превышайте рекомендуемую суточную порцию."]}
    entry = AITranslationMemory.objects.get(namespace=sm.LINE_NAMESPACE)
    assert (entry.ru_text, entry.source_log_id) == ("Не превышайте рекомендуемую суточную порцию.", fresh.pk)


@pytest.mark.django_db
def test_english_instead_of_russian_is_retried_once():
    calls = []

    def english_first(user_prompt):
        calls.append(user_prompt)
        items = json.loads(user_prompt.split("\n\n", 1)[1])
        ru = "Olive oil" if len(calls) == 1 else "Оливковое масло"
        return {key: {"ru": ru, "en": "Olive oil"} for key in items}

    blocks, usage = sm.translate_blocks({"ingredients": "İçeriği:\nZeytinyağı"}, _translator_llm(english_first))

    assert len(calls) == 2 and usage["cost_usd"] == pytest.approx(0.0004)
    assert blocks.ru == {"composition": ["Оливковое масло"]}


@pytest.mark.django_db
def test_bacteria_strains_stay_latin_without_model():
    llm = SimpleNamespace(generate_content=Mock())

    blocks, _usage = sm.translate_blocks({"ingredients": "İçeriği:\nLactobacillus acidophilus- LA-5®, Bifidobacterium- BB-12®"}, llm)

    assert blocks.ru == {"composition": ["Lactobacillus acidophilus- LA-5®", "Bifidobacterium- BB-12®"]}
    llm.generate_content.assert_not_called()


@pytest.mark.django_db
def test_glossary_hints_go_to_translator_and_wrong_plant_is_not_remembered():
    def wrong(user_prompt):
        items = json.loads(user_prompt.split("\n\n", 1)[1])
        return {key: {"ru": "Экстракт семян укропа", "en": "Fennel seed extract"} for key in items}

    llm = _translator_llm(wrong)
    blocks, _usage = sm.translate_blocks({"ingredients": "İçeriği:\nRezene Tohum Ekstraktı"}, llm)

    assert "REZENE" in llm.generate_content.call_args.kwargs["system_prompt"]
    # Только первый вариант словаря: «фолиевая кислота / фолат» модель переносила в перевод целиком.
    sm.translate_blocks({"ingredients": "İçeriği:\nFolik asit"}, llm)
    assert '"FOLIK ASIT": {"ru": "фолиевая кислота", "en": "folic acid"}' in llm.generate_content.call_args.kwargs["system_prompt"]
    assert blocks.ru == {} and blocks.stats["rejected"] == {"Rezene Tohum Ekstraktı": ["supplement_ingredient_mistranslated"]}
    assert not AITranslationMemory.objects.filter(namespace=sm.LINE_NAMESPACE).exists()


@pytest.mark.django_db
def test_new_parts_are_translated_once_and_then_come_from_memory():
    sections = {"product_info": PRODUCT_INFO, "ingredients": INGREDIENTS}
    llm = _translator_llm()

    blocks, usage = sm.translate_blocks(sections, llm)

    # «Su» и «Tatlandırıcı (Eritrol, Ksilitol)» — короткие, по одной на запрос; остальные 6 — одним запросом.
    assert llm.generate_content.call_count == 3
    assert usage["cost_usd"] == pytest.approx(0.0006)
    assert blocks.ru["usage"] == ["По 1 штуке в день, разжёвывая."]
    assert blocks.stats["translated"] == 8 and blocks.stats["cached"] == 0
    assert AITranslationMemory.objects.filter(namespace=sm.LINE_NAMESPACE).count() == 8

    again, usage = sm.translate_blocks(sections, _translator_llm())
    assert again.ru == blocks.ru and again.stats["cached"] == 8 and usage["cost_usd"] == 0


@pytest.mark.django_db
def test_shifted_answer_keeps_block_out_and_memory_clean():
    def shifted(user_prompt):
        answer = _answer_for(user_prompt)
        keys = list(answer)
        return {key: answer[keys[min(index + 1, len(keys) - 1)]] for index, key in enumerate(keys)}

    blocks, _usage = sm.translate_blocks({"product_info": PRODUCT_INFO}, _translator_llm(shifted))

    assert blocks.ru == {}
    assert set(blocks.stats["incomplete_blocks"]) == {"usage", "warnings", "storage"}
    assert not AITranslationMemory.objects.filter(namespace=sm.LINE_NAMESPACE).exists()


@pytest.mark.django_db
def test_admin_edit_in_memory_is_used_without_model():
    remember(sm.LINE_NAMESPACE, {"Günde 1 tane çiğneyerek tüketilebilir.": {"ru": "1 штука в день.", "en": "1 a day."}})
    llm = SimpleNamespace(generate_content=Mock())

    blocks, _usage = sm.translate_blocks({"product_info": "Kullanım Şekli:\nGünde 1 tane çiğneyerek tüketilebilir."}, llm)

    assert blocks.ru == {"usage": ["1 штука в день."]}
    llm.generate_content.assert_not_called()


@pytest.mark.django_db
def test_bad_translation_already_in_memory_is_retranslated_and_replaced_but_manual_edit_is_kept():
    # Ревью #327: «mg/5ml» и «сафлор» из памяти прода снова попадали на карточки — проверки шли только по новым.
    product = Product.objects.create(name="X", slug="sup-line-bad-memory")
    log = AIProcessingLog.objects.create(product=product, status=AIProcessingStatus.COMPLETED, input_data={})
    remember(sm.LINE_NAMESPACE, {"Aspir yağı": {"ru": "сафлор", "en": "safflower"}}, log=log)
    remember(sm.LINE_NAMESPACE, {"Su": {"ru": "вода (H2O) 10 ml", "en": "water"}})  # ручная правка — без лога
    translations = {"Aspir yağı": ("сафлоровое масло", "safflower oil")}

    def answer(user_prompt):
        items = json.loads(user_prompt.split("\n\n", 1)[1])
        return {key: {"ru": translations[text][0], "en": translations[text][1]} for key, text in items.items()}

    blocks, _usage = sm.translate_blocks({"ingredients": "İçeriği: Aspir yağı, Su"}, _translator_llm(answer))

    assert blocks.ru == {"composition": ["сафлоровое масло", "вода (H2O) 10 ml"]}
    assert blocks.stats["memory_rejected"] == {"Aspir yağı": ["supplement_ingredient_mistranslated"]}
    entry = AITranslationMemory.objects.get(namespace=sm.LINE_NAMESPACE, source_text="Aspir yağı")
    assert entry.ru_text == "сафлоровое масло"


@pytest.mark.parametrize(
    "text, composition",
    [
        # Заголовки таблицы вместо состава (пилот 2 на проде, 06.11.2026).
        ("İçerik Bilgisi:\nAdı\nMiktarı\nBalık Yağı\n1100 mg", None),  # OCEAN PULSE 7257
        ("İçindekiler: Her 1 tablette;\n%BRD\nAlfa Lipoik Asit 200 mg", None),  # NUTRAXIN 7233
        ("Ürün Bileşenleri\nGünlük Doz2 kapsül\nRDA\nVitamin C Buffered C\n1000 mg", None),  # NUTRAFARM 7242
        ("Ürün Bileşimi:\nADI", None),  # OCEAN IODINE 7227
        ("Bileşenler: Her kapsülde;\n1000 mg Çörek Otu Yağı", ["1000 mg Çörek Otu Yağı"]),  # OCEAN 7287
        # Состав фразой с «E», «B3» — не список (DOPPELHERZ 7300).
        ("Ürün Bileşimi:\nKoenzim Q10, E, B3, B5, B12, B2, B6, B1 Vitaminleri, Biotin ve Selenyum içerir.", None),
        # Английская копия с ошибками распознавания (ZADE VITAL 7357).
        ("İçindekiler: glutatyon, biotin, metilkobalamin (B12 vitamini). INGREDIENTS: Hydtrolyzed fsh collagen, "
         "peptides, inulin", ["glutatyon", "biotin", "metilkobalamin (B12 vitamini)"]),
        # Сноска, приклеенная к компоненту (PHARMATON 7265).
        ("İçindekiler: Biotin, Kolekalsiferol. Formülasyonda kaplama maddesi olarak kullanilan bilesenin ticari "
         "markasidır", ["Biotin", "Kolekalsiferol"]),
        # Сокращения — не сноска (ревью #328).
        ("İçindekiler: Bifidobacterium (B. Lactis BB-12) 1 milyar KOB, Vit. C Askorbik asit 500 mg",
         ["Bifidobacterium (B. Lactis BB-12) 1 milyar KOB", "Vit. C Askorbik asit 500 mg"]),
        ("İçindekiler: Ekstr. Ginkgo biloba yaprak ekstresi 120 mg, Havuç konsantresi. Kapsül kabuğu bileşenleri: "
         "sığır jelatini",
         ["Ekstr. Ginkgo biloba yaprak ekstresi 120 mg",
          "Havuç konsantresi. Kapsül kabuğu bileşenleri: sığır jelatini"]),
    ],
)
def test_composition_without_table_headers_prose_and_second_copies(text, composition):
    assert sm.section_parts({"product_info": text}).get("composition") == composition


@pytest.mark.parametrize(
    "text, expected",
    [
        # VELAVIT KIDS 7511: строка таблицы — не способ применения.
        ("Kullanım Şekli:\n4-11 Yaş Arası 1,11 ve Üzeri Çiğnenebilir Tablet", {}),
        # Но указания без привычного глагола остаются.
        ("Kullanım Şekli:\nAkut Dönemde 12'şer Saat Arayla 2×1 Kapsül, Sonrasında Koruyucu Olarak 1×1 Kapsül",
         {"usage": ["Akut Dönemde 12'şer Saat Arayla 2×1 Kapsül, Sonrasında Koruyucu Olarak 1×1 Kapsül"]}),
        ("Kullanım Şekli:\nGünde 1 kapsül.\n(Tercihen Yemekle Birlikte ya da Yemekten Hemen Sonra)",
         {"usage": ["Günde 1 kapsül.", "(Tercihen Yemekle Birlikte ya da Yemekten Hemen Sonra)"]}),
        ("Kullanım Şekli:\nGünde 5 damla. Damlalar kaşıkla verilebilir.",
         {"usage": ["Günde 5 damla.", "Damlalar kaşıkla verilebilir."]}),
        # NUTRAXIN QUICK-SLIM 7423: «* Kafein içerir» — отдельная фраза, без звёздочки.
        ("Kullanım Şekli:\nGünde 3 defa 1 tablet kullanılması önerilir. * Kafein içerir.",
         {"usage": ["Günde 3 defa 1 tablet kullanılması önerilir."]}),
        # POREGE 7533: сводка через «--» — остаётся компонент после неё.
        ("Ürün Bileşimi:\nPropolis - Karamürver - Melaloyka Yağı -- Su, Propolis Ekstresi, Kara Mürver Ekstresi",
         {"composition": ["Su", "Propolis Ekstresi", "Kara Mürver Ekstresi"]}),
        # Компонент с тире — не сводка (ревью #331).
        ("İçindekiler: D-Mannoz, Kızılcık Ekstresi - Vaccinium macrocarpon - %25 PAC, Jelatin",
         {"composition": ["D-Mannoz", "Kızılcık Ekstresi - Vaccinium macrocarpon - %25 PAC", "Jelatin"]}),
        # Способ применения с заглавных — не строка таблицы (ревью #331).
        ("Kullanım Şekli:\nGünlük 1 Kapsül Su İle Alınız", {"usage": ["Günlük 1 Kapsül Su İle Alınız"]}),
        ("Kullanım Şekli:\nHer Gün 1 Tablet Su İle Alınız", {"usage": ["Her Gün 1 Tablet Su İle Alınız"]}),
        ("Kullanım Şekli:\nYetişkinler İçin Günlük 2 Tablet", {"usage": ["Yetişkinler İçin Günlük 2 Tablet"]}),
    ],
)
def test_pilot3_usage_rows_footnotes_and_summary_items(text, expected):
    assert sm.section_parts({"product_info": text}) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        # COXIL 7544: маркеры списка; OSENDE 7569: «•» вместо дефиса; GONAMAX 7623: фасовка вместо компонента.
        ("Ürün Bileşimi:\n- Sambucus Nigra (Karamürver), - Gam arabik, - Stevia, DL•a-tokoferil asetat, 30 kapsül",
         {"composition": ["Sambucus Nigra (Karamürver)", "Gam arabik", "Stevia", "DL-a-tokoferil asetat"]}),
        # DAY2DAY 7547: заголовок таблицы доз — не способ применения.
        ("Kullanım Şekli:\nGünde 10 g (1 ölçek) su ile karıştırılarak tüketilir. Her 1 ölçekte (10 g) ;",
         {"usage": ["Günde 10 g (1 ölçek) su ile karıştırılarak tüketilir."]}),
        # ACTIVE PLUS 7768: применение без дозы — блок неполный, не показывается.
        ("Kullanım Şekli:\n11 yaş ve üzeri yetişkinlerin kullanımına uygundur.", {}),
        # SUDA 7616: обещание пользы в применении.
        ("Kullanım Şekli:\nGünde 1 porsiyon tüketilir. 8 haftadan sonra elde ettiğiniz faydaya göre ayarlayabilirsiniz.",
         {"usage": ["Günde 1 porsiyon tüketilir."]}),
    ],
)
def test_pilot4_composition_and_usage_parsing(text, expected):
    assert sm.section_parts({"product_info": text}) == expected


def test_pilot4_usage_without_dose_is_marked_hidden():
    with mock.patch.object(sm, "lookup", return_value={}):
        blocks, _usage = sm.translate_blocks({"product_info": "Kullanım Şekli:\n11 yaş ve üzeri kullanım için uygundur."}, None)
    assert blocks.stats["hidden_blocks"] == {"usage": "no_dose"}


def test_partial_composition_with_actives_only_in_dose_table_is_hidden():
    # NUTRAXIN QUICK-SLIM 7423: в «Ürün Bileşimi» вспомогательные и хром, действующие — только в таблице доз.
    sections = {
        "product_info": "Her 3 Tablette\nYeşil Çay Ekstresi\n500 mg\nYeşil Kahve Ekstresi\n400 mg\nKafein\n80 mg",
        "ingredients": "Ürün Bileşimi:\nMikrokristalin Selüloz, Hidroksipropil Metil Selüloz, Silikon Dioksit, "
                       "Yağ Asitlerinin Magnezyum Tuzları, Krom Pikolinat.",
    }
    with mock.patch.object(sm, "lookup", return_value={}):
        blocks, _usage = sm.translate_blocks(sections, None)
    assert "composition" not in blocks.parts and blocks.stats["hidden_blocks"] == {"composition": "partial_list"}
    # Вещество и доза в одной строке таблицы — так же.
    inline = dict(sections, product_info="Her 3 Tablette\nYeşil Çay Ekstresi 300 mg\nKafein 150 mg\nAhududu Keton 75 mg")
    assert "composition" not in sm.section_parts(inline)
    # Одно действующее вещество + вспомогательные — полный состав (VENATURA SR VITAMIN C).
    single = {
        "product_info": "Her 1 tablette\nVitamin C\n1000 mg",
        "ingredients": "Ürün Bileşimi:\nL askorbik asit, Mikrokristalin selüloz, Silikon dioksit, Magnezyum stearat",
    }
    assert "composition" in sm.section_parts(single)
    # Вещества названы по-химически, в таблице — по-витаминному: состав полный (ревью #331).
    chemical = {
        "product_info": "Her 1 kapsülde\nVitamin D3\n25 µg\nVitamin K2\n75 µg",
        "ingredients": "İçindekiler: Kolekalsiferol, Menakinon-7, Mikrokristalin selüloz, Silikon dioksit, "
                       "Magnezyum stearat, Jelatin, Gliserin",
    }
    assert "composition" in sm.section_parts(chemical)


def test_prose_composition_is_marked_hidden_in_stats():
    text = "Ürün Bileşimi:\nKoenzim Q10, E, B3, B5 Vitaminleri, Biotin ve Selenyum içerir."
    with mock.patch.object(sm, "lookup", return_value={}):
        blocks, _usage = sm.translate_blocks({"ingredients": text}, None)
    assert blocks.stats["hidden_blocks"] == {"composition": "prose_list"}


def test_warning_under_usage_label_goes_to_warnings():
    # NUTRAFARM 7273: предупреждения внутри «Способа применения».
    text = ("Kullanım Şekli:\nGünde 2 kapsül alınız. Tavsiye edilen günlük dozu aşmayınız. "
            "Hamilelik döneminde doktorunuza danışınız.")
    assert sm.section_parts({"product_info": text}) == {
        "usage": ["Günde 2 kapsül alınız."],
        "warnings": ["Tavsiye edilen günlük dozu aşmayınız.", "Hamilelik döneminde doktorunuza danışınız."],
    }
    # Доза в запрете «… fazla …» — предупреждение (ревью #328).
    limits = "Kullanım Şekli:\nGünde 2 kapsülden fazla kullanmayınız. Bir defada 2 kapsülden fazla almayınız."
    assert sm.section_parts({"product_info": limits}) == {
        "warnings": ["Günde 2 kapsülden fazla kullanmayınız.", "Bir defada 2 kapsülden fazla almayınız."]
    }
    # Доза и запрет через запятую — доза в применении, запрет в предупреждениях (ревью #329).
    mixed = ("Kullanım Şekli:\nGünde 1 kapsül yemekle alınız, doktorunuza danışmadan daha fazla kullanmayınız. "
             "Günde 1 kapsül, 3 aydan fazla kullanmayınız.")
    assert sm.section_parts({"product_info": mixed}) == {
        "usage": ["Günde 1 kapsül yemekle alınız.", "Günde 1 kapsül."],
        "warnings": ["Doktorunuza danışmadan daha fazla kullanmayınız.", "3 aydan fazla kullanmayınız."],
    }
    # Десятичная запятая в дозе — не граница части фразы.
    decimal = ("Kullanım Şekli:\nGünde 2,5 ml alınız, 3 aydan fazla kullanmayınız. "
               "Günde 1,5 ölçek, doktorunuza danışmadan daha fazla kullanmayınız.")
    assert sm.section_parts({"product_info": decimal}) == {
        "usage": ["Günde 2,5 ml alınız.", "Günde 1,5 ölçek."],
        "warnings": ["3 aydan fazla kullanmayınız.", "Doktorunuza danışmadan daha fazla kullanmayınız."],
    }
    # С дозой — остаётся в применении (ревью #328).
    dose = "Kullanım Şekli:\nDoktorunuza danışarak günde 2 kapsül alınız."
    assert sm.section_parts({"product_info": dose}) == {"usage": ["Doktorunuza danışarak günde 2 kapsül alınız."]}


def test_unclosed_bracket_does_not_swallow_the_rest_of_composition():
    # HERBALAND 7156 (пилот 06.11.2026): «[» без «]» — витамины пропадали, а «Состав» выглядел полным.
    text = (
        "Ürün Bileşimi:\nŞeker Kamışı Şekeri, Su, Jelleştirici(Pektin), Multivitamin ve Mineral Karışımı(%3,77) "
        "[Vitamin C(L-askorbik asit), Vitamin E(DL-alfa-tokoferil asetat), D-Biotin, " + "Maltodekstrin, " * 40 + "Çinko."
    )
    parts = sm.section_parts({"ingredients": text})["composition"]
    assert parts[:5] == [
        "Şeker Kamışı Şekeri", "Su", "Jelleştirici(Pektin)", "Multivitamin ve Mineral Karışımı(%3,77): Vitamin C(L-askorbik asit)",
        "Vitamin E(DL-alfa-tokoferil asetat)",
    ]
    assert parts[-1] == "Çinko"
    # Часть длиннее UNIT_MAX_CHARS — блока нет совсем, а не без этой части; это видно в stats.
    long_warning = "Uyarılar:\nTavsiye edilen günlük porsiyonu aşmayın. " + "Hamilelik döneminde doktorunuza danışınız " * 12 + "."
    assert "warnings" not in sm.section_parts({"product_info": long_warning})
    with mock.patch.object(sm, "lookup", return_value={}):
        blocks, _usage = sm.translate_blocks({"product_info": long_warning}, None)
    assert blocks.stats["too_long_blocks"] == ["warnings"]
    # Незакрытая «(» в одном месте не отключает парные скобки: запятые внутри «(…, 10 mg)» список не дробят.
    mixed = "İçindekiler: Vitamin C (askorbik asit, 500 mg), Çinko (çinko sitrat, 10 mg), L-Askorbik Asit (Vitomin C, Talk"
    assert sm.section_parts({"product_info": mixed})["composition"] == [
        "Vitamin C (askorbik asit, 500 mg)", "Çinko (çinko sitrat, 10 mg)", "L-Askorbik Asit Vitomin C", "Talk",
    ]


def test_model_sentences_about_dosing_and_storage_are_dropped_when_blocks_cover_them():
    # Пилот на проде 06.11.2026: HERBALAND 7156, OSENDE 7171, STREPSILS 7148, OCEAN METHYL 7117.
    paragraphs = [
        "OSENDE QH Fort — пищевая добавка с убихинолом в мягких капсулах. В одной капсуле 200 мг убихинола.",
        "Принимать внутрь по 1 капсуле один раз в день.",
        "Детям 4–10 лет — по 1 конфете в день под присмотром взрослых. Таблетку растворяют в стакане воды.",
        "Ocean Methyl B12 — пищевая добавка в форме спрея для приёма под язык. Леденцы для рассасывания.",
        "Хранить в прохладном месте.",
    ]
    usage = "Способ применения: Рекомендуется принимать 1 капсулу 1 раз в день."
    with_blocks = sc.build_description(paragraphs, "ru", blocks=[usage], covered=sc.covered_by_blocks({"usage": [1]}))

    assert "один раз в день" not in with_blocks and "по 1 конфете" not in with_blocks and "растворяют" not in with_blocks
    assert "В одной капсуле 200 мг убихинола." in with_blocks and "для приёма под язык" in with_blocks
    assert "Леденцы для рассасывания." in with_blocks and "Хранить в прохладном месте." in with_blocks
    # Без блока способа применения модель о приёме говорит.
    assert "один раз в день" in sc.build_description(paragraphs, "ru")
    # Ложные срабатывания (ревью #327): описание, а не указание на приём или хранение.
    kept = ["Содержит 10 разных штаммов бактерий.", "Концентрация в 2 раза выше обычной.",
            "Капсулы удобно принимать.", "Капсула защищает от сохранения влаги."]
    covered = sc.covered_by_blocks({"usage": [1], "storage": [1]})
    assert all(sentence in sc.build_description(kept, "ru", blocks=[usage], covered=covered) for sentence in kept)
    # Если от текста модели ничего не осталось — блоки и дисклеймер остаются.
    only_dosing = sc.build_description(["Принимать внутрь."], "ru", blocks=[usage], covered=covered)
    assert only_dosing == f"<p>{usage}</p><p>{sc.DISCLAIMER['ru']}</p>"


def test_model_text_keeps_product_and_drops_what_blocks_say():
    # Пилот 2 на проде 06.11.2026.
    usage = "Способ применения: 1 капсула в день."
    covered = sc.covered_by_blocks({"usage": [1], "composition": [1], "warnings": [1]})
    paragraphs = [
        # SOLGAR 7225, 7318: «источник» — не рассуждение о данных, суть товара остаётся.
        "Мягкие капсулы с жиром печени трески, источником витаминов A и D.",
        "Состав: ментол, эвкалиптол.",  # OTACI 7210 — состав уже в блоке
        "Состав одной порции (2 мармеладки): экстракт эпимедиума 200 мг.",  # дозы на порцию — оставить
        "Принимать каждое утро: 2 мармеладки. Способ применения нужен для одного дня.",  # SOVITAL 7244
        "Хранить в недоступном для детей месте. Пищевые добавки не заменяют нормальный рацион.",  # NUTRAFARM 7273
        "Состав обновлён: в одной капсуле 480 мг экстракта.",  # HELIOCAPS 7259
        "Сироп во флаконе 150 мл. Ещё сироп в флаконе 100 мл.",  # OCEAN VM 7226
        "Пищевая добавка. Не заменяет нормальное питание.",  # OCEAN 7287
    ]
    text = sc.build_description(paragraphs, "ru", blocks=[usage], covered=covered)

    assert "источником витаминов A и D" in text and "Состав одной порции" in text
    assert "Состав: ментол" not in text and "каждое утро" not in text and "нужен для одного дня" not in text
    assert "недоступном" not in text and "не заменяют" not in text and "Пищевая добавка." not in text
    # «Не следует превышать дозу» модели при блоке предупреждений — тоже повтор (ревью #329).
    assert "превышать" not in sc.build_description(
        ["SOLGAR — витамин C.", "Не следует превышать рекомендуемую дозу."], "ru", blocks=[usage], covered=covered
    )
    assert "<p>В одной капсуле 480 мг экстракта.</p>" in text and "Ещё сироп во флаконе 100 мл." in text
    # Где нет блока состава и предупреждений — модель их называет.
    assert "Состав: ментол" in sc.build_description(paragraphs, "ru")
    # Одни «Вспомогательные вещества» состав не покрывают — действующие вещества модели остаются (ревью #328).
    excipients_only = sc.build_description(
        ["Состав: магний цитрат 300 мг, витамин B6 2 мг."], "ru",
        blocks=["Вспомогательные вещества: ГПМЦ."], covered=sc.covered_by_blocks({"excipients": [1]}),
    )
    assert "цитрат магния 300 мг" in excipients_only
    # «Содержание магния не превышает 300 мг» — не пересказ предупреждения.
    assert "не превышает 300 мг" in sc.build_description(
        ["Содержание магния не превышает 300 мг."], "ru", blocks=["Предупреждения: …"],
        covered=sc.covered_by_blocks({"warnings": [1]}),
    )
    # По-английски «source» — не рассуждение о данных (SOLGAR в EN).
    assert "natural source of vitamins" in sc.build_description(
        ["Cod liver oil is a natural source of vitamins A and D."], "en"
    )
    # Рассуждение о данных по-английски выпадает.
    meta = ["Cod liver oil softgels.", "The source provides no dosage.",
            "According to the source, one capsule contains 300 mg."]
    assert sc.build_description(meta, "en").startswith("<p>Cod liver oil softgels.</p><p>")
    assert "source" not in sc.build_description(meta, "en")


def test_pilot3_model_text_brand_turkish_brackets_and_block_wording():
    # VOONKA NEXT 7407: турецкие слова в скобках у модели.
    text = sc.build_description(["Состав: экстракт клюквы (Turna Yemişi) и шалфея (Adaçayı), D-манноза (D-Mannose)."], "ru")
    assert "Turna" not in text and "Adaçayı" not in text and "(D-Mannose)" in text
    # NATURES BOUNTY 7474: бренд в описании — латиницей, как в названии.
    assert sc._brand_latin(["Натурес Баунти — пищевая добавка."], "Натурес Баунти", "NATURES BOUNTY") == [
        "NATURES BOUNTY — пищевая добавка."
    ]
    # Только целым словом (ревью #331).
    assert sc._brand_latin("Нау — научно обоснованная формула.", "Нау", "NOW") == "NOW — научно обоснованная формула."
    assert sc._block_wording("2*1 капсула в день*") == "2*1 капсула в день"
    # NUTRAXIN 7455: «Cla», висящие звёздочки; SUNJOY 7377: «таблетка» у капсул.
    blocks = sm.SupplementBlocks(
        ru={"composition": ["Cla (конъюгированная линолевая кислота)", "Говяжий желатин*"],
            "usage": ["По 1 таблетке в день.", "* Содержит кофеин."]},
        en={"composition": ["Cla (conjugated linoleic acid)", "Bovine gelatin*"],
            "usage": ["1 tablet a day.", "* Contains caffeine."]},
    )
    ru = sc.memory_block_texts(blocks, "ru", "SUNJOY OMEGA MAX KAPSUL 30 kapsül")
    assert ru == ["Состав: CLA (конъюгированная линолевая кислота), Говяжий желатин.",
                  "Способ применения: По 1 капсуле в день. Содержит кофеин."]
    assert sc.memory_block_texts(blocks, "en", "SUNJOY OMEGA MAX KAPSUL 30 kapsül")[1] == (
        "How to use: 1 capsule a day. Contains caffeine."
    )
    # Подсказки словаря по веществам из разделов — модели.
    hints = sc._section_glossary({"ingredients": "Tribulus Terrestris Extract, Melaloyka Yağı"})
    assert hints["TRIBULUS"] == {"ru": "якорцы стелющиеся", "en": "tribulus"}
    assert hints["MELALOYKA"] == {"ru": "чайное дерево", "en": "tea tree"}


def test_pilot4_card_wording_translit_tablets_and_repeats():
    # Исправимый транслит: «ситрат», HELAL, «МСМ»; у таблеток «капсула» → «таблетка» (DYNAVIT 7688, 7719).
    text = sc.build_description(["Содержит магний ситрат и МСМ. Сертификат HELAL."], "ru")
    assert "цитрат" in text and "MSM" in text and "халяль" in text and "ситрат" not in text
    blocks = sm.SupplementBlocks(
        ru={"usage": ["1 капсула в день для взрослых.", "Взрослым рекомендуется принимать 1 порцию продукта в любое время суток.",
                      "Взрослым рекомендуется принимать 1 порцию (40 мл) продукта в любое время суток."]},
        en={"usage": ["1 capsule a day for adults.", "Adults: 1 serving at any time.", "Adults: 1 serving (40 ml) at any time."]},
    )
    ru = sc.memory_block_texts(blocks, "ru", "DYNAVIT BIOTIN TAKVIYE EDICI GIDA 5000 mcg 100 tablet")
    # Та же доза с уточнением в скобках — повтор (SUDA 7616); остаётся подробная.
    assert ru == ["Способ применения: 1 таблетка в день для взрослых. "
                  "Взрослым рекомендуется принимать 1 порцию (40 мл) продукта в любое время суток."]


def test_log_problems_flag_translit_and_baby_food():
    def log(name, description):
        return SimpleNamespace(
            raw_llm_response={"rule_content": {"supplement": {"brand": name.split()[0]}}},
            input_data={"name": name}, extracted_attributes={}, generated_title="", generated_description=description,
        )
    # CC II 7611, MAXLAK 7683: турецкое слово транслитом.
    assert "supplement_translit" in sc.log_problems(log("CC II KAPSUL 30 kapsül", "<p>Экстракт акгюнлюк.</p>"))["description"]
    # HIPP 7628: детское питание — всегда на модерацию.
    baby = sc.log_problems(log("HIPP 1 ORGANIK COMBIOTIC DEVAM SUTU 350 g", "<p>HIPP — молочная смесь.</p>"))
    assert "supplement_baby_food_review" in baby["description"]


def test_log_problems_flag_suspicious_source_age():
    # VIAPECIA 7524: «1 yaş ve üzeri yetişkinlerin» — опечатка источника, нужен человек.
    log = SimpleNamespace(
        raw_llm_response={"rule_content": {"supplement": {"brand": "VIAPECIA", "memory": {
            "rejected": {"1 yaş ve üzeri yetişkinlerin …": ["age_suspicious"]}}}}},
        input_data={"name": "VIAPECIA PRO-MAGNIUM SASE 20 saşe"}, extracted_attributes={}, generated_title="",
        generated_description="<p>VIAPECIA — магний в саше.</p>",
    )
    assert "supplement_source_suspicious" in sc.log_problems(log)["description"]


def test_pack_count_in_description_must_match_title():
    # OCEAN SMART GUMMIES 7360: «В одной упаковке 60 конфет» при «64 жевательные конфеты».
    pack = sc.parse_pack("OCEAN SMART GUMMIES MULTIVITAMIN TAKVIYE EDICI GIDA 64 çiğnenebilir jel form")
    assert sc.pack_mismatch("<p>В одной упаковке 60 конфет.</p>", pack)
    assert not sc.pack_mismatch("<p>Упаковка: 64 жевательные конфеты. Порция — 2 конфеты в день.</p>", pack)
    # Ревью #328: штаммы, порция в той же фразе, «2 x 30», блистеры.
    capsules = sc.parse_pack("X 60 Kapsül")
    assert not sc.pack_mismatch("<p>В упаковке 60 капсул с 10 штаммами бактерий.</p>", capsules)
    assert not sc.pack_mismatch("<p>В упаковке 60 капсул, по 2 капсулы в день.</p>", capsules)
    assert not sc.pack_mismatch("<p>Bottle of 60 softgels, take 2 softgels daily.</p>", capsules)
    assert not sc.pack_mismatch("<p>В упаковке 2 блистера по 30 капсул.</p>", capsules)
    assert not sc.pack_mismatch("<p>В упаковке 60 капсул.</p>", sc.parse_pack("X 2 x 30 Kapsül"))
    assert sc.pack_mismatch("<p>В упаковке 30 капсул.</p>", capsules)
    assert not sc.pack_mismatch("<p>В упаковке 60 капсул; 1 капсула = 1 порция.</p>", capsules)
    assert not sc.pack_mismatch("<p>Во флаконе по 1 капсуле на приём.</p>", capsules)
    # «В упаковке по 60 капсул» — фасовка, а не порция.
    assert sc.pack_mismatch("<p>Выпускается в упаковке по 60 капсул.</p>", sc.parse_pack("X 64 Kapsül"))


def test_log_problems_flag_pack_mismatch():
    log = SimpleNamespace(
        raw_llm_response={"rule_content": {"supplement": {"brand": "OCEAN"}}},
        input_data={"name": "OCEAN SMART GUMMIES MULTIVITAMIN TAKVIYE EDICI GIDA 64 çiğnenebilir jel form"},
        extracted_attributes={}, generated_title="",
        generated_description="<p>OCEAN — жевательные конфеты. В одной упаковке 60 конфет.</p>",
    )
    assert "supplement_pack_mismatch" in sc.log_problems(log)["description"]


def test_block_texts_drop_repeats_and_say_gummy_for_gummies():
    # IMUPLUS 120: одно и то же в предупреждениях и хранении, «дозу» и «порцию» дважды.
    blocks = sm.SupplementBlocks(
        ru={
            "usage": ["Детям 4–10 лет по 1 таблетке в день."],
            "warnings": ["Не превышайте рекомендуемую суточную дозу.", "Хранить в недоступном для детей месте.",
                         "Не превышайте рекомендуемую суточную порцию.", "Не применять детям до 4 лет."],
            "storage": ["Хранить в недоступном для детей месте при температуре ниже 25°C."],
        },
        en={
            "usage": ["Children 4–10: 1 tablet a day."],
            "warnings": ["Do not exceed the recommended daily dose.", "Keep out of reach of children.",
                         "Do not exceed the recommended daily portion.", "Not for children under 4."],
            "storage": ["Store out of reach of children below 25°C."],
        },
    )

    ru = sc.memory_block_texts(blocks, "ru", "HERBALAND MULTIVITAMINS GUMMIES CIGNENEBILIR FORM")
    en = sc.memory_block_texts(blocks, "en", "HERBALAND MULTIVITAMINS GUMMIES CIGNENEBILIR FORM")

    assert ru == [
        "Способ применения: Детям 4–10 лет по 1 жевательной конфете в день.",
        "Предупреждения: Не превышайте рекомендуемую суточную дозу. Не применять детям до 4 лет.",
        "Хранение: Хранить в недоступном для детей месте при температуре ниже 25°C.",
    ]
    assert en[0] == "How to use: Children 4–10: 1 gummy a day." and "portion" not in en[1]
    # У таблеток слово не меняется.
    assert "по 1 таблетке" in sc.memory_block_texts(blocks, "ru", "SOLGAR VITAMIN C 60 TABLET")[0]
    # Разные указания с общими словами — не повтор (PREGNACARE HIM & HER: розовый и фиолетовый блистер).
    pair = sm.SupplementBlocks(
        ru={"usage": ["Женщинам от 11 лет рекомендуется по 1 таблетке в день из таблеток в розовом блистере.",
                      "Мужчинам от 11 лет рекомендуется по 1 таблетке в день из таблеток в фиолетовом блистере."]},
        en={"usage": ["Women: 1 pink tablet a day.", "Men: 1 purple tablet a day."]},
    )
    assert "фиолетовом" in sc.memory_block_texts(pair, "ru")[0]
    # Одно и то же разными словами: «не следует превышать» = «превышать нельзя» (ревью #328).
    same = sm.SupplementBlocks(
        ru={"warnings": ["Не следует превышать рекомендуемую дозу.", "Рекомендуемую дозу превышать нельзя."]},
        en={"warnings": ["Do not exceed the recommended dose.", "The recommended dose must not be exceeded."]},
    )
    assert sc.memory_block_texts(same, "ru") == ["Предупреждения: Не следует превышать рекомендуемую дозу."]
    # Ревью #327: «не», числа целиком и группа людей.
    cases = [
        ("Принимать во время еды.", "Не принимать во время еды вместе с препаратами железа."),
        ("По 1 капсуле в день.", "Детям старше 12 лет по 1 капсуле в день."),
        ("По 1 капсуле в день.", "По 1–2 капсулы в день."),
        ("Взрослым по 2 капсулы в день во время еды, запивая водой.",
         "Беременным по 2 капсулы в день во время еды, запивая водой."),
        ("Содержит 100000 КОЕ в одной капсуле.", "Содержит 10000 КОЕ в одной капсуле."),
    ]
    for first, second in cases:
        both = sm.SupplementBlocks(ru={"usage": [first, second]}, en={"usage": ["a", "b"]})
        assert sc.memory_block_texts(both, "ru")[0] == f"Способ применения: {first} {second}", first


def test_chewable_tablets_are_not_gummies_and_wording_keeps_case():
    blocks = sm.SupplementBlocks(
        ru={"usage": ["Таблетку разжевать.", "По 1 жевательной таблетке в день."]},
        en={"usage": ["Chew the tablet.", "1 chewable tablet a day."]},
    )
    # «ÇİĞNENEBİLİR TABLET» — жевательная таблетка, слово не меняется.
    assert sc.memory_block_texts(blocks, "ru", "SOLGAR VITAMIN C CIGNENEBILIR TABLET 90")[0] == (
        "Способ применения: Таблетку разжевать. По 1 жевательной таблетке в день."
    )
    gummy = sc.memory_block_texts(blocks, "ru", "OCEAN SMART GUMMIES 60")[0]
    assert gummy == "Способ применения: Жевательную конфету разжевать. По 1 жевательной таблетке в день."
    assert sc.memory_block_texts(blocks, "en", "OCEAN SMART GUMMIES 60")[0] == (
        "How to use: Chew the gummy. 1 chewable tablet a day."
    )


def test_block_texts_keep_warnings_with_disease_words_and_go_before_disclaimer():
    # Ревью PR #313: фильтр обещаний лечения молча выбрасывал настоящие предупреждения и «лечебную ромашку».
    warning_ru = "Лицам с хроническими заболеваниями и принимающим лекарства не применять без консультации врача."
    warning_en = "People with chronic diseases or taking medicines should not use it without consulting a doctor."
    blocks = sm.SupplementBlocks(
        ru={"composition": ["вода", "экстракт лечебной ромашки"], "warnings": ["Не превышайте порцию", warning_ru]},
        en={"composition": ["water", "chamomile extract"], "warnings": ["Do not exceed the portion", warning_en]},
    )

    ru = sc.memory_block_texts(blocks, "ru")
    description = sc.build_description(["SOLGAR — пищевая добавка."], "ru", blocks=ru)

    assert ru == ["Состав: вода, экстракт лечебной ромашки.", f"Предупреждения: Не превышайте порцию. {warning_ru}"]
    assert sc.memory_block_texts(blocks, "en")[1] == f"Warnings: Do not exceed the portion. {warning_en}"
    assert description.endswith(f"<p>Предупреждения: Не превышайте порцию. {warning_ru}</p><p>{sc.DISCLAIMER['ru']}</p>")


def test_log_problems_do_not_check_memory_blocks_again():
    # Ревью PR #313: число из конца раздела (за пределом SECTION_TEXT_LIMIT) и числа словами
    # («Günde iki kez» → «2 раза») в блоках памяти отправляли всё описание на модерацию.
    usage_ru = "Способ применения: 2 раза в день."
    warning_ru = "Предупреждения: Не давать детям младше 15 лет. Не применять при заболеваниях сердца."
    description = f"<p>SOLGAR — пищевая добавка.</p><p>{usage_ru}</p><p>{warning_ru}</p><p>{sc.DISCLAIMER['ru']}</p>"
    long_text = "Ürün Bilgisi:\n" + "Bilgi. " * 400 + "\nUyarılar:\n15 yaşından küçüklerde kullanmayınız."
    supplement = {"brand": "SOLGAR", "memory_texts": {"ru": [usage_ru, warning_ru], "en": []}}
    log = SimpleNamespace(
        raw_llm_response={"rule_content": {"supplement": supplement}},
        input_data={"name": "SOLGAR TAKVIYE EDICI GIDA", "attributes": {"source_tabs": {"product_info": {"text": long_text}}}},
        extracted_attributes={},
        generated_title="",
        generated_description=description,
    )

    assert sc.log_problems(log) == {}
    supplement["memory_texts"] = {}
    assert set(sc.log_problems(log)["description"]) == {"supplement_health_claim", "supplement_unsourced_number"}


def _card_answer():
    return {
        "brand": "HERBALAND",
        "brand_ru": "Хербаленд",
        "product": {"ru": "Бузина, цинк и витамин C", "en": "Elderberry, Zinc and Vitamin C"},
        "ingredients": [],
        "serving": {"ru": "1 штука в день", "en": "1 piece a day"},
        "description": {"ru": ["HERBALAND — жевательные пастилки с бузиной."], "en": ["HERBALAND is chewable gummies with elderberry."]},
    }


@pytest.mark.django_db
def test_supplement_card_gets_memory_blocks_and_model_is_told_not_to_retell_them():
    input_data = {
        "name": "HERBALAND SAMBUZINC GUMMIES TAKVIYE EDICI GIDA 60 tablet",
        "attributes": {"source_tabs": {"product_info": {"text": PRODUCT_INFO}, "ingredients": {"text": INGREDIENTS}}},
    }
    card_call = {"content": _card_answer(), "tokens": {"prompt": 900, "completion": 300}, "cost_usd": 0.0003}

    def generate_content(**kwargs):
        if kwargs["system_prompt"].startswith(sm.LINE_SYSTEM_PROMPT):
            return {"content": _answer_for(kwargs["user_prompt"]), "tokens": {"prompt": 100, "completion": 80}, "cost_usd": 0.0002}
        return card_call

    llm = SimpleNamespace(generate_content=Mock(side_effect=generate_content))
    result = sc.run_supplement_content(SimpleNamespace(pk=None, name=input_data["name"]), input_data, llm)

    card_prompt = json.loads(llm.generate_content.call_args.kwargs["user_prompt"].split("\n", 1)[1])
    assert card_prompt["program_blocks"] == ["Состав", "Способ применения", "Предупреждения", "Хранение"]
    description = result["content"]["ru"]["generated_description"]
    assert "<p>Состав: вода, подсластитель (эритрит, ксилит), L-аскорбиновая кислота (витамин C)," in description
    assert "<p>Способ применения: По 1 штуке в день, разжёвывая.</p>" in description
    assert result["content"]["en"]["generated_description"].count("<p>") == 6
    assert result["cost_usd"] == pytest.approx(0.0009)  # карточка + 3 запроса перевода частей
    assert result["rule_content"]["supplement"]["memory_texts"]["ru"][1] == "Способ применения: По 1 штуке в день, разжёвывая."
    assert result["rule_content"]["description_source"] == "llm+memory"
    assert result["rule_content"]["supplement"]["memory"]["translated"] == 8
    # Есть «Способ применения» — в SEO обещается инструкция на русском (SEO-ядро 07.11.2026).
    assert "Инструкция на русском" in result["content"]["ru"]["seo_description"]


def test_pack_count_is_not_a_composition_paragraph():
    # GONAMAX 7623, пилот 4 на проде: модель написала «Состав: 30 капсул.»
    assert sc.clean_paragraph("Состав: 30 капсул.") == ""
    assert sc.clean_paragraph("Ingredients: 30 capsules.") == ""
    assert sc.clean_paragraph("Состав: 30 мг цинка.") == "Состав: 30 мг цинка."


@pytest.mark.parametrize(
    "text, expected",
    [
        # Ревью #332, п. 1: «Her …» с дозой — способ применения, заголовок — только «Her 1 ölçekte (10 g) ;».
        ("Kullanım Şekli:\nHer sabah 1 kapsül.", {"usage": ["Her sabah 1 kapsül."]}),
        ("Kullanım Şekli:\nHer öğünde 1 tablet.", {"usage": ["Her öğünde 1 tablet."]}),
        ("Kullanım Şekli:\nHer yemekten sonra 1 kapsül.", {"usage": ["Her yemekten sonra 1 kapsül."]}),
        # П. 2: «;» в конце — не повод выбрасывать дозу.
        ("Kullanım Şekli:\nYetişkinler için günde 2 kapsül;\nÇocuklar için günde 1 kapsül.",
         {"usage": ["Yetişkinler için günde 2 kapsül.", "Çocuklar için günde 1 kapsül."]}),
        # П. 3: доза ложками, граммами, каплетами, числительными — блок не скрывается.
        ("Kullanım Şekli:\n1 yemek kaşığı alınır.", {"usage": ["1 yemek kaşığı alınır."]}),
        ("Kullanım Şekli:\n2 ölçü kaşığı suya karıştırılarak alınır.", {"usage": ["2 ölçü kaşığı suya karıştırılarak alınır."]}),
        ("Kullanım Şekli:\n30 gram su ile karıştırılarak tüketilir.", {"usage": ["30 gram su ile karıştırılarak tüketilir."]}),
        ("Kullanım Şekli:\n1 kaplet su ile alınır.", {"usage": ["1 kaplet su ile alınır."]}),
        # П. 9: «fayda/zarar değerlendirmesi» — предупреждение, не заявление о пользе.
        ("Uyarılar:\nHamilelik döneminde fayda/zarar değerlendirmesi doktor tarafından yapılmalıdır.",
         {"warnings": ["Hamilelik döneminde fayda/zarar değerlendirmesi doktor tarafından yapılmalıdır."]}),
        # Желательное: «•» как разделитель, голое «Kapsül» — компонент.
        ("Ürün Bileşimi:\n• Vitamin C • Çinko • Vitamin D3", {"composition": ["Vitamin C", "Çinko", "Vitamin D3"]}),
        ("Ürün Bileşimi:\nBalık yağı, Kapsül", {"composition": ["Balık yağı", "Kapsül"]}),
    ],
)
def test_review_332_parsing_keeps_real_usage_warnings_and_components(text, expected):
    assert sm.section_parts({"product_info": text}) == expected


@pytest.mark.parametrize(
    "source, ru, problems",
    [
        # Ревью #332, п. 10: латынь строчными как есть — верно.
        ("lacticaseibacillus rhamnosus GG", "lacticaseibacillus rhamnosus GG", []),
        ("lactiplantibacillus plantarum 299v", "lactiplantibacillus plantarum 299v", []),
        ("akkermansia muciniphila", "akkermansia muciniphila", []),
        ("serenoa repens", "serenoa repens", []),
        ("ascophyllum nodosum", "ascophyllum nodosum", []),
        ("l. reuteri", "l. reuteri", []),
        # Обрывок распознавания и турецкое как есть — нет.
        ("kcenzim 010", "kcenzim 010", ["ru_untranslated"]),
        ("papatya ekstresi", "papatya ekstresi", ["ru_untranslated"]),
        # Желательное: «1 мерная ложка» после «принимать».
        ("Günde 1 ölçek alınır", "Принимать 1 мерная ложка в день", ["ru_grammar"]),
        ("Günde 1 ölçek alınır", "Принимать по 1 мерной ложке в день", []),
    ],
)
def test_review_332_line_problems(source, ru, problems):
    assert [p for p in sm.line_problems(source, ru, ru) if p in ("ru_untranslated", "ru_grammar")] == problems


def test_review_332_card_wording():
    # П. 4: исправления транслита — только в RU; «халяль» в начале фразы — с заглавной.
    assert "HELAL" not in sc.build_description(["HELAL certified capsules."], "en")
    assert "халяль" not in sc.build_description(["HELAL certified capsules."], "en")
    assert sc.clean_paragraph("HELAL сертификат.") == "Халяль сертификат."
    # Желательное: порядок слов соли, α-токоферол.
    assert sc.clean_paragraph("Содержит магний ситрат.") == "Содержит цитрат магния."
    assert sc.clean_paragraph("Магний цитрат 300 мг.") == "Цитрат магния 300 мг."
    assert sc.clean_paragraph("DL-a-токоферол ацетат.") == "DL-α-токоферол ацетат."
    assert sc.clean_paragraph("Ingredients: 60 softgels.") == ""
    # П. 5: фраза со своим словом («утром») — не повтор фразы с дозой в скобках.
    blocks = sm.SupplementBlocks(
        ru={"usage": ["Взрослым по 1 капсулу в день утром во время еды.",
                      "Взрослым по 1 капсулу (500 мг) в день во время еды."]},
        en={"usage": ["Adults: 1 capsule a day in the morning with food.", "Adults: 1 capsule (500 mg) a day with food."]},
    )
    assert "утром" in sc.memory_block_texts(blocks, "ru")[0]
    # П. 6: капсула ↔ таблетка — только в способе применения и не у наборов с обеими формами.
    blocks = sm.SupplementBlocks(
        ru={"composition": ["желатин (оболочка капсулы)"], "usage": ["1 капсула в день."],
            "warnings": ["Не принимать одновременно с капсулами железа."]},
        en={"composition": ["gelatin (capsule shell)"], "usage": ["1 capsule a day."],
            "warnings": ["Do not take with iron capsules."]},
    )
    ru = sc.memory_block_texts(blocks, "ru", "DYNAVIT BIOTIN TAKVIYE EDICI GIDA 100 tablet")
    assert ru[0] == "Состав: желатин (оболочка капсулы)."
    assert ru[1] == "Способ применения: 1 таблетка в день."
    assert "капсулами железа" in ru[2]
    assert sc.memory_block_texts(blocks, "en", "DYNAVIT BIOTIN 100 tablet")[0] == "Ingredients: gelatin (capsule shell)."
    mixed = sm.SupplementBlocks(ru={"usage": ["1 капсула утром и 1 таблетка вечером."]},
                                en={"usage": ["1 capsule in the morning and 1 tablet in the evening."]})
    assert sc.memory_block_texts(mixed, "ru", "OMEGA 3 30 KAPSUL + MULTIVITAMIN 30 TABLET") == [
        "Способ применения: 1 капсула утром и 1 таблетка вечером."
    ]
    assert sc.memory_block_texts(mixed, "ru", "SET 30 TABLET 30 KAPSUL") == [
        "Способ применения: 1 капсула утром и 1 таблетка вечером."
    ]
    # П. 8: модели подсказываются только вещества, не «для беременных» и «для энергии».
    hints = sc._section_glossary({"warnings": "Hamile ve emziren anneler, çocuklar kullanmamalıdır. Enerji. Ahududu aroması."})
    assert set(hints) == {"AHUDUDU"}
    # Желательное: «Dil altına» раздельно.
    assert "dil altina" in supplement_glossary.found_terms("Dil altına 1 puf")


@pytest.mark.parametrize(
    "source, ru, en, problems",
    [
        # Пилот 5 на проде 10.11.2026: переводы памяти и модели с ошибкой по словарю.
        ("Ayva suyu", "Яблочный сок", "Apple juice", ["supplement_ingredient_mistranslated"]),
        ("Ayva suyu", "Айвовый сок", "Quince juice", []),
        ("Doğası değiştirilmiş kollajen tip II", "Нативный коллаген типа II", "Native type II collagen",
         ["supplement_ingredient_mistranslated"]),
        ("Doğası değiştirilmiş kollajen tip II", "Денатурированный коллаген типа II", "Denatured type II collagen", []),
        ("Stevya Gluten", "Stevya Gluten", "Stevya Gluten", ["supplement_ingredient_mistranslated"]),
        ("Kediotu Kökü Ekstresi", "Экстракт корня кедиотуа", "Valerian root extract",
         ["supplement_ingredient_mistranslated", "ru_untranslated"]),
        ("Kediotu Kökü Ekstresi", "Экстракт корня валерианы", "Valerian root extract", []),
        ("Ferrik sodyum EDTA", "Феррик натрия ЭДТА", "Ferric sodium EDTA",
         ["supplement_ingredient_mistranslated", "ru_untranslated"]),
        ("Ferrik sodyum EDTA", "Натрия железа (III) ЭДТА", "Ferric sodium EDTA", []),
        # PHYTORELIEF JUNIOR 7838: «12er» детям — опечатка «1-2'şer», источник подозрителен.
        ("4-10 yaş arası çocuklar için günde 3 defa 12er çiğnenebilir form kullanılması önerilir.",
         "Детям 4–10 лет — по 12 жевательных форм 3 раза в день.", "Children 4–10: 12 chewables 3 times a day.",
         ["dose_suspicious"]),
        ("Günde 3 defa 1-2'şer tablet alınız.", "По 1–2 таблетки 3 раза в день.", "1–2 tablets 3 times a day.", []),
        ("Günde 2 defa 10'ar damla alınız.", "По 10 капель 2 раза в день.", "10 drops twice a day.", []),
    ],
)
def test_pilot5_line_problems(source, ru, en, problems):
    found = sm.line_problems(source, ru, en)
    assert [p for p in found if p in (*sm.LINE_PROBLEMS, *sm.SOURCE_PROBLEMS)] == problems


def test_pilot5_composition_parsing():
    # VENATURA 9422: невидимый пробел после точки давал второй «холекальциферол».
    text = "İçindekiler: Zeytinyağı, Kolekalsiferol.\nİçindekiler: Zeytinyağı, Kolekalsiferol. ​"
    assert sm.section_parts({"product_info": text})["composition"] == ["Zeytinyağı", "Kolekalsiferol"]
    # VENATURA 7978: фраза в кавычках после последнего компонента — не компонент.
    text = ("İçindekiler: Saf su, Stevya (Stevia rebaudiana). “4-10 yaş grubu çocukların kullanımına uygundur.”")
    assert sm.section_parts({"product_info": text})["composition"] == ["Saf su", "Stevya (Stevia rebaudiana)"]
    # Кавычки в названии компонента остаются.
    text = "İçindekiler: Maltodekstrin, “Tip II” kollajen"
    assert sm.section_parts({"product_info": text})["composition"] == ["Maltodekstrin", "“Tip II” kollajen"]


@pytest.mark.django_db
def test_pilot5_cut_component_keeps_composition_out():
    # OSENDE 7992: «Kalsiyum L-Askorbat, Hidroksi» — оборванный компонент, на карточке было «… Гидрокси.».
    blocks, _usage = sm.translate_blocks({"product_info": "İçindekiler: Kalsiyum L-Askorbat, Hidroksi"}, None)
    assert blocks.stats["fragments"] == ["Hidroksi"] and "composition" in blocks.stats["incomplete_blocks"]


def test_pilot5_card_wording_and_translit():
    # OTAVIT 7869, IMUNEKS 7912: числительное в роде.
    assert sc.clean_paragraph("Один капля содержит 25 мкг.") == "Одна капля содержит 25 мкг."
    assert sc.clean_paragraph("Два таблетки содержат 1056 GDU.") == "Две таблетки содержат 1056 GDU."
    assert sc.clean_paragraph("Два жевательные таблетки в день.") == "Две жевательные таблетки в день."
    assert sc.clean_paragraph("Один капсульный блистер, два раза в день.") == "Один капсульный блистер, два раза в день."
    # Транслит в описании модели: «джели», «в тек одноразовых саше», «Феррик», «кадына» — на модерацию.
    for text in ("Каждая джель упакована отдельно.", "в форме джелли", "Порошок в тек одноразовых саше.",
                 "Феррик натрия ЭДТА.", "Экстракт кадыны."):
        assert sm.TRANSLIT_RE.search(text), text
    for text in ("Жевательное желе.", "Желатиновая капсула.", "Текст на упаковке."):
        assert not sm.TRANSLIT_RE.search(text), text
    # Модели подсказывается «лютеин» при опечатке источника «glutein» и папоротник вместо «плаунка».
    hints = sc._section_glossary({"product_info": "Kapsül multivitamin, mineral, glutein ve omega-3. Löykotomos Eğreltisi"})
    assert {"GLUTEIN", "LOYKOTOMOS"} <= set(hints)


def test_pilot5_source_page_of_other_product():
    # 9491: по ссылке VITASENT — страница «Velavit V-Colostrum Lozenges 15 Pastil».
    name = "VITASENT EFF C1000 ORANGE PORTAKAL AROMALI EFERVESAN TABLET 20 tablet"
    other = {"product_info": "Velavit V-Colostrum Lozenges 15 Pastil\nColostrum, Zencefil ve Zerdeçal İçeren Pastil."}
    assert sc.source_page_mismatch(name, other)
    # Своя страница: слово названия слитно («Promen K» — PROMENK), фасовка другая, первая строка — подпись.
    assert not sc.source_page_mismatch("PROMENK SASE 30 saşe", {"product_info": "Neupharma Promen K 30 Saşe"})
    assert not sc.source_page_mismatch("REVOMIX MEN MULTIVITAMIN KAPSUL 60 kapsül", {"product_info": "Revomix Men 30 Kapsül"})
    assert not sc.source_page_mismatch("IMUNEKS PLUS KAPSUL 30 kapsül", {"product_info": "Ürün Açıklaması\nİmuneks"})
    assert not sc.source_page_mismatch("NATURES BOUNTY LUTEIN 50 kapsül", {"product_info": "Lutein 6 mg"})
    log = SimpleNamespace(
        raw_llm_response={"rule_content": {"supplement": {"brand": "VITASENT"}}},
        input_data={"name": name, "attributes": {"source_tabs": {"product_info": {"text": other["product_info"]}}}},
        extracted_attributes={}, generated_title="", generated_description="<p>Шипучие таблетки.</p>",
    )
    assert "supplement_source_mismatch" in sc.log_problems(log)["description"]


@pytest.mark.parametrize(
    "source, ru, en, problems",
    [
        # Волна 1 на проде 10.11.2026: «tercihen yemek zamanı» — во время еды, в памяти было «после еды» (SOLGAR).
        ("Yetişkinler için, tercihen yemek zamanı, günde bir (1) kapsül",
         "Для взрослых, предпочтительно после еды, 1 капсула в день.",
         "For adults, preferably after a meal, 1 capsule a day.", ["meal_timing_mistranslated"]),
        ("Yetişkinler için, tercihen yemek zamanı, günde bir (1) kapsül",
         "Для взрослых, предпочтительно во время еды, 1 капсула в день.",
         "For adults, preferably with a meal, 1 capsule a day.", []),
        ("Günde 1 tablet yemekle birlikte alınız.", "По 1 таблетке в день вместе с едой.", "1 tablet a day with food.", []),
        ("Günde 1 tablet yemeklerden sonra alınız.", "По 1 таблетке в день после еды.", "1 tablet a day after meals.", []),
        # Растения и меры словаря.
        ("Göz otu ekstresi", "Экстракт говяжьего глаза", "Eyebright extract", ["supplement_ingredient_mistranslated"]),
        ("Su teresi ekstresi", "Экстракт кресс-салата водяного", "Watercress extract", []),
        ("Günde 1 tatlı kaşığı", "По 1 чайной ложке в день", "1 dessert spoon a day", ["supplement_ingredient_mistranslated"]),
        ("Kimyon (Cuminum cyminum) Sabit Yağı", "Тмин (Cuminum cyminum) — жирное масло", "Cumin (Cuminum cyminum) fixed oil",
         ["supplement_ingredient_mistranslated"]),
    ],
)
def test_wave1_line_problems(source, ru, en, problems):
    found = sm.line_problems(source, ru, en)
    assert [p for p in found if p in (*sm.LINE_PROBLEMS, *sm.SOURCE_PROBLEMS)] == problems


def test_wave1_composition_headers_phrases_and_markers():
    # Заголовки таблиц вместо компонентов: «Состав: Активные ингредиенты.» (11434), «Таблица состава продукта» (10311).
    for header in ("Aktif İçerikler", "Ürün İçerik Tablosu, Aktif İçerikler", "Etkin Maddeler", "İçerik Adı",
                   "Beslenme Referans Değeri"):
        assert "composition" not in sm.section_parts({"product_info": f"İçindekiler: {header}"}), header
    # Фраза этикетки вместо компонента; компоненты рядом остаются.
    text = "İçindekiler: Propolis ekstraktı, saf su, tatlandırıcı ve renklendirici içermez"
    assert sm.section_parts({"product_info": text})["composition"] == ["Propolis ekstraktı", "saf su"]
    text = "İçindekiler: Ekinezya, Biotin, Zarbee’s Wellness Bal ile tatlandırılmıştır"
    assert sm.section_parts({"product_info": text})["composition"] == ["Ekinezya", "Biotin"]
    # «İçindekiler:» внутри первого компонента — «Состав: Состав: …» (9543).
    text = "Ürün Bileşimi:\nİçindekiler: Balık yağı, Zeytinyağı"
    assert sm.section_parts({"product_info": text})["composition"] == ["Balık yağı", "Zeytinyağı"]
    # Маркеры списка в предупреждениях (9835).
    text = "Uyarılar:\n- Tavsiye edilen günlük porsiyonu aşmayınız.\n- Takviye edici gıdalar normal bir beslenmenin yerine geçmez."
    assert all(not item.startswith("-") for item in sm.section_parts({"product_info": text})["warnings"])


def test_wave1_card_checks():
    # Опасные дозы: % нормы вместо мкг (21248), опечатка «mg» у селена (10220); медь 1000 мкг рядом с D3 — нет.
    assert sc.dose_suspicious("<p>В одном саше 1000 мг кальция, 500 мкг (1000 МЕ) витамина D и 15 мг цинка.</p>")
    assert sc.dose_suspicious("<p>В таблетке витамин C 1000 мг, селен 55 мг и цинк 10 мг.</p>")
    assert not sc.dose_suspicious("<p>Кальций 800 мг, витамин D3 10 мкг, медь 1000 мкг, селен 50 мкг.</p>")
    assert not sc.dose_suspicious("<p>Витамин D3 25 мкг (1000 МЕ), селенит натрия 0,1 мг.</p>")
    # Набор другой марки по ссылке (10251) и опечатка своей страницы (9688).
    assert sc.source_page_mismatch(
        "VITASENT KERATIN WITH BIOTIN 60 tablet", {"product_info": "Velavit Viva BRNX 60 Tablet ve Viva CLRX HEDİYE"}
    )
    assert not sc.source_page_mismatch(
        "NBTLIFE METHYLIFE TAKVIYE EDICI GIDA 30 kapsül", {"product_info": "NBT İlaç Methllife Takviye Edici Gıda 30 Kapsül"}
    )
    assert not sc.source_page_mismatch(
        "MAGNIMORE PLUS TAKVIYE EDICI GIDA 30 tablet", {"product_info": "Sabah öğünden 2 saat sonra 1 tablet alınız."}
    )
    # Род «саше», транслит «портакал».
    assert sc.clean_paragraph("Одна саше в день. Каждый саше содержит 5 г.") == "Одно саше в день. Каждое саше содержит 5 г."
    assert sm.TRANSLIT_RE.search("со вкусом портакала (апельсина)")


def _judge_client(answer=None, exc=None):
    class Messages:
        calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            if exc:
                raise exc
            usage = SimpleNamespace(input_tokens=1000, cache_read_input_tokens=0, cache_creation_input_tokens=0,
                                    output_tokens=200)
            return SimpleNamespace(stop_reason="end_turn", usage=usage,
                                   content=[SimpleNamespace(type="text", text=json.dumps(answer))])

    return SimpleNamespace(model="claude-haiku-5-5", client=SimpleNamespace(messages=Messages()))


def test_supplement_judge_flags_only_confident_findings_and_fails_closed():
    from apps.ai.services import supplement_judge as sj

    answer = {"problems": [
        {"kind": "перевод", "quote": "после еды", "source": "yemek zamanı", "error": "во время еды", "confidence": 4},
        {"kind": "стиль", "quote": "x", "source": "y", "error": "z", "confidence": 5},
    ]}
    client = _judge_client(answer)
    result = sj.judge("SOLGAR X 30 kapsül", {"product_info": "Tercihen yemek zamanı"},
                      "<p>Принимать после еды.</p><p>Дисклеймер.</p>", skip=("Дисклеймер.",), client=client)
    assert [p["kind"] for p in result["problems"]] == ["перевод"] and sj.flagged(result)
    request = client.client.messages.calls[-1]
    # Только Claude с адаптивными размышлениями и схемой ответа; дисклеймер судье не показывается.
    assert request["thinking"] == {"type": "adaptive"} and request["output_config"]["format"]["type"] == "json_schema"
    assert "Дисклеймер" not in request["messages"][0]["content"]
    assert result["cost_usd"] == round((1000 * 0.10 + 200 * 0.50) / 1_000_000, 6)
    # Сомнение модели (confidence 1) — не на модерацию; ошибка запроса — на модерацию.
    low = sj.judge("X", {}, "<p>Текст.</p>", client=_judge_client({"problems": [
        {"kind": "число", "quote": "a", "source": "b", "error": "c", "confidence": 1}]}))
    assert not sj.flagged(low)
    import anthropic

    failed = sj.judge("X", {}, "<p>Текст.</p>", client=_judge_client(exc=anthropic.APIConnectionError(request=None)))
    assert "error" in failed and sj.flagged(failed)
    assert not sj.flagged(None) and not sj.flagged({"problems": []})


def test_log_problems_flag_judge_findings():
    def log(judge):
        return SimpleNamespace(
            raw_llm_response={"rule_content": {"supplement": {"brand": "SOLGAR", "judge": judge}}},
            input_data={"name": "SOLGAR X 30 kapsül"}, extracted_attributes={}, generated_title="",
            generated_description="<p>SOLGAR — капсулы.</p>",
        )
    flagged = {"problems": [{"kind": "перевод", "quote": "a", "source": "b", "error": "c", "confidence": 3}]}
    assert "supplement_judge" in sc.log_problems(log(flagged))["description"]
    assert "supplement_judge" not in sc.log_problems(log({"problems": []})).get("description", [])
    assert "supplement_judge" not in sc.log_problems(log(None)).get("description", [])


def test_wave1b_parsing_numbers_phones_free_from_and_tails():
    # Голое число после вещества (12182, 9842) убирается; «Polisorbat 80», «Omega 3», «kcenzim 010» — нет.
    text = "İçindekiler: Feverfew Ekxtraktı 83, Glukozamin Hcl 40, Polisorbat 80, Omega 3, Lactobacillus plantarum 299"
    assert sm.section_parts({"product_info": text})["composition"] == [
        "Feverfew Ekxtraktı", "Glukozamin Hcl", "Polisorbat 80", "Omega 3", "Lactobacillus plantarum 299",
    ]
    # Хвост-фраза после компонента: возраст с цифры (12158), торговая марка в кавычках (12061).
    text = "İçindekiler: Zeytinyağı, Kolekalsiferol. 11 yaş ve üzeri bireylerin kullanımına yöneliktir"
    assert sm.section_parts({"product_info": text})["composition"] == ["Zeytinyağı", "Kolekalsiferol"]
    text = "İçindekiler: D-biotin, Topaklanmayı önleyici (Silikon dioksit.) “Vitamins by DSM – Quali® is a trademark of DSM”"
    assert sm.section_parts({"product_info": text})["composition"] == ["D-biotin", "Topaklanmayı önleyici (Silikon dioksit.)"]
    # Фраза-описание на «-dır» в составе (11717, 10005).
    text = "İçerik: 500 mg Üzüm Çekirdeği Yağı, Sığır jelatini.\nÜzüm çekirdeği yağı, Omega 6 ve Omega 9 yağ asitlerini içeren değerli bir yağdır."
    assert sm.section_parts({"product_info": text})["composition"] == ["500 mg Üzüm Çekirdeği Yağı", "Sığır jelatini"]
    # Телефон службы поддержки и «… içermez» в способе применения (12138, 12151) — не указания.
    text = ("Kullanım Şekli:\nGünde 1 kapsül alınız.\nDetaylı bilgi için; 0312 285 23 24 ve ya 0850 222 33 44 arayınız.\n"
            "Velavit Glutatyon Saşe; soya, maya, süt ürünleri, şeker ve GDO'lu bileşenler içermez.")
    assert sm.section_parts({"product_info": text})["usage"] == ["Günde 1 kapsül alınız."]
    # Маркер «- » посреди строки (9835).
    text = "Muhafaza Koşulları:\nÇocukların erişemeyeceği yerlerde saklayınız. - 25°C altında saklayınız."
    assert all(not item.startswith("-") for item in sm.section_parts({"product_info": text})["storage"])


@pytest.mark.parametrize(
    "source, ru, en, problems",
    [
        ("Günde 1 puf kullanılır.", "1 пуф в день.", "1 puff a day.", ["supplement_ingredient_mistranslated", "ru_untranslated"]),
        ("Günde 1 puf kullanılır.", "1 впрыск в день.", "1 puff a day.", []),
        ("Bifidobacterium bifidum powder", "Bifidobacterium bifidum powder", "Bifidobacterium bifidum powder",
         ["ru_untranslated"]),
        ("11 yaş ve üzeri yetişkin kadınlar günde 1 tablet", "Взрослым и детям от 11 лет женщинам по 1 таблетке в день",
         "Women aged 11 and over: 1 tablet a day", ["ru_grammar"]),
        ("Yetişkin kadınlar günde 1 tablet", "Взрослым женщинам по 1 таблетке в день", "Adult women: 1 tablet a day", []),
    ],
)
def test_wave1b_line_problems(source, ru, en, problems):
    found = sm.line_problems(source, ru, en)
    assert [p for p in found if p in (*sm.LINE_PROBLEMS, *sm.SOURCE_PROBLEMS)] == problems


def test_wave1b_description_checks():
    source = "Her 2 kapsülde: Sitikolin 500 mg"
    assert sc.dose_per_portion_suspicious("<p>Цитиколин 500 мг в одной капсуле.</p>", source)
    assert not sc.dose_per_portion_suspicious("<p>Состав на 2 капсулы: цитиколин 500 мг.</p>", source)
    assert not sc.dose_per_portion_suspicious("<p>Цитиколин 500 мг в одной капсуле.</p>", "Her kapsülde 500 mg")

    def log(blocks):
        return SimpleNamespace(
            raw_llm_response={"rule_content": {"supplement": {"brand": "X", "memory_texts": {"ru": blocks}}}},
            input_data={"name": "X KAPSUL 30 kapsül"}, extracted_attributes={}, generated_title="",
            generated_description="".join(f"<p>{text}</p>" for text in blocks),
        )
    assert "supplement_untranslated" in sc.log_problems(log(["Состав: Bifidobacterium lactis powder, инулин."]))["description"]
    assert "supplement_untranslated" not in sc.log_problems(log(["Состав: Bifidobacterium lactis, инулин."])).get(
        "description", []
    )


def test_wave1c_composition_roles_other_ingredients_and_excipients():
    # «Kıvam arttırıcı; Gliserol (E422)» — назначение склеивается с веществом (NATUWELL 10315).
    text = "İçindekiler: Deiyonize su, Kıvam arttırıcı; Gliserol (E422), Koruyucu; Sodyum benzoat (E211)"
    assert sm.section_parts({"product_info": text})["composition"] == [
        "Deiyonize su", "Kıvam arttırıcı: Gliserol (E422)", "Koruyucu: Sodyum benzoat (E211)",
    ]
    # «Diğer İçerikler» — вспомогательные вещества, не «Состав» (11964).
    text = "İçerik: Metilkobalamin\nDiğer İçerikler: Mikrokristalin Selüloz, Mannitol, Kiraz Aroması"
    parts = sm.section_parts({"product_info": text})
    assert parts["composition"] == ["Metilkobalamin"]
    assert parts["excipients"] == ["Mikrokristalin Selüloz", "Mannitol", "Kiraz Aroması"]
    # Краситель и разрыхлитель оболочки — вспомогательные: список из одних них не «Состав» (10210).
    text = "İçindekiler: Mikrokristalin Selüloz, Kroskarmelloz Sodyum, Titanyum dioksit, Demir oksit"
    parts = sm.section_parts({"product_info": text})
    assert "composition" not in parts and len(parts["excipients"]) == 4


def test_wave1c_olcek_glossary():
    assert "supplement_ingredient_mistranslated" in sm.line_problems(
        "Günde 1 defa 1 ölçek (5 ml).", "1 раз в день 1 мерный стаканчик (5 мл).", "1 measuring cup (5 ml) once a day."
    )
    assert sm.line_problems("Günde 1 defa 1 ölçek (5 ml).", "1 раз в день 1 мерная ложка (5 мл).",
                            "1 scoop (5 ml) once a day.") == []
    assert sm.line_problems("Günde 1 ölçek kabı (10 ml).", "1 мерный стаканчик (10 мл) в день.",
                            "1 measuring cup (10 ml) a day.") == []


def test_wave1d_capsule_order_glossary_and_shot():
    # «Hydroxypropylmethyl Cellulose Bitkisel kapsül» → «Bitkisel kapsül (…)» (12182, 9966); без «bitkisel» — как есть.
    text = "İçindekiler: Ginkgo Ekstraktı, Hydroxypropylmethyl Cellulose Bitkisel kapsül"
    assert sm.section_parts({"product_info": text})["composition"] == [
        "Ginkgo Ekstraktı", "Bitkisel kapsül (Hydroxypropylmethyl Cellulose)",
    ]
    text = "İçindekiler: Ginkgo Ekstraktı, Hidroksipropil metil selüloz"
    assert sm.section_parts({"product_info": text})["composition"] == ["Ginkgo Ekstraktı", "Hidroksipropil metil selüloz"]
    # Словарь: черешня, порошок родиолы, мальтит, пастилка — неверный перевод не принимается, верный — да.
    for source, wrong, right in (
        ("Kiraz Aroması", "Вкус вишни", "Ароматизатор черешни"),
        ("rodiola tozu", "корень родиолы", "порошок родиолы"),
        ("kıvam artırıcı Maltitol", "загуститель Maltitol", "загуститель мальтит"),
        ("Günde 3 defa 1 pastil", "по 1 леденец 3 раза в день", "по 1 пастилке 3 раза в день"),
    ):
        assert "supplement_ingredient_mistranslated" in sm.line_problems(source, wrong, wrong), source
        assert "supplement_ingredient_mistranslated" not in sm.line_problems(source, right, {
            "Kiraz Aroması": "Sweet cherry flavour", "rodiola tozu": "rhodiola powder",
            "kıvam artırıcı Maltitol": "thickener maltitol", "Günde 3 defa 1 pastil": "1 lozenge 3 times a day",
        }[source]), source
    # «1 шот» — транслит; «шоты» в других словах — нет.
    assert sm.TRANSLIT_RE.search("1 шот в день")
    assert not sm.TRANSLIT_RE.search("шотландский виски")
