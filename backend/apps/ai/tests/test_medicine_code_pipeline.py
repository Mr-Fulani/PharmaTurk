"""Лекарства: справочные поля, МНН, название и разделы — кодом и памятью переводов."""

import json
import re
from types import SimpleNamespace

import pytest

from apps.ai.models import AIProcessingLog, AITranslationMemory
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.medicine_memory import (
    BRAND_TOKEN,
    INN_NAMESPACE,
    PARAGRAPH_NAMESPACE,
    items_from_user_prompt,
    normalize_paragraph,
    paragraph_problems,
    split_paragraphs,
    translate_active_ingredient,
)
from apps.ai.services.medicine_reference import (
    meaningful_special_notes,
    neutral_prescription_text,
    translate_reference_field,
    translate_volume,
)
from apps.ai.services.medicine_title import (
    TRUNCATED_TITLE_RE,
    build_medicine_title,
    equivalents_source_name,
    looks_like_source_name,
    medicine_seo_title,
    medicine_source_name,
    paragraph_brand,
    title_with_inn,
)
from apps.ai.services.result_applier import AIResultApplier
from apps.ai.services.semantic_validator import SemanticValidator
from apps.ai.services.translation_memory import lookup, remember
from apps.catalog.models import Category, MedicineProduct

pytestmark = pytest.mark.django_db


def _result(content):
    return {
        "content": content,
        "tokens": {"prompt": 100, "completion": 50, "total": 150},
        "cost_usd": 0.001,
        "processing_time_ms": 5,
    }


class RecordingLLM:
    """Отвечает по типу запроса: карточка, МНН или абзацы инструкции."""

    model = "test-model"

    def __init__(self, card=None, inn=None, paragraphs=None):
        self.card = card or {}
        self.inn = inn or {}
        self.paragraphs = paragraphs or {}
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        system = kwargs["system_prompt"]
        if "МНН" in system or "действующих веществ" in system:
            items = json.loads(kwargs["user_prompt"].split("\n\n", 1)[1])
            return _result({
                "ru": {k: self.inn[v][0] for k, v in items.items() if v in self.inn},
                "en": {k: self.inn[v][1] for k, v in items.items() if v in self.inn},
            })
        if "абзацы" in system:
            items = json.loads(kwargs["user_prompt"].split("\n\n", 1)[1])
            return _result({
                k: {"ru": self.paragraphs[v][0], "en": self.paragraphs[v][1]}
                for k, v in items.items() if v in self.paragraphs
            })
        return _result(self.card)

    def calls_of(self, marker):
        return [call for call in self.calls if marker in call["system_prompt"]]


def _generator(llm):
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.llm = llm
    generator.vector_store = None
    generator.result_applier = AIResultApplier()
    return generator


def test_reference_fields_are_translated_by_dictionary():
    assert translate_reference_field("prescription_type", "Kısıtlanmış Beyaz Reçete") == (
        "Рецептурный препарат с ограничением назначения", "Restricted prescription medicine",
    )
    assert translate_reference_field("prescription_type", "BEYAZ REÇETE")[0] == "Рецептурный препарат"
    assert translate_reference_field("sgk_status", "Bedeli Ödenir") == ("Оплачивается SGK", "Covered by SGK")
    assert translate_reference_field("origin_country", "İMAL")[1] == "Manufactured in Turkey"
    assert translate_reference_field("shelf_life", "24 Ay") == ("24 месяца", "24 months")
    assert translate_reference_field("shelf_life", "36 Ay") == ("36 месяцев", "36 months")
    assert translate_reference_field("administration_route", "İntravenöz/İntramüsküler") == (
        "Внутривенно, внутримышечно", "Intravenous, intramuscular",
    )
    assert translate_reference_field("storage_conditions", "Işıktan Korunması Gereken")[0] == (
        "Хранить в защищённом от света месте"
    )
    # Неизвестное значение не «угадывается»: остаётся исходник.
    assert translate_reference_field("administration_route", "Bilinmeyen yol") is None


def test_volume_is_number_plus_unit_from_form_or_name():
    # Пилот: в MedicineProduct.volume только число, модель дописывала «мл».
    assert translate_volume("20", dosage_form="tablet", name="LASIRIN 20 MG TABLET") == (
        "20 таблеток", "20 tablets",
    )
    assert translate_volume("10", dosage_form="injection", name="X 20 MG/ML 10 AMPUL") == (
        "10 ампул", "10 ampoules",
    )
    # Пилот: «1» → «50 мл» — выдумка; код не берёт единицу из чужого числа.
    assert translate_volume("1", dosage_form="syrup", name="ZINCO SURUP 50 ML") == ("1 шт.", "1 pc")


def test_code_fields_replace_model_values_and_are_not_fact_checked():
    generator = _generator(None)
    input_data = {
        "name": "LASIRIN 20 MG TABLET",
        "dosage_form": "tablet",
        "volume": "20",
        "prescription_type": "Beyaz Reçete",
        "barcode": "8690000000001",
    }
    code_fields = generator._build_medicine_code_fields(input_data, allow_llm=False)
    content = {
        "ru": {"volume": "20 мл", "dosage_form": "таблетки, покрытые плёночной оболочкой"},
        "en": {"volume": "20 ml"},
    }

    generator._apply_medicine_code_fields(content, input_data, code_fields)
    ContentGenerator._apply_medicine_fact_checks(content, input_data, {})

    assert content["ru"]["volume"] == "20 таблеток"
    assert content["en"]["volume"] == "20 tablets"
    assert content["ru"]["dosage_form"] == "Таблетки"
    assert content["ru"]["prescription_type"] == "Рецептурный препарат"
    assert content["attributes"]["barcode"] == "8690000000001"
    assert content["attributes"]["medicine_translation_quality"] == {}


def test_long_dosage_form_translation_is_not_written_to_varchar20():
    # Пилот, товар 283: «value too long for type character varying(20)».
    medicine = MedicineProduct.objects.create(name="MED 283", slug="med-283-dosage-form")
    medicine.refresh_from_db()

    AIResultApplier().apply_to_product(
        medicine.base_product,
        {
            "translations": {
                "ru": {"dosage_form": "таблетки, покрытые плёночной оболочкой"},
                "en": {"dosage_form": "Tablets"},
            }
        },
    )

    assert medicine.translations.get(locale="ru").dosage_form == ""
    assert medicine.translations.get(locale="en").dosage_form == "Tablets"


def test_half_translated_inn_is_rejected_and_not_cached():
    llm = RecordingLLM(inn={"klorfeniramin maleat": ("Клорфенирамин Maleat", "Chlorpheniramine maleate")})

    value, usage = translate_active_ingredient("Klorfeniramin Maleat", llm=llm)

    assert value is None
    assert usage["cost_usd"] == pytest.approx(0.001)
    assert not AITranslationMemory.objects.filter(namespace=INN_NAMESPACE).exists()


def test_inn_is_translated_once_then_taken_from_memory_by_component():
    llm = RecordingLLM(inn={
        "sodyum klorur": ("натрия хлорид", "sodium chloride"),
        "dekstroz": ("декстроза", "dextrose"),
    })

    first, _usage = translate_active_ingredient("Sodyum Klorür + Dekstroz", llm=llm)
    second, usage = translate_active_ingredient("SODYUM KLORÜR", llm=llm)

    assert first == ("Натрия хлорид + Декстроза", "Sodium chloride + Dextrose")
    assert second == ("Натрия хлорид", "Sodium chloride")
    assert usage is None
    assert len(llm.calls) == 1


def test_manual_inn_edit_in_memory_is_applied_to_all_products():
    remember(INN_NAMESPACE, {"klorfeniramin maleat": {"ru": "Хлорфенамин", "en": "Chlorphenamine"}})
    medicines = []
    for index, inn in enumerate(("Klorfeniramin Maleat", "KLORFENIRAMIN MALEAT + Parasetamol")):
        medicine = MedicineProduct.objects.create(
            name=f"INN {index}", slug=f"inn-propagation-{index}", active_ingredient=inn
        )
        medicine.translations.create(locale="ru", active_ingredient="старое")
        medicine.translations.create(locale="en", active_ingredient="old")
        medicines.append(medicine)
    remember(INN_NAMESPACE, {"parasetamol": {"ru": "Парацетамол", "en": "Paracetamol"}})

    entry = AITranslationMemory.objects.get(namespace=INN_NAMESPACE, source_text="klorfeniramin maleat")
    entry.ru_text = "Хлорфенамина малеат"
    entry.save()

    assert medicines[0].translations.get(locale="ru").active_ingredient == "Хлорфенамина малеат"
    assert medicines[1].translations.get(locale="ru").active_ingredient == (
        "Хлорфенамина малеат + Парацетамол"
    )
    assert medicines[1].translations.get(locale="en").active_ingredient == "Chlorphenamine + Paracetamol"


PARA_A = "Doktorunuzun söylediği şekilde günde 2 kez 500 mg kullanınız. " * 4
PARA_B = "Bu ilacı çocukların göremeyeceği yerde saklayınız. " * 3
PARA_C = "Hamilelik döneminde doktorunuza danışınız. " * 3
TRANSLATIONS = {
    PARA_A.strip(): (
        "Принимайте по 500 мг 2 раза в день, как сказал врач. " * 4,
        "Take 500 mg 2 times a day as your doctor told you. " * 4,
    ),
    PARA_B.strip(): (
        "Храните препарат в недоступном для детей месте. " * 3,
        "Keep this medicine out of the reach of children. " * 3,
    ),
    PARA_C.strip(): (
        "Во время беременности проконсультируйтесь с врачом. " * 3,
        "Consult your doctor during pregnancy. " * 3,
    ),
}


def test_paragraphs_from_memory_are_not_sent_to_model_again():
    llm = RecordingLLM(paragraphs={k: (ru.strip(), en.strip()) for k, (ru, en) in TRANSLATIONS.items()})
    generator = _generator(llm)

    first = {"ru": {}, "en": {}}
    generator._translate_medicine_source_sections(
        first, {"usage_instructions": f"{PARA_A}\n{PARA_B}"}, product_id=1
    )
    second = {"ru": {}, "en": {}}
    usage = generator._translate_medicine_source_sections(
        second, {"usage_instructions": f"{PARA_A}\n\n{PARA_C}"}, product_id=2
    )

    paragraph_calls = llm.calls_of("абзацы")
    assert len(paragraph_calls) == 2
    sent = json.loads(paragraph_calls[1]["user_prompt"].split("\n\n", 1)[1])
    assert list(sent.values()) == [PARA_C.strip()]
    assert usage["paragraphs_cached"] == 1
    assert usage["paragraphs_translated"] == 1
    assert second["ru"]["usage_instructions"] == (
        TRANSLATIONS[PARA_A.strip()][0].strip() + "\n\n" + TRANSLATIONS[PARA_C.strip()][0].strip()
    )
    assert AITranslationMemory.objects.filter(namespace=PARAGRAPH_NAMESPACE).count() == 3


def test_paragraph_with_changed_dose_is_not_cached_and_blocks_section():
    wrong = TRANSLATIONS[PARA_A.strip()][0].replace("500 мг", "50 мг")
    llm = RecordingLLM(paragraphs={PARA_A.strip(): (wrong.strip(), TRANSLATIONS[PARA_A.strip()][1].strip())})
    generator = _generator(llm)
    content = {"ru": {}, "en": {}}

    generator._translate_medicine_source_sections(content, {"usage_instructions": PARA_A}, product_id=3)

    quality = content["attributes"]["medicine_translation_quality"]["usage_instructions"]
    assert quality["complete"] is False
    assert quality["fact_mismatch"]
    assert "usage_instructions" not in content["ru"]
    assert len(llm.calls_of("абзацы")) == 2  # один повтор
    assert lookup(PARAGRAPH_NAMESPACE, [PARA_A.strip()]) == {}


