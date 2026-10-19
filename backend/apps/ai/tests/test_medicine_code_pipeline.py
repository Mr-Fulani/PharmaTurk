"""Лекарства: справочные поля, МНН, название и разделы — кодом и памятью переводов."""

import json
from types import SimpleNamespace

import pytest

from apps.ai.models import AIProcessingLog, AITranslationMemory
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.medicine_memory import (
    INN_NAMESPACE,
    PARAGRAPH_NAMESPACE,
    translate_active_ingredient,
)
from apps.ai.services.medicine_reference import translate_reference_field, translate_volume
from apps.ai.services.medicine_title import build_medicine_title
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
                "ru": {k: self.paragraphs[v][0] for k, v in items.items() if v in self.paragraphs},
                "en": {k: self.paragraphs[v][1] for k, v in items.items() if v in self.paragraphs},
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
        "Ограниченный белый рецепт", "Restricted white prescription",
    )
    assert translate_reference_field("prescription_type", "BEYAZ REÇETE")[0] == "Белый рецепт"
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
    assert content["ru"]["prescription_type"] == "Белый рецепт"
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


def test_title_template_from_structured_name():
    assert build_medicine_title("MAJEZIK 100 MG 15 FILM TABLET") == {
        "ru": "MAJEZIK 100 мг, таблетки, покрытые плёночной оболочкой, 15 шт.",
        "en": "MAJEZIK 100 mg, film-coated tablets, 15 pcs",
    }
    assert build_medicine_title("ZINCO SURUP 150 ML") == {"ru": "ZINCO, сироп, 150 мл", "en": "ZINCO, syrup, 150 ml"}
    # Незнакомое слово после бренда — шаблон не строится, название даст модель.
    assert build_medicine_title("X 5 MG KARISIM") is None


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
    assert log.generated_title == "MAJEZIK 100 мг, таблетки, покрытые плёночной оболочкой, 15 шт."
    translations = log.extracted_attributes["translations_data"]
    assert translations["ru"]["volume"] == "15 таблеток"
    assert translations["ru"]["active_ingredient"] == "Флурбипрофен"
    assert translations["ru"]["shelf_life"] == "24 месяца"
    assert translations["ru"]["usage_instructions"].startswith("Принимайте по 500 мг")
    assert float(log.cost_usd) == pytest.approx(0.003)  # карточка + МНН + абзацы
    report = SemanticValidator().validate_log(log)
    assert "medicine_fact_mismatch" not in report.reasons
    assert "title" not in report.rejected_fields


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

    class FakeFiles:
        def create(self, file, purpose):
            uploaded["jsonl"] = file[1].decode("utf-8")
            return SimpleNamespace(id="file-in")

        def content(self, file_id):
            if file_id == "file-in":
                return SimpleNamespace(text=uploaded["jsonl"])
            request = json.loads(uploaded["jsonl"].splitlines()[0])
            items = json.loads(request["body"]["messages"][1]["content"].split("\n\n", 1)[1])
            answer = {
                "ru": {k: TRANSLATIONS[v][0].strip() for k, v in items.items()},
                "en": {k: TRANSLATIONS[v][1].strip() for k, v in items.items()},
            }
            row = {
                "custom_id": request["custom_id"],
                "response": {"body": {
                    "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}],
                    "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
                }},
            }
            return SimpleNamespace(text=json.dumps(row))

    class FakeBatches:
        def create(self, **kwargs):
            uploaded["batch"] = kwargs
            return SimpleNamespace(id="batch-1")

        def retrieve(self, batch_id):
            return SimpleNamespace(
                status="completed", input_file_id="file-in", output_file_id="file-out", request_counts=None
            )

    class FakeClient:
        model = "gpt-4o-mini"
        pricing = {"gpt-4o-mini": {"input": 0.15, "output": 0.60}}
        client = SimpleNamespace(files=FakeFiles(), batches=FakeBatches())

        @staticmethod
        def _parse_json_response(raw):
            return json.loads(raw)

    monkeypatch.setattr(medicine_paragraph_batch, "LLMClient", FakeClient)
    out = StringIO()

    call_command("medicine_paragraph_batch", "submit", stdout=out)
    call_command("medicine_paragraph_batch", "collect", "batch-1", stdout=out)

    request = json.loads(uploaded["jsonl"].splitlines()[0])
    assert list(json.loads(request["body"]["messages"][1]["content"].split("\n\n", 1)[1]).values()) == [
        PARA_C.strip()
    ]
    assert uploaded["batch"]["completion_window"] == "24h"
    assert lookup(PARAGRAPH_NAMESPACE, [PARA_C.strip()])[PARA_C.strip()]["ru"].startswith("Во время беременности")
    assert "записано абзацев: 1" in out.getvalue()


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
