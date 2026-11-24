"""Номера автозапчастей: один вид записи для поиска и склейки источников.

«1K0 615 301 AA», «1k0-615-301aa» и «1K0615301AA» — один номер. Нормализованный
вид — верхний регистр, только латинские буквы и цифры (docs/AUTO_PARTS_AI_DESIGN.md).
"""

import re

from django.utils.text import slugify

_NOT_ALNUM = re.compile(r"[^A-Z0-9]")
# Турецкие и немецкие буквы артикулов и марок — латиницей («LEMFÖRDER», «CITROËN»);
# «Ё» — кириллическая буква, которой Aloparça пишет «CITROЁN».
_LATIN = str.maketrans("İIıŞşÇçĞğÖöÜüËëЁё", "IIiSsCcGgOoUuEeEe")


def normalize_part_number(value) -> str:
    """Артикул или OEM-номер без пробелов, дефисов и точек, в верхнем регистре."""
    return _NOT_ALNUM.sub("", str(value or "").translate(_LATIN).upper())


def vehicle_slug(value) -> str:
    """Марка или модель автомобиля для поиска и фильтра: «MERCEDES-BENZ» → ``mercedes-benz``."""
    return slugify(str(value or "").translate(_LATIN))[:64]