BRANDED_RU = f"Не принимайте {BRAND_TOKEN} при аллергии на флурбипрофен и другие обезболивающие. " * 2
BRANDED_EN = f"Do not take {BRAND_TOKEN} if you are allergic to flurbiprofen or other painkillers. " * 2


def _branded(text):
    return f"{text} ağrı kesicilere alerjiniz varsa kullanmayınız. " * 2


def test_brand_is_replaced_by_token_with_turkish_suffixes_and_case():
    assert paragraph_brand("MAJEZIK 100 MG 15 FILM TABLET", "Flurbiprofen") == "MAJEZIK"
    assert paragraph_brand("IBUPROFEN 400 MG 20 TABLET", "İbuprofen") == ""  # вещество, а не бренд
    assert paragraph_brand("AB 5 MG TABLET") == ""
    assert normalize_paragraph("MAJEZİK'in  etkisi; Majezik’i alın; MAJEZIK kullanın", "MAJEZIK") == (
        "{BRAND}'in etkisi; {BRAND}'i alın; {BRAND} kullanın"
    )
    # Гармония гласных: «PAROL'ün», «ZINCO'yu» — тот же ключ, что «MAJEZIK'in», «MAJEZIK'i».
    assert normalize_paragraph("PAROL'ün etkisi, PAROL'ü alın", "PAROL") == "{BRAND}'in etkisi, {BRAND}'i alın"
    assert normalize_paragraph("ZINCO'yu ZINCO'ya ZINCO'da", "ZINCO") == "{BRAND}'i {BRAND}'e {BRAND}'de"
    # Слово со строчной и часть другого слова — не бренд.
    assert normalize_paragraph("grip olursanız GRIPIN alın", "GRIP") == "grip olursanız GRIPIN alın"


def test_same_paragraph_with_different_brands_is_translated_once():
    key = normalize_paragraph(_branded("MAJEZIK'i"), "MAJEZIK")
    assert key == normalize_paragraph(_branded("PAROL'ü"), "PAROL")
    llm = RecordingLLM(paragraphs={key: (BRANDED_RU.strip(), BRANDED_EN.strip())})
    generator = _generator(llm)

    first = {"ru": {}, "en": {}}
    generator._translate_medicine_source_sections(
        first, {"contraindications": _branded("MAJEZIK'i")}, product_id=1, brand="MAJEZIK"
    )
    second = {"ru": {}, "en": {}}
    usage = generator._translate_medicine_source_sections(
        second, {"contraindications": _branded("PAROL'ü")}, product_id=2, brand="PAROL"
    )

    assert len(llm.calls_of("абзацы")) == 1
    assert usage["paragraphs_cached"] == 1
    assert first["ru"]["contraindications"] == BRANDED_RU.strip().replace(BRAND_TOKEN, "MAJEZIK")
    assert first["en"]["contraindications"] == BRANDED_EN.strip().replace(BRAND_TOKEN, "MAJEZIK")
    assert second["ru"]["contraindications"].startswith("Не принимайте PAROL при аллергии")
    assert second["en"]["contraindications"].startswith("Do not take PAROL if")
    entry = AITranslationMemory.objects.get(namespace=PARAGRAPH_NAMESPACE)
    assert entry.source_text == key and BRAND_TOKEN in entry.ru_text


def test_paragraph_without_brand_token_in_answer_is_rejected():
    key = normalize_paragraph(_branded("MAJEZIK'i"), "MAJEZIK")
    ru = BRANDED_RU.replace(BRAND_TOKEN, "Маджезик").strip()
    llm = RecordingLLM(paragraphs={key: (ru, BRANDED_EN.strip())})
    content = {"ru": {}, "en": {}}

    _generator(llm)._translate_medicine_source_sections(
        content, {"contraindications": _branded("MAJEZIK'i")}, product_id=4, brand="MAJEZIK"
    )

    quality = content["attributes"]["medicine_translation_quality"]["contraindications"]
    assert quality["problems"] == ["brand_token_missing"]
    assert "contraindications" not in content["ru"]
    assert lookup(PARAGRAPH_NAMESPACE, [key]) == {}


def test_paragraph_batch_masks_brand_like_regular_processing():
    from apps.ai.services.medicine_paragraph_batch import iter_missing_paragraphs

    for name, slug, suffix in (("MAJEZIK 100 MG 15 FILM TABLET", "batch-majezik", "MAJEZIK'i"),
                               ("PAROL 500 MG 20 TABLET", "batch-parol", "PAROL'ü")):
        MedicineProduct.objects.create(
            name=name, slug=slug,
            external_data={"attributes": {"source_tabs": {"before_use_warnings": {"text": _branded(suffix)}}}},
        )

    assert [paragraph for paragraph, _ in iter_missing_paragraphs()] == [
        normalize_paragraph(_branded("MAJEZIK'i"), "MAJEZIK")
    ]


# Строки, на которые парсер разрезал одно предложение строчным тегом (<b>, <sup>,
# <sub>, <a>), — примеры со страниц ilacfiyati.com.
CUT_SENTENCES = [
    (
        "Somatropine veya NORDITROPIN\n®\n'un içerisindeki herhangi bir bileşene karşı alerjiniz varsa.",
        "Somatropine veya NORDITROPIN®'un içerisindeki herhangi bir bileşene karşı alerjiniz varsa.",
    ),
    ("NORDITROPIN\n'in yiyecek ve içecek ile kullanılması", "NORDITROPIN'in yiyecek ve içecek ile kullanılması"),
    ("EPORON\n®\ntedavisinin gerekli olduğuna karar verebilir.", "EPORON® tedavisinin gerekli olduğuna karar verebilir."),
    ("1. EPORON\n®\nNEDİR VE NE İÇİN KULLANILIR?", "1. EPORON® NEDİR VE NE İÇİN KULLANILIR?"),
    ("MON.LUTEC\nile radyoaktif olarak işaretlenen ilacın uygulanması", "MON.LUTEC ile radyoaktif olarak işaretlenen ilacın uygulanması"),
    ("DERHAL\ndoktorunuza başvurunuz:", "DERHAL doktorunuza başvurunuz:"),
    ("A\nşağıdakilerden biri olursa kullanmayı durdurunuz.", "Aşağıdakilerden biri olursa kullanmayı durdurunuz."),
    ("Kanda B\n12\nvitamini konsantrasyonunu azaltabilir.", "Kanda B12 vitamini konsantrasyonunu azaltabilir."),
    ("günde bir defa 150 mg/m\n2\n'ye kadar", "günde bir defa 150 mg/m2'ye kadar"),
    (
        "Ayrıca karşılaştığınız yan etkileri\nwww.titck.gov.tr\nsitesinde yer alan ikona tıklayarak bildiriniz.",
        "Ayrıca karşılaştığınız yan etkileri www.titck.gov.tr sitesinde yer alan ikona tıklayarak bildiriniz.",
    ),
    ("25\no\nC altındaki oda sıcaklığında saklayınız.", "25o C altındaki oda sıcaklığında saklayınız."),
    ("Bu durum sizin için geçerliyse\n, doktorunuza danışınız.", "Bu durum sizin için geçerliyse, doktorunuza danışınız."),
]

# Строки — отдельные абзацы: списки, таблица доз, нумерация, заголовки, реквизиты.
KEPT_LINES = [
    "Yaygın:\nbaş ağrısı\nbulantı\nishal",
    "Yaygın olmayan yan etkiler\ngöz kapağında kaşıntı\ngörme bozuklukları",
    "AUGMENTİN ES miktarı\n8\nGünde iki kez 3 ml\n12\nGünde iki kez 4,5 ml",
    "1.\nEPORON nedir ve ne için kullanılır?\n2.\nEPORON'u kullanmadan önce dikkat edilmesi gerekenler",
    "2. EPORON'U KULLANMADAN ÖNCE DİKKAT EDİLMESİ GEREKENLER\nEPORON'u aşağıdaki durumlarda KULLANMAYINIZ",
    "Ruhsat sahibi:\nAbdi İbrahim İlaç San. ve Tic. A.Ş.\nReşitpaşa Mah. Eski Büyükdere Cad. No:4\n34467 Maslak / İstanbul",
    "Bu ilacı kullanmadan önce bu kullanma talimatını dikkatlice okuyunuz.\n"
    "Bu ilaç kişisel olarak sizin için reçete edilmiştir, başkalarına vermeyiniz.",
    "Ambalajında saklayınız.\n25\nderecenin altında tutunuz.",
    # Через пустую строку не клеится.
    "Somatropine veya NORDITROPIN\n\n'un içerisindeki herhangi bir bileşene karşı alerjiniz varsa.",
    # Пункты списков и строки таблиц без знака в конце (каталог 22.10.2026).
    "böbrek fonksiyonunda azalma veya böbrek hastalığı\nkalp hastalığı",
    "mide ya da onikiparmak bağırsağı ülseriniz varsa veya geçirdiyseniz\nbronşiyal astımınız varsa",
    "kortikosteroid adı verilen ilaçları kullanıyorsanız (prednisolon veya deksametazon gibi)\nkanseriniz varsa",
    "bakteriyel enfeksiyonlar için antibiyotikler-klaritromisin gibi\nmantar enfeksiyonları için ilaçlar-posakonazol gibi",
    "PALİGİS'in yiyecek ve içecek ile kullanılması\nPALİGİS kullanırken alkol almayınız.",
    "Vitamin B12\nmcg",
    "-10 ya da daha az : 0\n-11-20 : 1",
]

# Предложение, разрезанное самим сайтом на пункты списка или строки таблицы (перенос
# из PDF): «…serebral</li><li>vazokonstriksiyon…». Примеры — из частей 3–5 Batch-перевода.
SITE_CUT_SENTENCES = [
    (
        "Aşağıda belirtilen durumlardan herhangi biri sizin için söz konusuysa, tedaviniz doktorunuz\n"
        "tarafından dikkatli bir şekilde düzenlenmelidir:",
        "Aşağıda belirtilen durumlardan herhangi biri sizin için söz konusuysa, tedaviniz doktorunuz "
        "tarafından dikkatli bir şekilde düzenlenmelidir:",
    ),
    (
        "Mide yanması ve kusma gibi belirtilerin tedavisinde (Gastro-özofajiyal reflü hastalığının\n"
        "semptomatik tedavisinde) önerilen tedavi dozu günde bir kez 20 mg esomeprazoldur.",
        "Mide yanması ve kusma gibi belirtilerin tedavisinde (Gastro-özofajiyal reflü hastalığının "
        "semptomatik tedavisinde) önerilen tedavi dozu günde bir kez 20 mg esomeprazoldur.",
    ),
    (
        "Perindopril, anjiyotensin dönüştürücü enzim inhibitörü (ADE) adı verilen ilaçlar\nsınıfındandır.",
        "Perindopril, anjiyotensin dönüştürücü enzim inhibitörü (ADE) adı verilen ilaçlar sınıfındandır.",
    ),
    (
        "Eğer romatoid artritiniz varsa ve HUMIRA tedavisiyle birlikte metotreksat\n"
        "almıyorsanız, doktorunuz haftada bir 40 mg adalimumab verebilir.",
        "Eğer romatoid artritiniz varsa ve HUMIRA tedavisiyle birlikte metotreksat "
        "almıyorsanız, doktorunuz haftada bir 40 mg adalimumab verebilir.",
    ),
    (
        "160 mg'lık (bir günde 40\nmg'lık dört enjeksiyon ya da birbirini izleyen iki gün\n"
        "boyunca her gün 40 mg'lık iki enjeksiyon) başlangıç dozunu takiben",
        "160 mg'lık (bir günde 40 mg'lık dört enjeksiyon ya da birbirini izleyen iki gün "
        "boyunca her gün 40 mg'lık iki enjeksiyon) başlangıç dozunu takiben",
    ),
    ("6 yaşından büyük, vücut ağırlığı 15\n-30 kg arasında çocuklar ve ergenler",
     "6 yaşından büyük, vücut ağırlığı 15-30 kg arasında çocuklar ve ergenler"),
    ("Bundan sonra normal doz iki haftada bir uygulanan 40\nmg'dır.",
     "Bundan sonra normal doz iki haftada bir uygulanan 40 mg'dır."),
    ("Gebelik ve\nemzirme", "Gebelik ve emzirme"),
    ("Üründe bozukluk fark ederseniz ilacı\nkullanmayınız.", "Üründe bozukluk fark ederseniz ilacı kullanmayınız."),
]


