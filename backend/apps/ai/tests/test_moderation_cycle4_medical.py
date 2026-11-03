"""Модерация, круг 4: разбор 56 медицинских записей 03.11.2026 — ложные тревоги проверок.

Примеры — логи прода (номер в комментарии). Рядом — настоящие ошибки из той же
очереди: проверки должны их ловить и дальше.
"""

import pytest

from apps.ai.services import supplement_content
from apps.ai.services.medicine_memory import section_paragraph_problems
from apps.ai.services.medicine_paragraph_check import concepts, item_problems
from apps.ai.services.medicine_title import paragraph_brand

# --- понятие «хранение» ---


def test_intestines_are_not_storage():
    # Лог 28893 (SAXENDA): «bağır-sakla-rı» засчитывалось как «saklayınız».
    assert "storage" not in concepts("Mide ve bağırsakları etkileyen yan etkiler", "tr")


@pytest.mark.parametrize("text", ["25°C altındaki oda sıcaklığında saklayınız.", "Buzdolabında saklanmalıdır."])
def test_storage_words_are_still_storage(text):
    assert "storage" in concepts(text, "tr")


# --- «en az»: частота побочного эффекта ---


def test_very_common_frequency_is_not_a_lost_lower_bound():
    # Логи 28903, 28907, 28914 (BLOXER, NEVIMOL): стандартная строка частоты ≥1/10.
    problems = item_problems(
        "Çok yaygın (En az 10 kişiden birini etkiler)",
        "Очень часто (могут возникать у 1 из 10 человек)",
        "Very common (may affect 1 in 10 people)",
    )
    assert "at_least_mismatch" not in problems


@pytest.mark.parametrize(
    "source, ru, en",
    [
        ("Tedaviye en az 14 gün devam ediniz.", "Продолжайте лечение 14 дней.", "Continue treatment for 14 days."),
        # Логи 28860, 28866, 30732 (HIZENTRA): потеряна нижняя граница загрузочной дозы.
        (
            "Doktorunuz en az 1-2,5 ml/kg vücut ağırlığı yükleme dozu verebilir.",
            "Врач может назначить нагрузочную дозу от 1 до 2,5 мл/кг массы тела.",
            "Your doctor may give a loading dose of 1-2.5 ml/kg body weight.",
        ),
    ],
)
def test_lost_lower_bound_is_still_caught(source, ru, en):
    assert "at_least_mismatch" in item_problems(source, ru, en)


# --- бренд внутри чужого слова ---


@pytest.mark.parametrize(
    "brand, source, ru, en",
    [
        # Лог 28746 (SEF): бренд находился в «Sefalosporinlere».
        (
            "SEF",
            "Sefalosporinlere alerjiniz varsa penisilinlere de alerjiniz olabilir.",
            "Если у вас аллергия на цефалоспорины, у вас может быть аллергия и на пенициллины.",
            "If you are allergic to cephalosporins, you may also be allergic to penicillins.",
        ),
        # Логи 28789, 28790 (OKSAPAR): бренд находился в «Enoksaparin».
        (
            "OKSAPAR",
            "Enoksaparin sodyum, heparinden elde edilen bir ilaçtır.",
            "Эноксапарин натрия — препарат, получаемый из гепарина.",
            "Enoxaparin sodium is a medicine obtained from heparin.",
        ),
    ],
)
def test_brand_inside_another_word_is_not_the_brand(brand, source, ru, en):
    assert section_paragraph_problems(source, ru, en, brand=brand) == []


# --- бренд абзацев: «%» и число в названии ---


@pytest.mark.parametrize(
    "name, brand",
    [
        # Логи 28762, 28935, 28940: «FLEBOGAMMA% %10 DIF» в переводе.
        ("FLEBOGAMMA% 10 DIF 10 G/100 ML IV INFUZYONLUK COZELTI", "FLEBOGAMMA"),
        ("VENIDARA% 5 KREM", "VENIDARA"),
        # Лог 28939: «72» — часть названия, за ним дозировка; без него number_mismatch в 20 абзацах.
        ("ERTES 72 1,5 MG 1 TABLET", "ERTES 72"),
        # Число с единицей — дозировка, число перед словом — по-прежнему не бренд абзацев (TD-030).
        ("MAJEZIK 100 MG 15 FILM TABLET", "MAJEZIK"),
        ("CAPD 18 STAY SAFE PERITON DIALIZ 2000 ML", "CAPD"),
        ("CALPOL 6 PLUS 250 MG/5 ML 150 ML SURUP", "CALPOL"),
    ],
)
def test_paragraph_brand_percent_and_name_number(name, brand):
    assert paragraph_brand(name) == brand


# --- БАДы: фасовка русскими словами ---


@pytest.mark.parametrize(
    "source, ru, en",
    [
        # Логи 28767, 28965, 28994: названия без турецкого источника — фасовка пропадала.
        ("SOVITAL RED CARPET TAKVIYE EDICI GIDA 60 капсул", "60 капсул", "60 capsules"),
        ("SUITENDO, пищевая добавка, 30 капсул", "30 капсул", "30 capsules"),
        ("Фолиевая кислота ANEVITA 90 таблеток", "90 таблеток", "90 tablets"),
    ],
)
def test_russian_pack_words_are_parsed(source, ru, en):
    pack = supplement_content.parse_pack(source)
    assert (pack.ru, pack.en) == (ru, en)


def test_brand_after_russian_words_is_the_brand():
    # Лог 28994 (ANEVITA): бренд не в начале названия — брался первый русский
    # «Фолиевая», и название стало «Фолиевая Фолиевая кислота».
    source = "Фолиевая кислота ANEVITA 90 таблеток"
    brand, from_model = supplement_content._brand("ANEVITA", source)
    assert (brand, from_model) == ("ANEVITA", True)
    pack = supplement_content.parse_pack(source)
    assert supplement_content.assemble_title(brand, "Фолиевая кислота", pack.ru, "ru") == (
        "ANEVITA Фолиевая кислота, 90 таблеток"
    )


def test_turkish_name_brand_still_must_be_the_start():
    # Турецкое название: бренд — только начало названия, как и раньше.
    assert supplement_content._brand("RED CARPET", "SOVITAL RED CARPET TAKVIYE EDICI GIDA 60 капсул") == (
        "SOVITAL", False
    )
