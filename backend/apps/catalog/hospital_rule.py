"""Правило «похоже на больничный препарат» (TD-047, docs/HOSPITAL_MEDICINES.md).

Одна чистая функция без базы: по турецкому названию источника и коду ATC говорит, к какой
группе больничных относится лекарство, или возвращает пустую строку. Группы — те же, что в
отборах 26.10.2026 (по названию) и 13.11.2026 (по ATC): растворы для капельниц и питания,
диализ, радиофармпрепараты, кожные пробы и аллергены, диагностические средства.

Правило осторожное: лучше не отметить больничный, чем отметить обычное аптечное лекарство.
Поэтому сюда НЕ входят: «инфузионный» препарат с действующим веществом (антибиотик, онкология,
наркоз), альбумин, масла и смеси лечебного питания (приём внутрь), препарат без розничной цены сам
по себе. Ампулы соли и электролитов отмечаются только при коде ATC B05X (так было в обоих отборах);
без кода ATC по одному названию ампулы не отмечаются.
"""
import re

GROUP_INFUSION = "Растворы для капельниц и питания"
GROUP_DIALYSIS = "Диализ и гемофильтрация"
GROUP_RADIO = "Радиофармпрепараты"
GROUP_ALLERGEN = "Кожные пробы и аллергены"
GROUP_DIAGNOSTIC = "Диагностические средства"

_TR_ASCII = str.maketrans("İIŞĞÜÖÇışğüöçâîû", "IISGUOCisguocaiu")

_DIALYSIS_NAME = re.compile(r"PERITON\w*\s+DIY?ALIZ|HEMODIYALIZ|HEMOFILTRASYON|HEMODIYAFILTRASYON")
_RADIO_NAME = re.compile(r"RADYOFARMASOTIK|RADYONUKLID|JENERATOR|\b[MG]BQ\b")
_PRICK_NAME = re.compile(r"PRIC?K\s+TEST")
# Флакон или пакет с системой для капельницы / без неё — так источник пишет только растворы.
_INFUSION_SET = re.compile(r"\bSET(LI|SIZ)\b")
# Раствор-носитель: глюкоза, соль, Рингер, маннитол, аминокислоты, жировая эмульсия…
_CARRIER = re.compile(
    r"DEKSTROZ|DEXTROSE|SODYUM\s+KLORUR|\bNACL\b|RINGER|MANNITOL|IZOTONIK|AMINO\s*ASIT|"
    r"LIPID\s*EMULSIYON|ELEKTROLIT|DEKSTRAN|HIDROKSIETIL\s+NISASTA"
)
_INFUSION_WORD = re.compile(r"INFUZ|INFUS|IRR?IGASYON")
# Признак введения в вену / большой тары — для групп ATC B05A, B05B, B05C, B05X.
_PARENTERAL = re.compile(
    r"INFUZ|INFUS|IRR?IGASYON|PERFUZYON|ENJEKSIYON|INJECTION|EMULSIYON|\bTORBA\b|\bSISE\b|"
    r"\bI\.?\s?V\b|\bVIAL|\bAMP"
)
# Формы для приёма дома: с ними название больничным раствором не считаем.
_HOME_FORM = re.compile(
    r"\bORAL\b|TABLET|KAPSUL|\bSASE\b|SURUP|DAMLA|SPREY|\bBURUN\b|NAZAL|\bGOZ\b|GARGARA|\bOIL\b|\bKREM\b|\bJEL\b"
)
_VOLUME_ML = re.compile(r"(\d{2,5})\s*ML\b")


def _normalize(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").translate(_TR_ASCII).upper()).strip()


def _large_volume(name: str) -> bool:
    return any(int(volume) >= 100 for volume in _VOLUME_ML.findall(name))


def hospital_medicine_group(name, atc_code="") -> str:
    """Группа больничных препаратов или ``""``, если лекарство на больничное не похоже.

    ``name`` — название в источнике (турецкое), ``atc_code`` — код ATC, если известен.
    """
    name = _normalize(name)
    atc = re.sub(r"[^A-Z0-9]", "", _normalize(atc_code))
    home_form = bool(_HOME_FORM.search(name))

    if atc.startswith(("B05D", "B05Z")) or _DIALYSIS_NAME.search(name):
        return GROUP_DIALYSIS
    if atc.startswith(("V09", "V10")) or _RADIO_NAME.search(name):
        return GROUP_RADIO
    if _PRICK_NAME.search(name) or (atc.startswith("V01AA") and "TABLET" not in name):
        return GROUP_ALLERGEN
    if atc.startswith("V04C"):
        return GROUP_DIAGNOSTIC

    if home_form:
        return ""
    if atc.startswith(("B05A", "B05B", "B05C", "B05X")):
        if atc.startswith("B05AA01"):  # альбумин: решение владельца не принято
            return ""
        return GROUP_INFUSION if _PARENTERAL.search(name) or _INFUSION_SET.search(name) else ""
    if atc:
        # У лекарства другой группы ATC «инфузия» в названии — это способ введения
        # действующего вещества (антибиотик, онкология), а не раствор для капельницы.
        return ""
    if _INFUSION_SET.search(name):
        return GROUP_INFUSION
    if _CARRIER.search(name) and (_INFUSION_WORD.search(name) or _large_volume(name)):
        return GROUP_INFUSION
    return ""


def looks_like_hospital_medicine(name, atc_code="") -> bool:
    return bool(hospital_medicine_group(name, atc_code))