@pytest.mark.parametrize("text, paragraph", CUT_SENTENCES)
def test_line_cut_by_inline_tag_is_glued_to_its_sentence(text, paragraph):
    assert split_paragraphs(text) == [paragraph]


@pytest.mark.parametrize("text", KEPT_LINES)
def test_regular_lines_stay_separate_paragraphs(text):
    assert split_paragraphs(text) == re.split(r"(\n+)", text)


@pytest.mark.parametrize("text, paragraph", SITE_CUT_SENTENCES)
def test_sentence_cut_by_site_markup_is_glued(text, paragraph):
    assert split_paragraphs(text) == [paragraph]


def test_list_followed_by_its_sentence_ending_glues_only_the_ending():
    text = (
        "Burun tıkanması, akıntısı veya kaşıntısı\nHapşırma\nGözlerde sulanma, kaşıntı veya kızarıklık\n"
        "gibi alerjik belirtilerin tedavisinde kullanılır."
    )

    assert split_paragraphs(text)[::2] == [
        "Burun tıkanması, akıntısı veya kaşıntısı",
        "Hapşırma",
        "Gözlerde sulanma, kaşıntı veya kızarıklık gibi alerjik belirtilerin tedavisinde kullanılır.",
    ]


def test_glued_sentence_gets_one_memory_key_with_canonical_suffix():
    paragraph = split_paragraphs(CUT_SENTENCES[0][0])[0]
    key = "Somatropine veya {BRAND}'in içerisindeki herhangi bir bileşene karşı alerjiniz varsa."
    assert normalize_paragraph(paragraph, "NORDITROPIN") == key
    assert normalize_paragraph("Somatropine veya MAJEZİK'in içerisindeki herhangi bir bileşene karşı "
                               "alerjiniz varsa.", "MAJEZIK") == key
    # Знак ® после бренда в ключ не попадает и суффикс после него приводится к одной форме.
    assert normalize_paragraph("2. EPORON®'U KULLANMADAN ÖNCE", "EPORON") == "2. {BRAND}'i KULLANMADAN ÖNCE"


def test_cut_sentence_is_translated_as_one_paragraph():
    source = "Somatropine veya MAJEZIK\n®\n'in içerisindeki herhangi bir bileşene karşı alerjiniz varsa."
    key = "Somatropine veya {BRAND}'in içerisindeki herhangi bir bileşene karşı alerjiniz varsa."
    llm = RecordingLLM(paragraphs={key: (
        "Если у вас аллергия на соматропин или любой компонент препарата {BRAND}.",
        "If you are allergic to somatropin or any of the ingredients of {BRAND}.",
    )})
    content = {"ru": {}, "en": {}}

    _generator(llm)._translate_medicine_source_sections(
        content, {"contraindications": source}, product_id=5, brand="MAJEZIK"
    )

    calls = llm.calls_of("абзацы")
    assert len(calls) == 1 and items_from_user_prompt(calls[0]["user_prompt"]) == {"1": key}
    assert content["ru"]["contraindications"] == (
        "Если у вас аллергия на соматропин или любой компонент препарата MAJEZIK."
    )


def test_title_template_from_structured_name():
    assert build_medicine_title("MAJEZIK 100 MG 15 FILM TABLET") == {
        "ru": "MAJEZIK 100 мг, таблетки, покрытые плёночной оболочкой, 15 шт.",
        "en": "MAJEZIK 100 mg, film-coated tablets, 15 pcs",
    }
    assert build_medicine_title("ZINCO SURUP 150 ML") == {"ru": "ZINCO, сироп, 150 мл", "en": "ZINCO, syrup, 150 ml"}
    # Незнакомое слово после бренда — шаблон не строится, название даст модель.
    assert build_medicine_title("X 5 MG KARISIM") is None


def test_title_names_active_ingredient_without_salt():
    title = build_medicine_title("UROMAX 0,4 MG MR DEGISTIRILMIS SALIMLI SERT KAPSUL (30 ADET)")
    assert title_with_inn(
        title, "UROMAX 0,4 MG MR DEGISTIRILMIS SALIMLI SERT KAPSUL (30 ADET)",
        ("Тамсулозин гидрохлорид", "Tamsulosin hydrochloride"), "Tamsulosin Hidroklorur",
    ) == {
        "ru": "UROMAX (тамсулозин) 0,4 мг MR, капсулы с модифицированным высвобождением, 30 шт.",
        "en": "UROMAX (tamsulosin) 0.4 mg MR, modified-release hard capsules, 30 pcs",
    }
    name = "ROLASTYM AEROSOL 160 MCG/4,5 MCG SUSPANSIYON ICEREN OLCULU DOZ INHALER (120 DOZ)"
    assert title_with_inn(
        build_medicine_title(name), name,
        ("Формотерол фумарат дигидрат + Будезонид", "Formoterol fumarate dihydrate + Budesonide"),
        "Formoterol Fumarat Dihidrat + Budezonid",
    )["ru"] == "ROLASTYM (формотерол + будезонид) 160 мкг/4,5 мкг, суспензия для ингаляций дозированная, 120 доз"
    # Вещество уже в бренде — не повторяем.
    plain = build_medicine_title("IBUPROFEN 400 MG 20 TABLET")
    assert title_with_inn(plain, "IBUPROFEN 400 MG 20 TABLET", ("Ибупрофен", "Ibuprofen"), "Ibuprofen") == plain


def test_title_inn_salt_cases_and_garbage():
    name = "SIMFLAT 40 MG/80 MG 30 FILM TABLET"
    title = build_medicine_title(name)
    # Перед анионом соли вещество в родительном падеже: в названии — именительный.
    assert title_with_inn(
        title, name, ("Отилония бромид + Симетикон", "Otilonium bromide + Simethicone"), "Otilonyum Bromur + Simetikon"
    )["ru"].startswith("SIMFLAT (отилоний + симетикон) 40 мг/80 мг")
    name = "KORDARON 200 MG 30 TABLET"
    assert title_with_inn(build_medicine_title(name), name, ("Амиодарона гидрохлорид", "Amiodarone hydrochloride"), "Amiodaron")[
        "ru"
    ].startswith("KORDARON (амиодарон) 200 мг")
    name = "VOLTAREN 50 MG 20 TABLET"
    # Катион после вещества — вещество уже в именительном.
    assert title_with_inn(build_medicine_title(name), name, ("Диклофенак натрия", "Diclofenac sodium"), "Diklofenak Sodyum")[
        "ru"
    ].startswith("VOLTAREN (диклофенак) 50 мг")
    # Обрывок названия вместо вещества — название без скобок.
    plain = build_medicine_title(name)
    assert title_with_inn(plain, name, ("Отаг (мл)", "Otag (Ml)"), "Otag (Ml)") == plain


def test_medicine_seo_title_drops_tail_parts_to_fit():
    title = "SCANIX (гадодиамид) 287 мг/мл, раствор для инъекций, флакон (в/в), 20 мл"
    assert medicine_seo_title(title) == "SCANIX (гадодиамид) 287 мг/мл, раствор для инъекций, флакон (в/в)"
    assert medicine_seo_title("CITOL (циталопрам) 20 мг, таблетки, 28 шт.") == "CITOL (циталопрам) 20 мг, таблетки, 28 шт."
    long = "BRAND (" + "очень длинное название вещества " * 3 + ") 10 мг, таблетки"
    assert len(medicine_seo_title(long)) <= 70 and not medicine_seo_title(long).endswith(" ")


def test_title_template_injection_ampoule_forms():
    assert build_medicine_title("FUROJECT 20MG/2 ML IM/IV ENJ. COZ. ICEREN 5 AMPUL")["ru"] == (
        "FUROJECT 20 мг/2 мл, раствор для инъекций (в/м, в/в), 5 ампул"
    )
    assert build_medicine_title("CALCITRON 2 MCG/ML IV ENJ. COZELTI ICEREN AMPUL(25)")["ru"] == (
        "CALCITRON 2 мкг/мл, раствор для инъекций (в/в), 25 ампул"
    )
    assert build_medicine_title("FILINSEL 24MG/ML 10 ML X 3 AMPUL")["ru"] == "FILINSEL 24 мг/мл, 10 мл, 3 ампулы"


def test_title_template_new_forms_thousands_and_brand_words():
    assert build_medicine_title("MIRENA RAHIM ICI SISTEM")["ru"] == "MIRENA, внутриматочная система"
    assert build_medicine_title("BELOC ZOK 50 MG KONTROLLU SALIMLI 20 FILM TABLET")["ru"] == (
        "BELOC ZOK 50 мг, таблетки с контролируемым высвобождением, покрытые плёночной оболочкой, 20 шт."
    )
    assert build_medicine_title("NEXIUM 40 MG ENTERIK KAPLI 28 PELLET TABLET")["ru"] == (
        "NEXIUM 40 мг, кишечнорастворимые таблетки, 28 шт."
    )
    assert build_medicine_title("ADENOSIN-L.M. 5 MG/ML ENJ/INF. ICIN COZ. ICEREN 2 ML 10 AMPUL")["ru"] == (
        "ADENOSIN-L.M. 5 мг/мл, раствор для инъекций и инфузий, 2 мл, 10 ампул"
    )
    # «5.000 I.U.» — пять тысяч, а не «5,000 МЕ».
    assert build_medicine_title("DEVIT-3 5.000 I.U. YUMUŞAK KAPSUL (50 KAPSUL)") == {
        "ru": "DEVIT-3 5000 МЕ, мягкие капсулы, 50 шт.",
        "en": "DEVIT-3 5000 IU, soft capsules, 50 pcs",
    }
    # Внутримышечно и внутрь сразу — шаблоном не записать.
    assert build_medicine_title("MONOVIT D3 300.000 IU/ML I.M./ORAL COZELTI (1 AMPUL)") is None
    # «LIKIT», «PELLET», «TEK DOZLUK» бывают частью бренда.
    assert build_medicine_title("FORANE LIKIT 100 ML SISE")["ru"] == "FORANE LIKIT, флакон, 100 мл"
    assert build_medicine_title("REFRESH TEK DOZLUK GOZ DAMLASI 30 FLAKON")["ru"] == (
        "REFRESH TEK DOZLUK, глазные капли, 30 флаконов"
    )
    assert build_medicine_title("KREON FUR KINDER PELLET 20 G")["ru"] == "KREON FUR KINDER PELLET 20 г"


