"""Ложные тревоги проверок абзацев лекарств, найденные в круге 7 модерации (27.11.2026)."""

from apps.ai.services.medicine_fact_check import strip_proper_name_lines
from apps.ai.services.medicine_memory import paragraph_problems
from apps.ai.services.medicine_paragraph_check import concepts
from apps.catalog.product_semantics import looks_untranslated_turkish


def test_cikardiysaniz_is_not_heart_norlevo():
    source = "Vajinal diyafragm veya gebelik önleyici bariyeriniz yerinden oynadıysa ya da onu erken çıkardıysanız;"
    assert "heart" not in concepts(source, "tr")
    assert paragraph_problems(
        source,
        "Если ваша вагинальная диафрагма или барьерное средство контрацепции сместилось или вы извлекли его раньше времени;",
        "If your vaginal diaphragm or contraceptive barrier has shifted or you removed it early;",
    ) == []


def test_cardiac_words_still_heart():
    assert "heart" in concepts("Taşikardi ve kardiyak aritmi görülebilir.", "tr")
    assert "heart" in concepts("Kalp yetmezliği", "tr")


def test_conceive_is_pregnancy_proluton():
    source = "Doğal yoldan gebe kalamama (Sarı cisim (corpus luteum) yetmezliğine bağlı infertilite"
    assert "pregnancy" in concepts("Inability to conceive naturally", "en")
    assert paragraph_problems(
        source,
        "Невозможность забеременеть естественным путём (бесплодие, связанное с недостаточностью жёлтого тела (corpus luteum)",
        "Inability to conceive naturally (infertility due to corpus luteum insufficiency",
    ) == []


def test_concept_mismatch_still_caught():
    # Чужой абзац о хранении вместо абзаца о беременности — по-прежнему брак.
    assert "concept_mismatch" in paragraph_problems(
        "Hamilelik döneminde doktorunuza danışınız. Gebelik sırasında kullanmayınız.",
        "Храните при комнатной температуре.",
        "Store at room temperature.",
    )


def test_city_in_caps_is_address_precedex():
    text = (
        "Владелец регистрационного удостоверения:\nMeditera İthalat ve İhracat A.Ş.\n5758 Sok., No:4/C-E\n"
        "Karabağlar - İZMİR\nТел.: 0 232 237 59 49"
    )
    assert "Karabağlar - İZMİR" not in strip_proper_name_lines(text)
    assert not looks_untranslated_turkish(strip_proper_name_lines(text))


def test_untranslated_line_still_caught():
    assert looks_untranslated_turkish(strip_proper_name_lines("Bulantı ve kusma görülebilir. Doktorunuza danışınız."))
