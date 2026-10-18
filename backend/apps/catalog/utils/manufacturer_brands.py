"""Нормализация производителей лекарств и БАДов в бренды каталога.

Производитель приходит из ilacfiyati в разных написаниях одной фирмы:
«Abdi İbrahim», «Abdi İbrahim İlaç Sanayi Ve Ticaret A.Ş», «Farma-Tek» / «Farmatek»,
«Sanofi» / «Sanofi Pasteur Aşı». `manufacturer_key_tokens` сводит написание к словам
без юридической формы; одна фирма = самый короткий набор слов, с которого начинаются
остальные (`BrandResolver`). `manufacturer_display_name` убирает юридическую форму
из названия, сохраняя регистр оригинала.
"""
import re
import unicodedata

OTHER_BRAND_SLUG = "other"
PHARMA_CATEGORY_SLUGS = frozenset({"medicines", "supplements", "medical-equipment"})
MANUFACTURER_BRAND_SOURCE = "manufacturer"

_TR_ASCII = str.maketrans({
    "İ": "i", "I": "i", "ı": "i",
    "Ç": "c", "ç": "c", "Ğ": "g", "ğ": "g",
    "Ö": "o", "ö": "o", "Ş": "s", "ş": "s", "Ü": "u", "ü": "u",
})

# Юридическая форма и вид деятельности в хвосте названия: убираются и из ключа,
# и из отображаемого имени («Nobel İlaç Sanayii Ve Ticaret A.Ş.» → «Nobel İlaç»).
_LEGAL_TAIL = frozenset({
    "as", "anonim", "sirketi", "sirket", "san", "sanayi", "sanayii", "ve", "tic",
    "ticaret", "ltd", "sti", "limited", "holding", "kimya", "ithalat", "ihracat",
    "pazarlama", "dis", "turizm", "egitim", "inc", "gmbh", "ag", "co", "llc",
    "corp", "&",
})
# Родовые слова: убираются только из ключа, чтобы «Nobel İlaç» и «Nobel»
# считались одной фирмой, но в имени бренда остаются как у источника.
_GENERIC_TAIL = frozenset({
    "ilac", "ilaclari", "saglik", "urunleri", "gida", "medikal", "kozmetik",
})


def _fold(value: str) -> str:
    value = (value or "").translate(_TR_ASCII)
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch)).lower()


def _token_key(token: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _fold(token))


def _dot_parts(token: str) -> list[str]:
    """«Tic.Ltd.Şti» → три слова; подряд идущие буквы — одна аббревиатура
    («A.Ş.» → «AŞ», «Tic.A.Ş» → «Tic», «AŞ»)."""
    parts, letters = [], ""
    for part in (p for p in token.split(".") if _token_key(p)):
        if len(_token_key(part)) == 1:
            letters += part
            continue
        if letters:
            parts.append(letters)
            letters = ""
        parts.append(part)
    if letters:
        parts.append(letters)
    return parts or [token]


def _is_stop(token: str, stop: frozenset) -> bool:
    if _token_key(token) in stop | {""}:
        return True
    return all(_token_key(p) in stop for p in _dot_parts(token))


def _strip_tail(tokens: list[str], stop: frozenset) -> list[str]:
    tokens = list(tokens)
    while len(tokens) > 1 and _is_stop(tokens[-1], stop):
        tokens.pop()
    return tokens


def manufacturer_display_name(raw: str) -> str:
    tokens = (raw or "").split()
    return " ".join(_strip_tail(tokens, _LEGAL_TAIL)).strip(" ,.-")


def manufacturer_key_tokens(raw: str) -> tuple:
    tokens = _strip_tail((raw or "").split(), _LEGAL_TAIL | _GENERIC_TAIL)
    return tuple(_token_key(p) for t in tokens for p in _dot_parts(t) if _token_key(p))


def manufacturer_brand_key(raw: str) -> str:
    return "".join(manufacturer_key_tokens(raw))