def test_full_medicine_processing_uses_code_and_memory():
    root = Category.objects.create(name="Медицина", slug="code-medicines-root")
    category = Category.objects.create(name="Обезболивающие", slug="code-painkillers", parent=root)
    medicine = MedicineProduct.objects.create(
        name="MAJEZIK 100 MG 15 FILM TABLET",
        slug="majezik-code-pipeline",
        category=category,
        dosage_form="tablet",
        volume="15",
        active_ingredient="Flurbiprofen",
        prescription_type="Beyaz Reçete",
        shelf_life="24 Ay",
        external_data={"attributes": {"source_tabs": {"usage_instructions": {"text": PARA_A}}}},
    )
    medicine.refresh_from_db()
    card = {
        "ru": {
            "generated_title": "Маджезик",
            "generated_description": "MAJEZIK — таблетки, покрытые плёночной оболочкой, с флурбипрофеном 100 мг. "
            "Отпускается по белому рецепту. Срок годности 24 месяца.",
            "seo_title": "MAJEZIK 100 мг таблетки",
            "seo_description": "MAJEZIK 100 мг, флурбипрофен.",
            "keywords": ["MAJEZIK"],
            "volume": "15 мл",
        },
        "en": {
            "generated_description": "MAJEZIK film-coated tablets with flurbiprofen 100 mg. White prescription.",
            "seo_title": "MAJEZIK 100 mg tablets",
            "seo_description": "MAJEZIK 100 mg, flurbiprofen.",
            "keywords": ["MAJEZIK"],
        },
    }
    llm = RecordingLLM(
        card=card,
        inn={"flurbiprofen": ("флурбипрофен", "flurbiprofen")},
        paragraphs={PARA_A.strip(): tuple(t.strip() for t in TRANSLATIONS[PARA_A.strip()])},
    )
    generator = _generator(llm)
    generator._should_use_images_for_product = lambda _product: False

    log = generator.process_product(medicine.base_product.id, options={"analyze_images": False, "force": True})

    card_prompt = [c for c in llm.calls if "медицинский редактор" in c["system_prompt"]][0]["user_prompt"]
    assert "fixed_title" in card_prompt and '"dosage_form": "' not in card_prompt.split("Данные о")[0]
    log = AIProcessingLog.objects.get(pk=log.pk)
    # Действующее вещество — в скобках после бренда (title_with_inn).
    assert log.generated_title == "MAJEZIK (флурбипрофен) 100 мг, таблетки, покрытые плёночной оболочкой, 15 шт."
    # SEO title — из того же названия, с веществом, а не ответ модели («MAJEZIK 100 мг таблетки»).
    assert log.generated_seo_title == "MAJEZIK (флурбипрофен) 100 мг, таблетки, покрытые плёночной оболочкой"
    translations = log.extracted_attributes["translations_data"]
    assert translations["ru"]["volume"] == "15 таблеток"
    assert translations["ru"]["active_ingredient"] == "Флурбипрофен"
    assert translations["ru"]["shelf_life"] == "24 месяца"
    assert translations["ru"]["usage_instructions"].startswith("Принимайте по 500 мг")
    assert float(log.cost_usd) == pytest.approx(0.003)  # карточка + МНН + абзацы
    report = SemanticValidator().validate_log(log)
    assert "medicine_fact_mismatch" not in report.reasons
    assert "title" not in report.rejected_fields


def _fake_batch_client(uploaded, translate, answer=None):
    """OpenAI-клиент для Batch API: файлы пакета отдаются потоково, как в openai>=1.

    Каждый submit — новый пакет batch-N (готов сразу) со своим входным файлом
    file-in-N; ``answer(items)`` — ответ модели на запрос целиком (для сдвига).
    """
    from contextlib import contextmanager

    files, batches = uploaded.setdefault("files", {}), uploaded.setdefault("batches", [])
    answer = answer or (lambda items: {k: dict(zip(("ru", "en"), translate(v))) for k, v in items.items()})

    def output_lines(file_id):
        for line in files[file_id.replace("out", "in")].splitlines():
            request = json.loads(line)
            items = json.loads(request["body"]["messages"][1]["content"].split("\n\n", 1)[1])
            yield json.dumps({
                "custom_id": request["custom_id"],
                "response": {"body": {
                    "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer(items))}}],
                    "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
                }},
            })

    @contextmanager
    def content(file_id):
        if file_id.startswith("file-in"):
            data = files[file_id].encode("utf-8")
            yield SimpleNamespace(iter_bytes=lambda: iter([data[:100], data[100:]]))
        else:
            yield SimpleNamespace(iter_lines=lambda: output_lines(file_id))

    class FakeFiles:
        with_streaming_response = SimpleNamespace(content=content)

        def create(self, file, purpose):
            file_id = f"file-in-{len(files) + 1}"
            files[file_id] = uploaded["jsonl"] = file[1].decode("utf-8")
            return SimpleNamespace(id=file_id)

        def retrieve(self, file_id):
            return SimpleNamespace(bytes=len(files[file_id].encode("utf-8")))

    class FakeBatches:
        def create(self, **kwargs):
            uploaded["batch"] = kwargs
            batch = SimpleNamespace(
                id=f"batch-{len(batches) + 1}", status="completed", created_at=1_760_000_000 + len(batches),
                input_file_id=kwargs["input_file_id"], output_file_id=kwargs["input_file_id"].replace("in", "out"),
                request_counts=None, metadata=kwargs["metadata"],
            )
            batches.append(batch)
            return batch

        def retrieve(self, batch_id):
            return next(batch for batch in batches if batch.id == batch_id)

        def list(self, limit):
            return list(reversed(batches))

    class FakeClient:
        model = "gpt-4o-mini"
        pricing = {"gpt-4o-mini": {"input": 0.15, "output": 0.60}}
        client = SimpleNamespace(files=FakeFiles(), batches=FakeBatches())

        @staticmethod
        def _parse_json_response(raw):
            return json.loads(raw)

    return FakeClient


def test_paragraph_batch_api_submit_then_collect_fills_memory(monkeypatch):
    from io import StringIO

    from django.core.management import call_command

    from apps.ai.management.commands import medicine_paragraph_batch

    MedicineProduct.objects.create(
        name="BATCH MED",
        slug="batch-med-paragraphs",
        external_data={"attributes": {"source_tabs": {"side_effects": {"text": f"{PARA_B}\n{PARA_C}"}}}},
    )
    remember(PARAGRAPH_NAMESPACE, {PARA_B.strip(): {"ru": "уже есть", "en": "cached"}})
    uploaded = {}
    client = _fake_batch_client(uploaded, lambda text: tuple(t.strip() for t in TRANSLATIONS[text]))
    monkeypatch.setattr(medicine_paragraph_batch, "LLMClient", client)
    out = StringIO()

    call_command("medicine_paragraph_batch", "submit", stdout=out)
    call_command("medicine_paragraph_batch", "collect", "batch-1", stdout=out)

    request = json.loads(uploaded["jsonl"].splitlines()[0])
    assert list(json.loads(request["body"]["messages"][1]["content"].split("\n\n", 1)[1]).values()) == [
        PARA_C.strip()
    ]
    assert uploaded["batch"]["completion_window"] == "24h"
    assert lookup(PARAGRAPH_NAMESPACE, [PARA_C.strip()])[PARA_C.strip()]["ru"].startswith("Во время беременности")
    assert "записано новых абзацев: 1" in out.getvalue()


def test_remember_writes_in_chunks_and_is_idempotent(monkeypatch):
    from apps.ai.services import translation_memory

    sizes = []
    original = AITranslationMemory.objects.bulk_create

    def spy(objs, **kwargs):
        objs = list(objs)
        sizes.append(len(objs))
        return original(objs, **kwargs)

    monkeypatch.setattr(AITranslationMemory.objects, "bulk_create", spy)
    rows = {f"Paragraf {i} için metin.": {"ru": f"Абзац {i}", "en": f"Paragraph {i}"} for i in range(1201)}

    created = translation_memory.remember(PARAGRAPH_NAMESPACE, rows)
    again = translation_memory.remember(PARAGRAPH_NAMESPACE, rows)

    assert created == 1201
    assert again == 0
    assert max(sizes) <= translation_memory.REMEMBER_BATCH_SIZE
    assert sizes[:3] == [500, 500, 201]
    assert AITranslationMemory.objects.filter(namespace=PARAGRAPH_NAMESPACE).count() == 1201


def test_large_paragraph_batch_is_collected_in_chunks_and_repeat_adds_nothing(monkeypatch):
    from io import StringIO

    from django.core.management import call_command

    from apps.ai.management.commands import medicine_paragraph_batch

    paragraphs = [f"Bu ilaç {i}. paragrafta günde {i} kez kullanılır ve doktor kontrolü gerekir." for i in range(1500)]
    for index in range(0, len(paragraphs), 100):
        MedicineProduct.objects.create(
            name=f"BIG MED {index}",
            slug=f"big-batch-{index}",
            external_data={"attributes": {"source_tabs": {"usage_instructions": {
                "text": "\n".join(paragraphs[index:index + 100])
            }}}},
        )
    uploaded = {}

    def translate(text):
        number = text.split()[2].rstrip(".")
        return (
            f"Этот препарат в абзаце {number} применяют {number} раз в день под контролем врача.",
            f"This medicine in paragraph {number} is used {number} times a day under medical control.",
        )

    monkeypatch.setattr(medicine_paragraph_batch, "LLMClient", _fake_batch_client(uploaded, translate))
    from apps.ai.services import medicine_memory

    monkeypatch.setattr(medicine_memory, "PARAGRAPH_BATCH_CHARS", 3000)
    sizes = []
    original = AITranslationMemory.objects.bulk_create

    def spy(objs, **kwargs):
        objs = list(objs)
        sizes.append(len(objs))
        return original(objs, **kwargs)

    monkeypatch.setattr(AITranslationMemory.objects, "bulk_create", spy)
    out = StringIO()

    call_command("medicine_paragraph_batch", "submit", stdout=out)
    call_command("medicine_paragraph_batch", "collect", "batch-1", "--progress-every", "1", stdout=out)
    first = AITranslationMemory.objects.filter(namespace=PARAGRAPH_NAMESPACE).count()
    call_command("medicine_paragraph_batch", "collect", "batch-1", stdout=out)

    assert first == 1500
    assert AITranslationMemory.objects.filter(namespace=PARAGRAPH_NAMESPACE).count() == 1500
    assert max(sizes) <= 500
    assert "записано новых абзацев: 1500" in out.getvalue()
    assert "записано новых абзацев: 0" in out.getvalue()
    assert "запросов 1/" in out.getvalue()


def _numbered(i):
    """Абзац с номером и его верный перевод: чужой перевод виден по числам."""
    return (
        f"Bu ilaç {i}. paragrafta günde {i} kez kullanılır ve doktor kontrolü gerekir.",
        f"Этот препарат в абзаце {i} применяют {i} раз в день под контролем врача.",
        f"This medicine in paragraph {i} is used {i} times a day under medical control.",
    )


def _translate_numbered(text):
    return _numbered(int(text.split()[2].rstrip(".")))[1:]


def _skip_fourth(items):
    """Ответ модели, пропустившей 4-й абзац: дальше каждому ключу достаётся перевод следующего."""
    keys = list(items)
    rows = [dict(zip(("ru", "en"), _translate_numbered(items[key]))) for key in keys]
    return dict(zip(keys, rows[:3] + rows[4:] + [{}]))


