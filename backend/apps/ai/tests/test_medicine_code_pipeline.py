"""Лекарства: справочные поля, МНН, название и разделы — кодом и памятью переводов."""

import json
from types import SimpleNamespace

import pytest

from apps.ai.models import AIProcessingLog, AITranslationMemory
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.medicine_memory import (
    BRAND_TOKEN,
    INN_NAMESPACE,
    PARAGRAPH_NAMESPACE,
    normalize_paragraph,
    translate_active_ingredient,
)
from apps.ai.services.medicine_reference import translate_reference_field, translate_volume
from apps.ai.services.medicine_title import build_medicine_title, paragraph_brand
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
    from apps.ai.management.commands.medicine_paragraph_batch import Command

    for name, slug, suffix in (("MAJEZIK 100 MG 15 FILM TABLET", "batch-majezik", "MAJEZIK'i"),
                               ("PAROL 500 MG 20 TABLET", "batch-parol", "PAROL'ü")):
        MedicineProduct.objects.create(
            name=name, slug=slug,
            external_data={"attributes": {"source_tabs": {"before_use_warnings": {"text": _branded(suffix)}}}},
        )

    assert list(Command()._missing_paragraphs({"limit_products": 0})) == [
        normalize_paragraph(_branded("MAJEZIK'i"), "MAJEZIK")
    ]


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