def supplement_manufacturer(external_data) -> str:
    """У БАДов нет поля manufacturer — производитель лежит в атрибутах источника."""
    attrs = (external_data or {}).get("attributes") if isinstance(external_data, dict) else None
    value = attrs.get("manufacturer") if isinstance(attrs, dict) else None
    return str(value).strip() if value else ""


def is_pharma_brand(brand) -> bool:
    slugs = set(brand.category_slugs or []) | {brand.primary_category_slug or ""}
    return brand.slug != OTHER_BRAND_SLUG and bool(slugs & PHARMA_CATEGORY_SLUGS)


# Разные фирмы с общим первым словом (MSD ≠ Merck İlaç, Fresenius Kabi ≠ Fresenius
# Medikal, Biogen ≠ Bio-Gen) и слишком общие корни — не поглощают длинные названия.
_NO_PREFIX_ROOTS = frozenset({("merck",), ("fresenius",), ("biogen",), ("turk",), ("nbt",)})


def root_tokens(tokens: tuple, known: set) -> tuple:
    """Самый короткий известный набор слов, с которого начинается название."""
    for size in range(1, len(tokens)):
        prefix = tokens[:size]
        if prefix in known and prefix not in _NO_PREFIX_ROOTS:
            return prefix
    return tokens


class BrandResolver:
    """Поиск бренда для производителя среди существующих.

    Фарм-бренды сопоставляются и по началу названия («Sanofi Pasteur Aşı» → Sanofi);
    остальные — только по точному ключу, чтобы «Apple Pharma» не попала в Apple.
    """

    def __init__(self, brands):
        self.exact = {}
        self.pharma = {}
        for brand in sorted(brands, key=lambda b: b.pk):
            if brand.slug == OTHER_BRAND_SLUG:
                continue
            tokens = manufacturer_key_tokens(brand.name)
            self.exact.setdefault("".join(tokens), brand)
            if is_pharma_brand(brand):
                self.pharma.setdefault(tokens, brand)

    def match(self, tokens: tuple):
        tokens = root_tokens(tokens, set(self.pharma))
        return self.pharma.get(tokens) or self.exact.get("".join(tokens))


def unique_brand_slug(name: str) -> str:
    from django.utils.text import slugify

    from apps.catalog.models import Brand

    base = slugify(_fold(name)) or "brand"
    slug, counter = base, 1
    while Brand.objects.filter(slug=slug).exists():
        counter += 1
        slug = f"{base}-{counter}"
    return slug


def ensure_brand_category(brand, category_slug: str) -> bool:
    """Добавить категорию бренду (без сохранения). True, если что-то изменилось."""
    changed = False
    if category_slug and category_slug not in (brand.category_slugs or []):
        brand.category_slugs = [*(brand.category_slugs or []), category_slug]
        changed = True
    if category_slug and not brand.primary_category_slug:
        brand.primary_category_slug = category_slug
        changed = True
    return changed


def create_manufacturer_brand(name: str, category_slug: str = ""):
    from apps.catalog.models import Brand

    return Brand.objects.create(
        name=name,
        slug=unique_brand_slug(name),
        category_slugs=[category_slug] if category_slug else [],
        primary_category_slug=category_slug,
        external_data={"source": MANUFACTURER_BRAND_SOURCE},
        is_active=True,
    )


def get_or_create_manufacturer_brand(raw: str, category_slug: str):
    """Бренд для производителя: существующий той же фирмы или новый."""
    from apps.catalog.models import Brand

    tokens = manufacturer_key_tokens(raw)
    name = manufacturer_display_name(raw)
    if not tokens or not name:
        return None
    brand = BrandResolver(Brand.objects.only("id", "name", "slug", "category_slugs", "primary_category_slug")).match(tokens)
    if brand is None:
        return create_manufacturer_brand(name, category_slug)
    brand = Brand.objects.get(pk=brand.pk)
    if ensure_brand_category(brand, category_slug):
        brand.save(update_fields=["category_slugs", "primary_category_slug", "updated_at"])
    return brand