def test_paragraph_requests_are_short_and_ask_ru_en_per_item():
    from apps.ai.services.medicine_memory import paragraph_batches

    sources = [_numbered(i)[0] for i in range(2, 27)]
    assert [len(batch) for batch in paragraph_batches(sources)] == [10, 10, 5]
    assert [len(batch) for batch in paragraph_batches(["a" * 3000, "b" * 3000])] == [1, 1]
    llm = RecordingLLM(paragraphs={_numbered(i)[0]: _numbered(i)[1:] for i in range(2, 27)})
    content = {"ru": {}, "en": {}}

    _generator(llm)._translate_medicine_source_sections(
        content, {"usage_instructions": "\n".join(sources)}, product_id=301
    )

    calls = llm.calls_of("абзацы")
    assert len(calls) == 3
    assert '{"1": {"ru": "…", "en": "…"}' in calls[0]["user_prompt"]
    assert content["ru"]["usage_instructions"].startswith("Этот препарат в абзаце 2 применяют")
    assert AITranslationMemory.objects.filter(namespace=PARAGRAPH_NAMESPACE).count() == 25


def test_shift_rejects_whole_short_request_and_only_it_is_retried():
    sources = [_numbered(i)[0] for i in range(2, 22)]

    class SkipOnceLLM(RecordingLLM):
        def generate_content(self, **kwargs):
            result = super().generate_content(**kwargs)
            if len(self.calls_of("абзацы")) == 1:
                items = json.loads(kwargs["user_prompt"].split("\n\n", 1)[1])
                result["content"] = _skip_fourth(items)
            return result

    llm = SkipOnceLLM(paragraphs={_numbered(i)[0]: _numbered(i)[1:] for i in range(2, 22)})
    content = {"ru": {}, "en": {}}

    usage = _generator(llm)._translate_medicine_source_sections(
        content, {"side_effects": "\n".join(sources)}, product_id=302
    )

    calls = llm.calls_of("абзацы")
    assert len(calls) == 3  # 2 запроса + повтор первого целиком
    retried = json.loads(calls[2]["user_prompt"].split("\n\n", 1)[1])
    assert list(retried.values()) == sources[:10]  # и абзацы до пропуска, а второй запрос — нет
    assert content["attributes"]["medicine_translation_quality"]["side_effects"]["complete"] is True
    assert usage["retried_paragraphs"] == 10


def _part_products(count, per_product=6):
    for index in range(count):
        numbers = range(2 + index * per_product, 2 + (index + 1) * per_product)
        MedicineProduct.objects.create(
            name=f"PART MED {index}",
            slug=f"part-med-{index}",
            external_data={"attributes": {"source_tabs": {"usage_instructions": {
                "text": "\n".join(_numbered(i)[0] for i in numbers)
            }}}},
        )
    return list(MedicineProduct.objects.filter(slug__startswith="part-med-").order_by("pk").values_list("pk", flat=True))


def test_paragraph_batch_goes_in_parts_and_next_part_waits_for_previous(monkeypatch):
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    from apps.ai.management.commands import medicine_paragraph_batch

    pks = _part_products(4)
    uploaded = {}
    monkeypatch.setattr(medicine_paragraph_batch, "LLMClient", _fake_batch_client(uploaded, _translate_numbered))
    out = StringIO()

    call_command("medicine_paragraph_batch", "submit", "--part-size", "10", stdout=out)
    first = uploaded["batches"][0]
    # 10 абзацев набрано на втором лекарстве — часть дошла до его конца.
    assert first.metadata == {
        "kind": PARAGRAPH_NAMESPACE, "part": "1", "paragraphs": "12", "last_product": str(pks[1]), "retry_of": "",
    }
    assert len(uploaded["files"]["file-in-1"].splitlines()) == 2  # запросы по 10 и 2 абзаца
    with pytest.raises(CommandError, match="не забрана"):
        call_command("medicine_paragraph_batch", "submit", "--part-size", "10", stdout=out)

    call_command("medicine_paragraph_batch", "collect", first.id, stdout=out)
    assert "брак 0 (0.0%)" in out.getvalue()
    assert "можно следующую часть" in out.getvalue()

    first.status = "in_progress"
    with pytest.raises(CommandError, match="ещё в работе"):
        call_command("medicine_paragraph_batch", "submit", stdout=out)
    first.status = "completed"

    call_command("medicine_paragraph_batch", "submit", "--part-size", "10", stdout=out)
    second = uploaded["batches"][1]
    assert second.metadata["part"] == "2" and second.metadata["last_product"] == str(pks[3])
    assert _numbered(14)[0] in uploaded["files"]["file-in-2"] and _numbered(13)[0] not in uploaded["files"]["file-in-2"]
    call_command("medicine_paragraph_batch", "collect", second.id, stdout=out)

    call_command("medicine_paragraph_batch", "submit", stdout=out)
    assert "проход по каталогу закончен" in out.getvalue()
    status = StringIO()
    call_command("medicine_paragraph_batch", "status", stdout=status)
    assert status.getvalue().index("№2 batch-2 — completed") < status.getvalue().index("№1 batch-1")


def test_part_with_shift_stops_run_and_retry_sends_only_rejected(monkeypatch):
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    from apps.ai.management.commands import medicine_paragraph_batch

    pks = _part_products(3)
    state = {"skip": True}

    def answer(items):
        if state["skip"] and len(items) == 10:
            return _skip_fourth(items)
        return {key: dict(zip(("ru", "en"), _translate_numbered(text))) for key, text in items.items()}

    uploaded = {}
    monkeypatch.setattr(
        medicine_paragraph_batch, "LLMClient", _fake_batch_client(uploaded, _translate_numbered, answer)
    )
    out = StringIO()

    call_command("medicine_paragraph_batch", "submit", "--part-size", "10", stdout=out)
    call_command("medicine_paragraph_batch", "collect", "batch-1", stdout=out)

    report = out.getvalue()
    assert "абзацев 12, запросов 2; принято 2, брак 10 (83.3%); сдвиг в 1 запросах (50.0%)" in report
    assert "shifted 10" in report
    assert "$0.0625 за 1000 абзацев" in report  # 2 запроса × (1000 × $0.075 + 1000 × $0.30) / 1 млн
    assert "СТОП" in report
    with pytest.raises(CommandError, match="больше порога 15%"):
        call_command("medicine_paragraph_batch", "submit", stdout=out)

    state["skip"] = False
    call_command("medicine_paragraph_batch", "submit", "--retry", "batch-1", stdout=out)
    retry = uploaded["batches"][1]
    assert retry.metadata["retry_of"] == "batch-1" and retry.metadata["paragraphs"] == "10"
    sent = [
        text for line in uploaded["files"]["file-in-2"].splitlines()
        for text in json.loads(json.loads(line)["body"]["messages"][1]["content"].split("\n\n", 1)[1]).values()
    ]
    assert sent == [_numbered(i)[0] for i in range(2, 12)]
    call_command("medicine_paragraph_batch", "collect", retry.id, stdout=out)

    call_command("medicine_paragraph_batch", "submit", "--part-size", "10", stdout=out)
    third = uploaded["batches"][2]
    assert third.metadata["part"] == "3" and third.metadata["last_product"] == str(pks[2])
    assert AITranslationMemory.objects.filter(namespace=PARAGRAPH_NAMESPACE).count() == 12


def test_coverage_report_and_inn_dry_run_do_not_call_model():
    from io import StringIO

    from django.core.management import call_command

    MedicineProduct.objects.create(
        name="PAROL 500 MG 20 TABLET", slug="coverage-parol", is_active=True,
        administration_route="Oral", prescription_type="Gizli Reçete", active_ingredient="Parasetamol",
    )
    out = StringIO()

    call_command("medicine_reference_coverage", "--paragraphs", stdout=out)
    call_command("translate_medicine_inn", "--dry-run", stdout=out)

    report = out.getvalue()
    assert "'Gizli Reçete'" in report
    assert "Название по шаблону: 1 из 1" in report
    assert "к переводу: 1" in report


def test_manager_edits_inn_in_admin_and_it_reaches_products(client, django_user_model):
    client.force_login(django_user_model.objects.create_superuser(
        username="inn-admin", email="inn-admin@example.com", password="test-password",
    ))
    remember(INN_NAMESPACE, {"parasetamol": {"ru": "Парацетомол", "en": "Paracetamol"}})
    medicine = MedicineProduct.objects.create(name="ADMIN INN", slug="admin-inn-edit", active_ingredient="Parasetamol")
    medicine.translations.create(locale="ru", active_ingredient="Парацетомол")
    entry = AITranslationMemory.objects.get(namespace=INN_NAMESPACE)

    response = client.post(
        f"/admin/ai/aitranslationmemory/{entry.pk}/change/",
        {"ru_text": "Парацетамол", "en_text": "Paracetamol"},
    )

    assert response.status_code == 302
    assert medicine.translations.get(locale="ru").active_ingredient == "Парацетамол"


# ── Пилот 18.10.2026 (15 лекарств): названия от модели с браком и неполный раздел хранения ──

PILOT_TITLES = {
    # id 306: модель — «… ДИЛАЛТИ СПРЕЙ, РАСТВОР (АЛЬТЕРНАРИЯ)»
    "SULGEN 30000 TU/ML DİLALTI SPREY, ÇÖZELTİ": (
        "SULGEN 30000 ТЕ/мл, подъязычный спрей, раствор",
        "SULGEN 30000 TU/ml, sublingual spray, solution",
    ),
    # id 113: модель — «… 50 MG ФИЛЬМ-КАПСУЛИРОВАННЫЕ ТАБЛЕТКИ (80 ТАБЛЕТ)»
    "SOLOPINA 50 MG FİLM KAPLI TABLET (80 TABLET)": (
        "SOLOPINA 50 мг, таблетки, покрытые плёночной оболочкой, 80 шт.",
        "SOLOPINA 50 mg, film-coated tablets, 80 pcs",
    ),
    # id 339: модель — «LEMTRADA 12MG/1.2ML (10MG/ML) ИНЪЕКЦИЯ»
    "LEMTRADA 12MG/1.2ML (10MG/ML) IV İNFÜZYON İÇİN KONSANTRE ÇÖZELTİ": (
        "LEMTRADA 12 мг/1,2 мл (10 мг/мл), концентрат для приготовления раствора для инфузий",
        "LEMTRADA 12 mg/1.2 ml (10 mg/ml), concentrate for solution for infusion",
    ),
    "HERCEPTIN 150 MG IV İNFÜZYON İÇİN LİYOFİLİZE TOZ 1 FLAKON": (
        "HERCEPTIN 150 мг, лиофилизат для приготовления раствора для инфузий, 1 флакон",
        "HERCEPTIN 150 mg, powder for solution for infusion, 1 vial",
    ),
    "TEGRETOL 200 MG CR 50 TABLET": ("TEGRETOL 200 мг CR, таблетки, 50 шт.", "TEGRETOL 200 mg CR, tablets, 50 pcs"),
}


@pytest.mark.parametrize("source", PILOT_TITLES)
def test_pilot_forms_are_covered_by_title_template(source):
    ru, en = PILOT_TITLES[source]
    assert build_medicine_title(source) == {"ru": ru, "en": en}


@pytest.mark.parametrize(
    "source,llm_title",
    [
        ("SULGEN 30000 TU/ML DİLALTI SPREY, ÇÖZELTİ (ALTERNARIA)", "SULGEN 30000 TU/ML ДИЛАЛТИ СПРЕЙ, РАСТВОР (АЛЬТЕРНАРИЯ)"),
        ("SOLOPINA 50 MG FİLM KAPLI TABLET (80 TABLET)", "SOLOPINA 50 MG ФИЛЬМ-КАПСУЛИРОВАННЫЕ ТАБЛЕТКИ (80 ТАБЛЕТ)"),
        ("LEMTRADA 12MG/1.2ML (10MG/ML) IV İNFÜZYON İÇİN KONSANTRE ÇÖZELTİ", "LEMTRADA 12MG/1.2ML (10MG/ML) ИНЪЕКЦИЯ"),
    ],
)
def test_llm_medicine_title_with_transliteration_or_latin_units_is_rejected(source, llm_title):
    category, _ = Category.objects.get_or_create(slug="pilot-medicines", defaults={"name": "Медицина"})
    medicine = MedicineProduct.objects.create(
        name=source, slug=f"pilot-title-{abs(hash(source)) % 10**8}", category=category
    )
    medicine.refresh_from_db()
    validator = SemanticValidator()

    bad = validator.validate(medicine.base_product, generated_titles={"ru": llm_title}, dynamic_attributes=[])
    template = build_medicine_title(source) or {
        "ru": "SULGEN 30000 ТЕ/мл, подъязычный спрей, раствор (альтернария)"
    }
    good = validator.validate(
        medicine.base_product, generated_titles={"ru": template["ru"]}, dynamic_attributes=[]
    )

    assert "title_untranslated" in bad.reasons
    assert "title" in bad.rejected_fields
    assert "title_untranslated" not in good.reasons


