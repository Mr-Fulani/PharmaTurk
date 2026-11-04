"""БАДы: состав, способ применения, предупреждения и хранение — из памяти переводов."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.ai.models import AITranslationMemory
from apps.ai.services import supplement_content as sc
from apps.ai.services import supplement_memory as sm
from apps.ai.services.translation_memory import remember

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
        assert kwargs["system_prompt"] == sm.LINE_SYSTEM_PROMPT
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
        "Parti No ve Tavsiye Edilen Tüketim Tarihi (TETT) kutunun alt yüzündedir."
    )
    parts = sm.section_parts({"product_info": text})

    assert parts == {
        "excipients": ["Kapsül (hidroksipropilmetil selüloz)", "topaklanmayı önleyici (yağ asitlerinin magnezyum tuzları)"],
        "warnings": ["Serin ve kuru yerde muhafaza ediniz."],
    }


@pytest.mark.django_db
def test_new_parts_are_translated_once_and_then_come_from_memory():
    sections = {"product_info": PRODUCT_INFO, "ingredients": INGREDIENTS}
    llm = _translator_llm()

    blocks, usage = sm.translate_blocks(sections, llm)

    assert llm.generate_content.call_count == 1  # 8 частей — один запрос (до 10)
    assert usage["cost_usd"] == pytest.approx(0.0002)
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


def test_block_texts_drop_claims_in_both_languages_and_go_before_disclaimer():
    blocks = sm.SupplementBlocks(
        ru={"composition": ["вода", "витамин C"], "warnings": ["Не превышайте порцию", "Не применяется для лечения болезней."]},
        en={"composition": ["water", "vitamin C"], "warnings": ["Do not exceed the portion", "Not used to treat diseases."]},
    )

    ru = sc.memory_block_texts(blocks, "ru")
    description = sc.build_description(["SOLGAR — пищевая добавка."], "ru", blocks=ru)

    assert ru == ["Состав: вода, витамин C.", "Предупреждения: Не превышайте порцию."]
    assert sc.memory_block_texts(blocks, "en")[1] == "Warnings: Do not exceed the portion."
    assert description.endswith(f"<p>Предупреждения: Не превышайте порцию.</p><p>{sc.DISCLAIMER['ru']}</p>")


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
        if kwargs["system_prompt"] == sm.LINE_SYSTEM_PROMPT:
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
    assert result["cost_usd"] == pytest.approx(0.0005)
    assert result["rule_content"]["description_source"] == "llm+memory"
    assert result["rule_content"]["supplement"]["memory"]["translated"] == 8
