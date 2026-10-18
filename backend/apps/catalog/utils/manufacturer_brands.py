"""Нормализация производителей лекарств и БАДов в бренды каталога.

Производитель приходит из ilacfiyati в разных написаниях одной фирмы:
«Abdi İbrahim», «Abdi İbrahim İlaç Sanayi Ve Ticaret A.Ş», «Farma-Tek» / «Farmatek».
`manufacturer_brand_key` сводит их к одному ключу, `manufacturer_display_name`
убирает юридическую форму из названия, сохраняя регистр оригинала.
"""
import re
import unicodedata

OTHER_BRAND_SLUG = "other"

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

# Ручные склейки, которые не выводятся правилами (ключ → ключ).
MANUFACTURER_KEY_ALIASES = {
    "tebyurtdisindanilacteminibirimi": "teb",
    "pfizerpfe": "pfizer",
}


def _fold(value: str) -> str:
    value = (value or "").translate(_TR_ASCII)
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch)).lower()


def _token_key(token: str) -> str:
    return re.sub(r"[^a-z0-9&]", "", _fold(token))


def _strip_tail(tokens: list[str], stop: frozenset) -> list[str]:
    tokens = list(tokens)
    while len(tokens) > 1 and _token_key(tokens[-1]) in stop | {""}:
        tokens.pop()
    return tokens


def manufacturer_display_name(raw: str) -> str:
    tokens = (raw or "").split()
    return " ".join(_strip_tail(tokens, _LEGAL_TAIL)).strip(" ,.-")


def manufacturer_brand_key(raw: str) -> str:
    tokens = _strip_tail((raw or "").split(), _LEGAL_TAIL | _GENERIC_TAIL)
    key = "".join(_token_key(t) for t in tokens).replace("&", "")
    return MANUFACTURER_KEY_ALIASES.get(key, key)


def supplement_manufacturer(external_data) -> str:
    """У БАДов нет поля manufacturer — производитель лежит в атрибутах источника."""
    attrs = (external_data or {}).get("attributes") if isinstance(external_data, dict) else None
    value = attrs.get("manufacturer") if isinstance(attrs, dict) else None
    return str(value).strip() if value else ""


def build_brand_key_index(brands) -> dict:
    """Ключ → бренд (первый по id) для существующих брендов, без заглушки «Другое»."""
    index = {}
    for brand in sorted(brands, key=lambda b: b.pk):
        if brand.slug == OTHER_BRAND_SLUG:
            continue
        index.setdefault(manufacturer_brand_key(brand.name), brand)
    return index


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


def get_or_create_manufacturer_brand(raw: str, category_slug: str):
    """Бренд для производителя: существующий с тем же ключом или новый."""
    from apps.catalog.models import Brand

    key = manufacturer_brand_key(raw)
    name = manufacturer_display_name(raw)
    if not key or not name:
        return None
    brand = build_brand_key_index(Brand.objects.only("id", "name", "slug")).get(key)
    if brand is None:
        brand = Brand.objects.create(
            name=name,
            slug=unique_brand_slug(name),
            category_slugs=[category_slug],
            primary_category_slug=category_slug,
            is_active=True,
        )
        return brand
    brand = Brand.objects.get(pk=brand.pk)
    if ensure_brand_category(brand, category_slug):
        brand.save(update_fields=["category_slugs", "primary_category_slug", "updated_at"])
    return brand