STORAGE_SECTION = (
    "25°C'nin altındaki oda sıcaklığında, ambalajında saklayınız. Dondurmayınız.\n"
    "Ruhsat sahibi: Abdi İbrahim İlaç San. ve Tic. A.Ş.\n"
    "Reşitpaşa Mahallesi, Eski Büyükdere Cad. No: 4 34467 Maslak / Sarıyer / İstanbul\n"
    "Tel: 0212 366 84 00 Faks: 0212 276 20 20"
)


def test_storage_section_requisites_are_translated_by_code_and_not_blocked():
    storage = STORAGE_SECTION.splitlines()[0]
    llm = RecordingLLM(paragraphs={storage: (
        "Хранить при температуре ниже 25 °C в оригинальной упаковке. Не замораживать.",
        "Store below 25 °C in the original package. Do not freeze.",
    )})
    generator = _generator(llm)
    content = {"ru": {}, "en": {}}

    generator._translate_medicine_source_sections(content, {"storage_conditions": STORAGE_SECTION}, product_id=211)

    sent = json.loads(llm.calls_of("абзацы")[0]["user_prompt"].split("\n\n", 1)[1])
    assert list(sent.values()) == [storage]  # реквизиты модели не отправляются
    quality = content["attributes"]["medicine_translation_quality"]["storage_conditions"]
    assert quality["complete"] is True
    ru = content["ru"]["storage_conditions"]
    assert "Владелец регистрационного удостоверения: Abdi İbrahim İlaç San. ve Tic. A.Ş." in ru
    assert "Тел.: 0212 366 84 00 Факс: 0212 276 20 20" in ru
    assert "Marketing authorisation holder:" in content["en"]["storage_conditions"]
    # Ни применение, ни валидатор не считают адрес непереведённым текстом.
    assert generator._looks_untranslated_turkish(ru) is False
    medicine = MedicineProduct.objects.create(name="STORAGE MED", slug="storage-requisites")
    medicine.refresh_from_db()
    log = AIProcessingLog.objects.create(
        product=medicine.base_product,
        processing_type="full",
        input_data={},
        extracted_attributes={
            "medicine_translation_quality": content["attributes"]["medicine_translation_quality"],
            "translations_data": {"ru": {"storage_conditions": ru}, "en": {}},
        },
    )
    report = SemanticValidator().validate_log(log)
    assert "untranslated_medicine_field" not in report.reasons
    assert "incomplete_medicine_translation" not in report.reasons


def test_instruction_paragraph_with_phone_is_still_translated_by_model():
    from apps.ai.services.medicine_fact_check import is_proper_name_line

    assert not is_proper_name_line(
        "Türkiye Farmakovijilans Merkezi (TÜFAM)'ne bildiriniz (e-posta: tufam@titck.gov.tr; tel: 0 800 314 00 08)."
    )
    assert not is_proper_name_line("Günde 10 mg/kg verilir.")


# ── Пилот 20.10.2026 (AIRun 2, 50 лекарств id 179–252): брак, который проходил проверки ──


def _medicine(name):
    category, _ = Category.objects.get_or_create(slug="pilot2-medicines", defaults={"name": "Медицина"})
    medicine = MedicineProduct.objects.create(
        name=name, slug=f"pilot2-{abs(hash(name)) % 10**8}", category=category
    )
    medicine.refresh_from_db()
    return medicine.base_product


def _reasons(source, ru, en=""):
    return SemanticValidator().validate(
        _medicine(source), generated_titles={"ru": ru, "en": en}, dynamic_attributes=[]
    )


# 1. Названия ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "title",
    ["MOUNJARO 7", "DIFFERIN 0", "ZOPROTEC PLUS 30/12", "A-FERIN SINUS 500/30/1",
     "Аугментин 200 мг/28", "Кенакорт-А Орабаз %0", "OMNITROPE 15 MG (45 IU)/1"],
)
def test_truncated_medicine_title_goes_to_moderation(title):
    # Прошлая обработка обрезала название на десятичном разделителе (7,5 MG → «7»);
    # модель копирует его, и лог уходил как «готово».
    report = _reasons(title, title, title)

    assert report.reasons[0] == "title_truncated"
    assert "title" in report.rejected_fields


@pytest.mark.parametrize(
    "title",
    ["INDOCOLIR GOZ DAMLASI % 0,1", "DERMOVATE %0,05", "D-COLEFOR 20.000 IU",
     "MAJEZIK 100 мг, таблетки, покрытые плёночной оболочкой, 15 шт.", "BENEXOL B12"],
)
def test_percent_dose_and_template_titles_are_not_truncated(title):
    assert not TRUNCATED_TITLE_RE.search(title)


def test_copy_of_already_translated_source_name_goes_to_moderation():
    # Шаблон из кириллического названия не строится, модель копирует мусор как есть.
    source = "KLAMOKS BID 400/57 СУСПЕНЗИЯ ДЛЯ ПРИГОТОВЛЕНИЯ КРУПНОГО ПАХНУЩЕГО ПРАПОРТА 100 МЛ"
    report = _reasons(source, source, "KLAMOKS BID 400/57 SUSPENSION 100 ML")

    assert report.reasons[0] == "title_source_translated"
    assert "title" in report.rejected_fields


def test_moderator_fixed_title_of_translated_source_passes():
    report = _reasons(
        "CLEOCIN T 1% Топикальный раствор 30 мл",
        "CLEOCIN T 1%, раствор для наружного применения, 30 мл",
        "CLEOCIN T 1%, cutaneous solution, 30 ml",
    )

    assert "title" not in report.rejected_fields
    assert report.reasons == []


@pytest.mark.parametrize(
    "source,title",
    [
        ("PEXA XR 3 MG UZATILMIS SALIMLI 30 TABLET", "PEXA XR 3 мг УЗАТИЛМИШ САЛИМЛИ 30 таблеток"),
        ("CLEOCIN T %1 TOPIKAL COZELTI 30 ML", "CLEOCIN T 1% Топикальный раствор 30 мл"),
        ("OMHEAL 40 MG SERT KAPSUL (28 KAPSUL)", "OMHEAL 40 мг СЕРТ КАПСУЛЫ (28 капсул)"),
        ("CALIRA-MET 5 MG/1000 MG FILM KAPLI TABLET", "CALIRA-MET 5 мг/1000 мг ПЛЕНКА КАПЛИ ТАБЛЕТКИ"),
        ("BENEXOL B12 FILM KAPLI TABLET (50 TB)", "BENEXOL B12 таблетки (50 ТБ)"),
        ("DEVIT-3 300.000 IU/ML IM/ORAL COZELTI", "DEVIT-3 300.000 МЕ/мл, И.М./ОРОЛЬ раствор"),
        # AIRun 3, лог 1036 — уходил как «готово»
        (
            "PF K-CAMINE %8 AMINO ASIT IV INFUZYON ICIN COZELTI 500 ML (SETLI)",
            "PF K-CAMINE %8 АМИНОКИСЛОТ ИВ ИНФУЗИЯ 500 МЛ (СЕТ)",
        ),
    ],
)
def test_cyrillic_transliteration_of_turkish_form_is_untranslated(source, title):
    report = _reasons(source, title)

    assert "title_untranslated" in report.reasons


def test_hyphenated_brand_and_film_coated_survive_title_cleanup():
    # «DEVIT-3», «CALIRA-MET» и «film-coated» похожи на артикул и вырезались.
    generator = ContentGenerator.__new__(ContentGenerator)
    content = {
        "ru": {"generated_title": "CALIRA-MET 5 мг/1000 мг, таблетки, покрытые плёночной оболочкой, 56 шт."},
        "en": {"generated_title": "CALIRA-MET 5 mg/1000 mg, film-coated tablets, 56 pcs"},
    }

    generator._sanitize_ai_content(content, {"product_type": "medicines"})

    assert content["en"]["generated_title"] == "CALIRA-MET 5 mg/1000 mg, film-coated tablets, 56 pcs"
    assert generator._normalize_product_name(content["ru"]["generated_title"], "medicines").startswith(
        "CALIRA-MET 5 мг"
    )
    assert generator._normalize_product_name("DEVIT-3 50.000 IU", "medicines") == "DEVIT-3 50.000 IU"
    # У остальных доменов артикулы по-прежнему вырезаются.
    assert generator._normalize_product_name("Платье J5SM-TST7325", "clothing") == "Платье"


# 2. Хранение: заголовок раздела с брендом латиницей ───────────────────


@pytest.mark.parametrize(
    "source,ru,en",
    [
        ("5. DERMOVATE'IN SAKLANMASI", "5. Хранение DERMOVATE", "5. Storage of DERMOVATE"),
        ("5. AUGMENTİN'İN SAKLANMASI", "5. ХРАНЕНИЕ AUGMENTIN", "5. STORAGE OF AUGMENTIN"),
        ("5. {BRAND} SR'NİN SAKLANMASI", "5. Хранение {BRAND} SR", "5. Storage of {BRAND} SR"),
    ],
)
def test_storage_heading_with_latin_brand_is_russian(source, ru, en):
    # Все 9 разделов хранения с ru_not_russian в пилоте: единственный непринятый
    # абзац — этот заголовок («Хранение» — 8 кириллических букв при пороге 10).
    assert paragraph_problems(source, ru, en) == []


@pytest.mark.parametrize(
    "source,ru",
    [
        ("5. DERMOVATE'IN SAKLANMASI", "5. DERMOVATE'IN SAKLANMASI"),
        (
            "DERMOVATE'ı çocukların göremeyeceği, erişemeyeceği yerlerde ve ambalajında saklayınız.",
            "Хранение DERMOVATE: cocuklarin goremeyecegi yerlerde ve ambalajinda saklayiniz.",
        ),
    ],
)
def test_untranslated_storage_paragraph_is_still_rejected(source, ru):
    assert "ru_not_russian" in paragraph_problems(source, ru, "Keep DERMOVATE away from children.")


# 3. Тип рецепта ────────────────────────────────────────────────────────


def test_prescription_type_is_clear_for_russian_buyer():
    assert translate_reference_field("prescription_type", "Beyaz Reçete") == (
        "Рецептурный препарат", "Prescription medicine",
    )
    assert translate_reference_field("prescription_type", "Kırmızı Reçete") == (
        "Рецептурный препарат строгого учёта", "Controlled prescription medicine",
    )
    assert translate_reference_field("prescription_type", "Reçetesiz") == (
        "Безрецептурный препарат", "Over-the-counter medicine",
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Препарат принимается перорально и отпускается по белому рецепту.",
         "Препарат принимается перорально и отпускается по рецепту."),
        ("Для его получения необходим белый рецепт.", "Для его получения необходим рецепт."),
        ("Белый рецепт.", "Рецепт."),
        ("The product requires a white prescription.", "The product requires a prescription."),
        ("Available by White Prescription.", "Available by Prescription."),
        ("Рецептурный препарат, без рецепта не отпускается.", "Рецептурный препарат, без рецепта не отпускается."),
    ],
)
def test_prescription_colour_is_removed_from_text(text, expected):
    assert neutral_prescription_text(text) == expected


# 4. Особые сведения без предмета ───────────────────────────────────────


@pytest.mark.parametrize(
    "source,expected",
    [
        ("Birlikte kullanılmamalıdır. Dikkatli olunmalıdır.", ""),
        ("Hastalar duyarlılıkları belli oluncaya kadar kullanmamalıdır.", ""),
        (
            "Dikkatli olunmalıdır. Tedavi süresince emzirmemesi önerilir.(Kullanılmamalıdır) Yüksek riskli ilaç!",
            "Tedavi süresince emzirmemesi önerilir.(Kullanılmamalıdır) Yüksek riskli ilaç!",
        ),
        ("Araç ve makine kullanılmamalıdır.", "Araç ve makine kullanılmamalıdır."),
        ("", ""),
    ],
)
def test_special_notes_without_subject_are_dropped(source, expected):
    assert meaningful_special_notes(source) == expected


def _process(special_notes, card_notes):
    category = Category.objects.create(name="Медицина", slug="pilot2-notes")
    medicine = MedicineProduct.objects.create(
        name="MAJEZIK 100 MG 15 FILM TABLET",
        slug="pilot2-notes",
        category=category,
        dosage_form="tablet",
        prescription_type="Beyaz Reçete",
        special_notes=special_notes,
    )
    medicine.refresh_from_db()
    card = {
        "ru": {
            "generated_description": "MAJEZIK — таблетки, покрытые плёночной оболочкой, 100 мг. "
            "Препарат отпускается по белому рецепту и имеет срок годности 24 месяца.",
            "seo_title": "MAJEZIK 100 мг",
            "seo_description": "MAJEZIK 100 мг, по белому рецепту.",
            "keywords": ["MAJEZIK"],
            "special_notes": card_notes[0],
        },
        "en": {
            "generated_description": "MAJEZIK film-coated tablets 100 mg. It is available by white prescription.",
            "seo_title": "MAJEZIK 100 mg",
            "seo_description": "MAJEZIK 100 mg.",
            "keywords": ["MAJEZIK"],
            "special_notes": card_notes[1],
        },
    }
    llm = RecordingLLM(card=card)
    generator = _generator(llm)
    generator._should_use_images_for_product = lambda _product: False
    log = generator.process_product(medicine.base_product.id, options={"analyze_images": False, "force": True})
    prompt = [c for c in llm.calls if "медицинский редактор" in c["system_prompt"]][0]["user_prompt"]
    facts = json.loads(prompt.split("Данные о лекарственном препарате:", 1)[1])
    return AIProcessingLog.objects.get(pk=log.pk), facts


def test_meaningless_special_notes_are_not_accepted_and_rx_is_neutral():
    log, facts = _process(
        "Birlikte kullanılmamalıdır. Dikkatli olunmalıdır.",
        ("Не следует использовать совместно. Необходимо проявлять осторожность.",
         "Should not be used together. Caution is advised."),
    )

    assert "special_notes" not in facts["source_facts"]
    translations = log.extracted_attributes["translations_data"]
    assert "special_notes" not in translations["ru"]
    assert "special_notes" not in translations["en"]
    assert translations["ru"]["prescription_type"] == "Рецептурный препарат"
    assert "белому" not in log.generated_description
    assert "отпускается по рецепту" in log.generated_description
    seo = log.extracted_attributes["seo_translations"]
    assert "white" not in seo["en"]["generated_description"]
    assert "белому" not in seo["ru"]["meta_description"]


def test_special_notes_with_subject_are_kept():
    log, facts = _process(
        "Dikkatli olunmalıdır. Laktasyon döneminde kullanılmamalıdır.",
        ("Не применять в период лактации.", "Do not use during lactation."),
    )

    assert facts["source_facts"]["special_notes"] == "Laktasyon döneminde kullanılmamalıdır."
    assert log.extracted_attributes["translations_data"]["ru"]["special_notes"] == (
        "Не применять в период лактации."
    )


def test_medicine_without_category_is_still_validated():
    # Пилот AIRun 3, лог 1056: у товара нет категории, проверки пропускались, и
    # «RINGER LAKTAT OSEL» (бренд BIOSEL испорчен моделью) ушёл как «готово».
    medicine = MedicineProduct.objects.create(
        name="RINGER LAKTAT BIOSEL ENJEKTABL SOL. 500 ML SETLI SISE", slug="pilot3-no-category"
    )
    medicine.refresh_from_db()
    validator = SemanticValidator()

    broken = validator.validate(
        medicine.base_product,
        generated_titles={"ru": "RINGER LAKTAT OSEL 500 мл инъекционный раствор"},
        dynamic_attributes=[],
    )
    incomplete = validator.validate(
        medicine.base_product,
        generated_titles={},
        dynamic_attributes=[],
        extracted_attributes={"medicine_translation_quality": {"storage_conditions": {"complete": False}}},
    )

    assert medicine.base_product.category_id is None
    assert "title" in broken.rejected_fields
    assert "incomplete_medicine_translation" in incomplete.reasons


# Пилот AIRun 3 (логи 1025–1074) и разбор всех 13 тыс. названий: шаблон сдавался или ошибался.
PILOT3_TITLES = {
    # лог 1062: «+» между дозировками превращался в скобки
    "NASOWELL 1 MG/ML + 50 MG/ML BURUN SPREYI, COZELTI": (
        "NASOWELL 1 мг/мл + 50 мг/мл, назальный спрей, раствор",
        "NASOWELL 1 mg/ml + 50 mg/ml, nasal spray, solution",
    ),
    # лог 1061: модель перевернула смысл — «раствор для приготовления лиофилизированного порошка»
    "CERNEVIT IV/IM ENJEKSIYONLUK/INFUZYONLUK COZELTI HAZIRLAMAK ICIN LIYOFILIZE TOZ (4 FLAKON)": (
        "CERNEVIT, лиофилизат для приготовления раствора для инъекций и инфузий (в/в, в/м), 4 флакона",
        "CERNEVIT, powder for solution for injection/infusion (IV/IM), 4 vials",
    ),
    "AMOKLAVIN BID 400/57 MG FORTE ORAL SUSPANSIYON HAZIRLAMAK ICIN KURU TOZ (70 ML)": (
        "AMOKLAVIN BID 400/57 мг FORTE, порошок для приготовления суспензии для приёма внутрь, 70 мл",
        "AMOKLAVIN BID 400/57 mg FORTE, powder for oral suspension, 70 ml",
    ),
    "VERQUVO 5 MG 98 TABLETS": ("VERQUVO 5 мг, таблетки, 98 шт.", "VERQUVO 5 mg, tablets, 98 pcs"),
    "LYSODREN 500 MG, 100 TAB": ("LYSODREN 500 мг, таблетки, 100 шт.", "LYSODREN 500 mg, tablets, 100 pcs"),
    "PANTHEC 20 MG 28 ENT.TABLET": (
        "PANTHEC 20 мг, кишечнорастворимые таблетки, 28 шт.",
        "PANTHEC 20 mg, gastro-resistant tablets, 28 pcs",
    ),
    "ISOFLUDEM 100 ML SISE": ("ISOFLUDEM, флакон, 100 мл", "ISOFLUDEM, bottle, 100 ml"),
    # лог 1056: модель испортила бренд (BIOSEL → OSEL)
    "RINGER LAKTAT BIOSEL ENJEKTABL SOL. 500 ML SETLI SISE": (
        "RINGER LAKTAT BIOSEL, раствор для инъекций, флакон, с системой, 500 мл",
        "RINGER LAKTAT BIOSEL, solution for injection, bottle, with set, 500 ml",
    ),
    "VOCHERON 8 MG/4 ML IM/IV ENJEKSIYONLUK/INFUZYONLUK COZELTI": (
        "VOCHERON 8 мг/4 мл, раствор для инъекций и инфузий (в/м, в/в)",
        "VOCHERON 8 mg/4 ml, solution for injection/infusion (IM/IV)",
    ),
    "MEDOTILIN 1000 MG/4 ML IM/IV ENJEKSIYONLUK COZELTI ICEREN 5 AMPUL": (
        "MEDOTILIN 1000 мг/4 мл, раствор для инъекций (в/м, в/в), 5 ампул",
        "MEDOTILIN 1000 mg/4 ml, solution for injection (IM/IV), 5 ampoules",
    ),
    "PIMREVA 200 MG VE 50 MG FILM KAPLI TABLET (56 TABLET)": (
        "PIMREVA 200 мг + 50 мг, таблетки, покрытые плёночной оболочкой, 56 шт.",
        "PIMREVA 200 mg + 50 mg, film-coated tablets, 56 pcs",
    ),
    "KEDAY XR 300 MG UZATILMIS SALIMLI 30 TABLET": (
        "KEDAY XR 300 мг, таблетки пролонгированного высвобождения, 30 шт.",
        "KEDAY XR 300 mg, prolonged-release tablets, 30 pcs",
    ),
    "ESPEROCT 500 IU ENJEKSIYONLUK COZELTI HAZIRLAMAK ICIN TOZ VE COZUCU (1 FLAKON)": (
        "ESPEROCT 500 МЕ, порошок для приготовления раствора для инъекций, с растворителем, 1 флакон",
        "ESPEROCT 500 IU, powder for solution for injection, with solvent, 1 vial",
    ),
    "TRELEGY ELLIPTA 100/62,5/25 MCG KULLANIMA HAZIR INHALASYON TOZU 30 ADET": (
        "TRELEGY ELLIPTA 100/62,5/25 мкг, порошок для ингаляций, 30 шт.",
        "TRELEGY ELLIPTA 100/62.5/25 mcg, inhalation powder, 30 pcs",
    ),
    # «ICEREN FLAKON (1 FLAKON)» — флакон не повторяется
    "TIROXAN 12,5 MG/50 ML IV INFUZYON ICIN KONSANTRE COZELTI ICEREN FLAKON (1 FLAKON)": (
        "TIROXAN 12,5 мг/50 мл, концентрат для приготовления раствора для инфузий, 1 флакон",
        "TIROXAN 12.5 mg/50 ml, concentrate for solution for infusion, 1 vial",
    ),
    # «TAB» — часть бренда, а не сокращение формы
    "OLFREX EASY TAB 10 MG 28 AGIZDA DAGILAN TABLET": (
        "OLFREX EASY TAB 10 мг, таблетки, диспергируемые в полости рта, 28 шт.",
        "OLFREX EASY TAB 10 mg, orodispersible tablets, 28 pcs",
    ),
    # «24 … (24 TABLET)» давало «24 шт., 24 шт.»
    "FLEXTRA 400 MG 24 FILM KAPLI TABLET (24 TABLET)": (
        "FLEXTRA 400 мг, таблетки, покрытые плёночной оболочкой, 24 шт.",
        "FLEXTRA 400 mg, film-coated tablets, 24 pcs",
    ),
}


@pytest.mark.parametrize("source", PILOT3_TITLES)
def test_pilot3_forms_are_covered_by_title_template(source):
    ru, en = PILOT3_TITLES[source]
    assert build_medicine_title(source) == {"ru": ru, "en": en}


@pytest.mark.parametrize(
    "source",
    [
        # «500» без единицы перед «(20 TABLET)» — то ли доза, то ли фасовка
        "KLACID MR 500 DEGISTIRILMIS SALIM TABLET (20 TABLET)",
    ],
)
def test_ambiguous_medicine_name_is_left_to_model(source):
    assert build_medicine_title(source) is None


@pytest.mark.parametrize(
    "source",
    [
        "B6 VIGEN 250 MG 30 TABLET",  # цифра внутри бренда — не дозировка
        "RINGER BIOSEL ENJEKTABL SOL. 1000 ML SETSIZ SISE",  # «SOL.» — не бренд
        "EMARAY IV ENJEKSIYONLUK COZELTI ICEREN FLAKON 20 ML",  # «ICEREN» — не бренд
        "ECOPIRIN 100 MG 30 ENTERIK TABLET",  # «gastro-resistant tablets» — не категория «gastro»
        *PILOT3_TITLES,
    ],
)
def test_template_title_is_not_rejected_by_validator(source):
    title = build_medicine_title(source)
    report = _reasons(source, title["ru"], title["en"])

    assert "title" not in report.rejected_fields, report.reasons


# ── Турецкий оригинал названия (external_data["source_name"]) ──
# Прод 20.10.2026: у 119 из 13 033 лекарств name уже переведён или обрезан, а
# применение AI пишет в name RU-название — шаблон строится только из турецкого.

DISAVER = "DISAVER 50 MG FILM KAPLI TABLET (28 TABLET)"
DISAVER_RU = "DISAVER 50 MG ФИЛЬМ-КАПЛИ ТАБЛЕТКИ"
DISAVER_BARCODE = "8699536090170"


def _equivalents(text, barcode=DISAVER_BARCODE):
    return {"attributes": {"barcode": barcode, "source_tabs": {"equivalents": {"text": text}}}}


@pytest.mark.parametrize(
    "text",
    [
        # Текущая вёрстка: строка названия, под ней «BARKOD <код>»; сам препарат — среди аналогов.
        f"SERTRALIN 50 MG 28 TABLET\nBARKOD 8699546090114\n{DISAVER}\nBARKOD {DISAVER_BARCODE}",
        f"{DISAVER}\nBarkod: {DISAVER_BARCODE}\nATC Kodu: N06AB06",
        f"SERTRALIN 50 MG 28 TABLET\nBARKOD\n8699546090114\n{DISAVER}\nBARKOD\n{DISAVER_BARCODE}",
    ],
)
def test_source_name_is_found_in_equivalents_by_own_barcode(text):
    assert equivalents_source_name(_equivalents(text)) == DISAVER


@pytest.mark.parametrize(
    "external_data",
    [
        _equivalents("SERTRALIN 50 MG 28 TABLET\nBARKOD 8699546090114"),  # своего штрихкода нет
        _equivalents(f"{DISAVER}\nBARKOD {DISAVER_BARCODE}", barcode=""),
        {"attributes": {"barcode": DISAVER_BARCODE}},
        None,
    ],
)
def test_equivalents_without_own_barcode_give_nothing(external_data):
    assert equivalents_source_name(external_data) == ""


def test_medicine_source_name_prefers_stored_then_untouched_name_then_equivalents():
    equivalents = _equivalents(f"{DISAVER}\nBARKOD {DISAVER_BARCODE}")

    assert medicine_source_name("Дисавер 50 мг", {**equivalents, "source_name": "DISAVER 50 MG"}) == (
        "DISAVER 50 MG", "source_name",
    )
    assert medicine_source_name("DISAVER 50 MG 28 TABLET", equivalents) == ("DISAVER 50 MG 28 TABLET", "name")
    assert medicine_source_name(DISAVER_RU, equivalents) == (DISAVER, "equivalents")
    assert medicine_source_name("MOUNJARO 7", equivalents) == (DISAVER, "equivalents")
    # Турецкого названия нет нигде — остаётся name, нужен перескрейп.
    assert medicine_source_name(DISAVER_RU, {}) == (DISAVER_RU, "name")


@pytest.mark.parametrize(
    "name,expected",
    [(DISAVER, True), (DISAVER_RU, False), ("MOUNJARO 7", False), ("DERMOVATE %0,05", True), ("", False)],
)
def test_looks_like_source_name(name, expected):
    assert looks_like_source_name(name) is expected


def _medicine_with(name, external_data, slug):
    category, _ = Category.objects.get_or_create(slug="source-name-medicines", defaults={"name": "Медицина"})
    medicine = MedicineProduct.objects.create(
        name=name, slug=slug, category=category, external_data=external_data
    )
    medicine.refresh_from_db()
    return medicine


def test_template_is_built_from_equivalents_when_name_is_translated():
    medicine = _medicine_with(DISAVER_RU, _equivalents(f"{DISAVER}\nBARKOD {DISAVER_BARCODE}"), "disaver-ru")
    generator = _generator(RecordingLLM())

    input_data = generator._collect_input_data(medicine.base_product)
    code_fields = generator._build_medicine_code_fields(input_data, allow_llm=False)

    assert input_data["name"] == DISAVER
    assert code_fields["title"] == build_medicine_title(DISAVER)
    assert code_fields["title"]["ru"] == "DISAVER 50 мг, таблетки, покрытые плёночной оболочкой, 28 шт."


def test_template_title_is_validated_against_turkish_source_not_translated_name():
    medicine = _medicine_with(DISAVER_RU, _equivalents(f"{DISAVER}\nBARKOD {DISAVER_BARCODE}"), "disaver-check")
    title = build_medicine_title(DISAVER)
    validator = SemanticValidator()

    report = validator.validate(
        medicine.base_product, generated_titles=title, dynamic_attributes=[]
    )
    # Фасовка источника («28 TABLET») обязательна и для названия от модели.
    no_pack = validator.validate(
        medicine.base_product,
        generated_titles={"ru": "DISAVER 50 мг, таблетки, покрытые плёночной оболочкой"},
        dynamic_attributes=[],
    )

    assert report.reasons == []
    assert no_pack.reasons == ["title_identity_lost"]


def test_first_ai_title_keeps_turkish_name_in_source_name():
    medicine = _medicine_with(DISAVER, {"source": "ilacfiyati"}, "disaver-apply")
    product = medicine.base_product
    applier = AIResultApplier()

    applier.apply_to_product(product, {"generated_title": "DISAVER 50 мг, таблетки, 28 шт."})
    product.refresh_from_db()
    applier.apply_to_product(product, {"generated_title": "DISAVER 50 мг, таблетки, покрытые оболочкой, 28 шт."})

    product.refresh_from_db()
    medicine.refresh_from_db()
    assert product.name == medicine.name == "DISAVER 50 мг, таблетки, покрытые оболочкой, 28 шт."
    # Второе применение не затирает оригинал прежним RU-названием.
    assert product.external_data["source_name"] == medicine.external_data["source_name"] == DISAVER
    assert product.external_data["source"] == "ilacfiyati"


@pytest.mark.parametrize("name", [DISAVER_RU, "MOUNJARO 7"])
def test_translated_or_truncated_name_is_not_kept_as_source_name(name):
    medicine = _medicine_with(name, {}, f"broken-{abs(hash(name)) % 10**6}")

    AIResultApplier().apply_to_product(medicine.base_product, {"generated_title": "DISAVER 50 мг, 28 шт."})

    medicine.base_product.refresh_from_db()
    assert "source_name" not in medicine.base_product.external_data


def test_reprocessing_of_applied_medicine_rebuilds_template_and_passes_validation():
    # До 20.10.2026: после применения name = RU-название, шаблон не строился,
    # и копия названия уходила в модерацию (title_source_translated).
    medicine = _medicine_with(DISAVER, {}, "disaver-reprocess")
    product = medicine.base_product
    title = build_medicine_title(DISAVER)
    AIResultApplier().apply_to_product(product, {"generated_title": title["ru"]})
    product.refresh_from_db()
    generator = _generator(RecordingLLM())

    input_data = generator._collect_input_data(product)
    code_fields = generator._build_medicine_code_fields(input_data, allow_llm=False)
    report = SemanticValidator().validate(product, generated_titles=title, dynamic_attributes=[])

    assert product.name == title["ru"]
    assert input_data["name"] == DISAVER
    assert code_fields["title"] == title
    assert report.reasons == []


def test_paragraph_batch_keys_use_brand_of_turkish_original():
    # Обработка маскирует бренд из турецкого оригинала — пакет обязан строить те же ключи.
    from apps.ai.services.medicine_paragraph_batch import iter_missing_paragraphs

    paragraph = "DISAVER'i çocukların göremeyeceği yerde saklayınız ve ambalajında muhafaza ediniz."
    MedicineProduct.objects.create(
        name="Дисавер 50 мг, таблетки, 28 шт.",  # бренд из RU-названия не совпал бы с источником
        slug="batch-source-name",
        is_active=True,
        external_data={
            "source_name": DISAVER,
            "attributes": {"source_tabs": {"storage_conditions": {"text": paragraph}}},
        },
    )

    paragraphs = [paragraph for paragraph, _pk in iter_missing_paragraphs()]

    assert paragraphs == [normalize_paragraph(paragraph, "DISAVER")]
    assert paragraphs[0].startswith(f"{BRAND_TOKEN}'i ")


def test_coverage_report_counts_title_template_by_turkish_original():
    # После массового AI name — RU-название; отчёт считает шаблон, как обработка.
    from io import StringIO

    from django.core.management import call_command

    for slug, external_data in (
        ("coverage-source-name", {"source_name": DISAVER}),
        ("coverage-equivalents", _equivalents(f"{DISAVER}\nBARKOD {DISAVER_BARCODE}")),
        ("coverage-no-source", {}),  # турецкого названия нет — шаблон не строится
    ):
        MedicineProduct.objects.create(name=DISAVER_RU, slug=slug, is_active=True, external_data=external_data)
    out = StringIO()

    call_command("medicine_reference_coverage", stdout=out)

    assert build_medicine_title(DISAVER_RU) is None
    assert "Название по шаблону: 2 из 3" in out.getvalue()


def test_medicine_source_names_command_reports_and_records_equivalents():
    from io import StringIO

    from django.core.management import call_command

    from apps.catalog.models import Product

    found = _medicine_with(DISAVER_RU, _equivalents(f"{DISAVER}\nBARKOD {DISAVER_BARCODE}"), "cmd-found")
    stored = _medicine_with("MOUNJARO 7", {"source_name": "MOUNJARO 7,5 MG/0,5 ML 4 KALEM"}, "cmd-stored")
    missing = _medicine_with("KLAMOKS BID 400/57 СУСПЕНЗИЯ 100 МЛ", {}, "cmd-missing")
    Product.objects.filter(pk=missing.base_product.pk).update(
        external_url="https://ilacfiyati.com/ilaclar/klamoks-bid"
    )
    _medicine_with(DISAVER, {}, "cmd-fine")  # нормальное название в отчёт не попадает

    out = StringIO()
    call_command("medicine_source_names", "--dry-run", stdout=out)
    report = out.getvalue()
    found.base_product.refresh_from_db()

    assert "name переведён или обрезан: 3" in report
    assert f"{found.base_product.pk}\tequivalents\t{DISAVER_RU!r} → {DISAVER!r}\n" in report
    assert f"{stored.base_product.pk}\tsource_name\t" in report
    assert "Турецкое название без перескрейпа: 2 (source_name 1, вкладка аналогов 1)" in report
    assert "Нужен перескрейп по URL: 1" in report
    assert "https://ilacfiyati.com/ilaclar/klamoks-bid" in report
    assert "source_name" not in found.base_product.external_data  # dry-run ничего не пишет

    call_command("medicine_source_names", stdout=StringIO())

    found.base_product.refresh_from_db()
    found.refresh_from_db()
    assert found.base_product.external_data["source_name"] == found.external_data["source_name"] == DISAVER
    assert found.base_product.name == DISAVER_RU  # name не меняется
