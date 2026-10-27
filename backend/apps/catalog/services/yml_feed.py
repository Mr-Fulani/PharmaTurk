"""
YML-фид (Yandex Market Language) для ВК Маркета и Яндекс.Маркета.

Фид собирается потоком: товары читаются пачками по ``BATCH_SIZE`` с заранее
загруженными доменными записями, фото, вариантами и атрибутами, XML пишется
по одному <offer>. Так память не растёт с размером каталога и нет запросов
на каждый товар.

Полный каталог и корневые категории собирает задача ``catalog.generate_yml_feeds``
в файлы хранилища (``YMLFeedSnapshot``) — эндпоинт отдаёт готовый файл. Фид больше
лимитов ВК (8 МБ / 15 000 товаров) делится на части ``?part=N``.
Подкатегории эндпоинт отдаёт потоком на лету (``iter_yml_feed``), без деления.
Лекарства в фиды не попадают (решение владельца, ``BLOCKED_PRODUCT_TYPES``).

Особенности фида:
- Категории ВК берутся из таблицы VKCategoryMapping по типу товара и полу
  (Admin → Маппинги категорий ВК).
- Описание — обычным текстом (HTML из карточки снимается), характеристики (материал,
  вес, страна…) — в описании, без кодов поставщика; в конце — ссылка на карточку
  сайта (utm для ВК).
- Варианты (решение владельца 27.10.2026): у каждого варианта group_id = id товара,
  цвет (и размер) — в названии и в <param name="Цвет">/<param name="Размер">.
  ВК принимает не больше двух свойств, поэтому других <param> нет.
- Медиа: все изображения из галереи (ProductImage) и первое видео.
"""
from __future__ import annotations

import logging
import re
import tempfile
import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import Iterator

from django.conf import settings
from django.core.files import File
from django.db.models import Prefetch
from django.utils import timezone

from ..models import Category, Product
from ..models_vk import VKCategoryMapping, YMLFeedSnapshot
from .source_offer_catalog_projection import resolve_source_offer_catalog_availability

logger = logging.getLogger(__name__)

BATCH_SIZE = 500

# Лимиты импорта YML в ВК (vk.com/faq21697): файл до 8 МБ и до 15 000 товаров.
# Больший фид делится на части; запас к 8 МБ — на расхождение МБ/MiB у ВК.
MAX_PART_BYTES = 7_500_000
MAX_PART_OFFERS = 15_000

# Решение владельца 27.10.2026: лекарства не выкладываем ни в один фид
# (ни раздел, ни полный каталог), пока он не разрешит. БАДы и медтехника — можно.
BLOCKED_PRODUCT_TYPES = ("medicines",)
BLOCKED_ROOT_SLUGS = ("medicines",)

# Запасной маппинг, если в БД нет записи для (product_type, пол) и (product_type, «любой»).
# Те же пути, что ставит миграция 0229; предпочтительный способ — Admin → Маппинги категорий ВК.
_FALLBACK_VK_MAP = {
    "clothing":          "Гардероб > Женщинам",
    "shoes":             "Гардероб > Мужчинам > Обувь",
    "jewelry":           "Гардероб > Женщинам > Аксессуары",
    "electronics":       "Смартфоны и гаджеты",
    "furniture":         "Дом и дача > Мебель",
    "books":             "Книги и журналы",
    "perfumery":         "Парфюмерия",
    "supplements":       "Витамины, БАДы и пищевые добавки",
    "medical_equipment": "Медицинские изделия и расходные материалы",
    "tableware":         "Дом и дача > Посуда и товары для кухни",
    "accessories":       "Гардероб > Женщинам > Аксессуары",
    "incense":           "Ароматерапия",
    "sports":            "Спортивная одежда",
    "auto_parts":        "Запчасти",
    "headwear":          "Гардероб > Мужчинам > Аксессуары",
    "underwear":         "Гардероб > Женщинам",
    "islamic_clothing":  "Гардероб > Женщинам",
}

FEED_GENDERS = ("men", "women", "kids")

MAX_DESCRIPTION_CHARS = 3000
VK_LINK_UTM = "utm_source=vk&utm_medium=market"
_CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)
# Характеристики с кодами поставщика: «Артикул», «Код товара», «Штрихкод», «SKU»…
_SUPPLIER_CODE_RE = re.compile(r"артикул|код|штрих|sku|barcode|gtin|mpn", re.IGNORECASE)


def load_vk_mapping() -> dict[tuple[str, str], str]:
    """
    Маппинг (product_type, пол) → путь категории ВК: записи БД поверх fallback.
    Пол "" — запись для товаров без пола и унисекс.
    """
    mapping = {(product_type, ""): path for product_type, path in _FALLBACK_VK_MAP.items()}
    for m in VKCategoryMapping.objects.all():
        mapping[(m.product_type, m.gender or "")] = m.vk_category_path
    return mapping


def vk_category_path(vk_map, product_type: str, gender: str, category_name: str) -> str:
    product_type = (product_type or "other").lower()
    return (
        vk_map.get((product_type, gender or ""))
        or vk_map.get((product_type, ""))
        or f"Товары > {category_name}"
    )


def feed_site_url() -> str:
    """Адрес сайта для ссылок на товары и относительных путей картинок."""
    return (getattr(settings, "FRONTEND_SITE_URL", "") or getattr(settings, "SITE_URL", "")).rstrip("/")


def root_category_slug(product_type: str) -> str:
    """Slug корневой категории для product_type: medical_equipment → medical-equipment."""
    return (product_type or "").replace("_", "-")


def _blocked_category_ids() -> set[int]:
    from ..views import _get_category_ids_with_descendants

    return _get_category_ids_with_descendants(list(BLOCKED_ROOT_SLUGS))


def is_blocked_feed_key(category_slug: str) -> bool:
    """Фид раздела отключён (лекарства и их подкатегории)."""
    if not category_slug:
        return False
    return Category.objects.filter(slug=category_slug, id__in=_blocked_category_ids()).exists()


def prepared_feed_keys() -> list[str]:
    """Фиды, которые собираются заранее: активные корневые категории и полный каталог ("")."""
    roots = list(
        Category.objects.filter(parent__isnull=True, is_active=True)
        .exclude(slug__in=BLOCKED_ROOT_SLUGS)
        .order_by("sort_order", "name")
        .values_list("slug", flat=True)
    )
    return roots + [""]


def is_prepared_feed_key(category_slug: str) -> bool:
    if not category_slug:
        return True
    return (
        Category.objects.filter(slug=category_slug, parent__isnull=True, is_active=True)
        .exclude(slug__in=BLOCKED_ROOT_SLUGS)
        .exists()
    )


# ----------------------------------------------------------------------
# Загрузка товаров пачками
# ----------------------------------------------------------------------

def _has_relation(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
    except Exception:
        return False
    return True


def _domain_relations() -> dict[str, tuple[str, type]]:
    """product_type → (accessor на Product, доменная модель)."""
    relations = {}
    for rel in Product._meta.related_objects:
        domain_type = getattr(rel.related_model, "_domain_product_type", "")
        if rel.one_to_one and domain_type:
            relations[domain_type] = (rel.get_accessor_name(), rel.related_model)
    return relations


def _domain_queryset(model):
    prefetches = []
    if _has_relation(model, "images"):
        prefetches.append("images")
    if _has_relation(model, "variants"):
        variant_model = model._meta.get_field("variants").related_model
        variants = variant_model.objects.filter(is_active=True)
        if _has_relation(variant_model, "images"):
            variants = variants.prefetch_related("images")
        prefetches.append(Prefetch("variants", queryset=variants, to_attr="yml_active_variants"))
    if _has_relation(model, "dynamic_attributes"):
        prefetches.append(
            Prefetch(
                "dynamic_attributes",
                queryset=_attribute_values_queryset(),
            )
        )
    return model.objects.prefetch_related(*prefetches)


def _attribute_values_queryset():
    from ..models import ProductAttributeValue

    return ProductAttributeValue.objects.select_related("attribute_key").prefetch_related(
        "attribute_key__translations"
    )


def _attach_domain_items(products: list) -> None:
    """
    Кладёт в prod.yml_domain_item доменную запись (ShoeProduct и т.п.) или сам Product.

    Одним запросом на тип товара вместо Product.domain_item на каждый товар.
    """
    relations = _domain_relations()
    by_type: dict[str, list] = {}
    for prod in products:
        prod.yml_domain_item = prod
        pt = (prod.product_type or "").replace("-", "_")
        if pt in relations:
            by_type.setdefault(pt, []).append(prod)

    for pt, prods in by_type.items():
        _accessor, model = relations[pt]
        items = _domain_queryset(model).filter(base_product_id__in=[p.id for p in prods])
        by_base = {item.base_product_id: item for item in items}
        for prod in prods:
            prod.yml_domain_item = by_base.get(prod.id, prod)


def _feed_scope(category_slug: str):
    """(категории для <categories>, товары) для фида."""
    from ..views import _get_category_ids_with_descendants

    product_prefetches = ["images"]
    if bool(getattr(settings, "SOURCE_OFFER_CATALOG_PROJECTION_ENABLED", False)) and bool(
        getattr(settings, "SOURCE_OFFER_VERIFICATION_ENABLED", False)
    ):
        product_prefetches.append("source_offers")

    blocked_ids = _blocked_category_ids()
    products = (
        Product.objects
        .filter(is_active=True)
        .exclude(medicine_item__import_restricted_countries__gt="")  # не рекламируем (TD-024)
        .exclude(product_type__in=BLOCKED_PRODUCT_TYPES)
        .exclude(category_id__in=blocked_ids)
        .select_related("brand", "category", "price_info")
        .prefetch_related(*product_prefetches)
        .distinct()
    )

    if not category_slug:
        return Category.objects.filter(is_active=True).exclude(id__in=blocked_ids), products

    all_cat_ids = _get_category_ids_with_descendants([category_slug])

    # Рекурсивно добавляем всех родителей чтобы дерево было валидным
    all_relevant_ids = set(all_cat_ids)
    current_ids = list(
        Category.objects.filter(id__in=all_cat_ids)
        .values_list("parent_id", flat=True)
    )
    while any(pid for pid in current_ids if pid is not None):
        parent_ids = [
            pid for pid in current_ids
            if pid is not None and pid not in all_relevant_ids
        ]
        if not parent_ids:
            break
        all_relevant_ids.update(parent_ids)
        current_ids = list(
            Category.objects.filter(id__in=parent_ids)
            .values_list("parent_id", flat=True)
        )

    cats = Category.objects.filter(id__in=all_relevant_ids, is_active=True)
    return cats, products.filter(category_id__in=all_cat_ids)


def _iter_product_batches(products) -> Iterator[list]:
    last_id = 0
    while True:
        batch = list(products.filter(id__gt=last_id).order_by("id")[:BATCH_SIZE])
        if not batch:
            return
        last_id = batch[-1].id
        _attach_domain_items(batch)
        yield batch


# ----------------------------------------------------------------------
# XML
# ----------------------------------------------------------------------

def _xml(el) -> str:
    return ET.tostring(el, encoding="unicode")


FEED_TAIL = "</offers></shop></yml_catalog>"


def _feed_head(cats) -> str:
    """Всё до первого <offer>: магазин, валюта, дерево категорий."""
    date = timezone.now().replace(microsecond=0).isoformat()
    pieces = ["<?xml version='1.0' encoding='utf-8'?>\n", f'<yml_catalog date="{date}"><shop>']

    for tag, text in (("name", "Mudaroba"), ("company", "Mudaroba"), ("url", "https://mudaroba.com/")):
        el = ET.Element(tag)
        el.text = text
        pieces.append(_xml(el))

    currencies = ET.Element("currencies")
    ET.SubElement(currencies, "currency", id="RUB", rate="1")
    pieces.append(_xml(currencies))

    # Дерево категорий
    categories_el = ET.Element("categories")
    for cat in cats.only("id", "parent_id", "name").iterator():
        cat_el = ET.SubElement(categories_el, "category", id=str(cat.id))
        if cat.parent_id:
            cat_el.set("parentId", str(cat.parent_id))
        cat_el.text = cat.name
    pieces.append(_xml(categories_el))
    pieces.append("<offers>")
    return "".join(pieces)


class _GenderResolver:
    """
    Пол товара для категории ВК — как фильтр «Пол» на сайте: поле товара,
    затем пол категории или её родителей, затем пол по названию/slug категории.
    """

    def __init__(self):
        self._categories = {
            row[0]: row[1:]
            for row in Category.objects.values_list("id", "parent_id", "gender", "slug", "name")
        }
        self._cache: dict[int, str] = {}

    def category_gender(self, category_id) -> str:
        from ..views import _infer_gender_values_from_text

        if category_id in self._cache:
            return self._cache[category_id]
        gender, node, seen = "", category_id, set()
        while node and node not in seen and not gender:
            seen.add(node)
            parent_id, own_gender, slug, name = self._categories.get(node, (None, "", "", ""))
            inferred = _infer_gender_values_from_text(slug, name) - {"unisex"}
            gender = own_gender or (inferred.pop() if len(inferred) == 1 else "")
            node = parent_id
        self._cache[category_id] = gender or ""
        return self._cache[category_id]

    def product_gender(self, prod, domain_item) -> str:
        gender = (
            getattr(prod, "gender", "")
            or getattr(domain_item, "gender", "")
            or self.category_gender(prod.category_id)
        )
        return gender if gender in FEED_GENDERS else ""


def _iter_offers(products, site_url: str) -> Iterator[str]:
    """<offer> по одному, в порядке id товара."""
    vk_map = load_vk_mapping()
    genders = _GenderResolver()
    exported_ids: set[str] = set()  # защита от дублей
    for batch in _iter_product_batches(products):
        for prod in batch:
            offers_el = ET.Element("offers")
            _add_product_offers(offers_el, prod, site_url, vk_map, exported_ids, genders)
            for offer in offers_el:
                yield _xml(offer)


def iter_yml_feed(category_slug: str = "", site_url: str | None = None) -> Iterator[str]:
    """
    Фид по кускам строк. Пустой slug — полный каталог; slug категории — она и её потомки.
    Без деления на части — для подкатегорий, которые отдаются на лету.
    """
    site_url = (site_url or feed_site_url()).rstrip("/")
    cats, products = _feed_scope(category_slug)
    yield _feed_head(cats)
    buffer: list[str] = []
    for offer in _iter_offers(products, site_url):
        buffer.append(offer)
        if len(buffer) >= 200:
            yield "".join(buffer)
            buffer.clear()
    yield "".join(buffer) + FEED_TAIL


def _add_product_offers(offers_el, prod, site_url, vk_map, exported_ids: set[str], genders) -> None:
    domain_item = getattr(prod, "yml_domain_item", prod)
    variants = list(getattr(domain_item, "yml_active_variants", None) or [])
    gender = genders.product_gender(prod, domain_item)

    if not variants:
        oid = str(prod.id)
        if oid in exported_ids:
            return
        exported_ids.add(oid)
        offer = create_offer(
            offers_el, prod, site_url, vk_map,
            domain_item=domain_item,
            has_variants=False,
            gender=gender,
        )
        add_params_to_description(offer, prod, domain_item)
        return

    # Каждый вариант — отдельный offer с group_id товара и ТОЛЬКО своими изображениями.
    for variant in variants:
        offer_id = f"{prod.id}v{variant.id}"
        if offer_id in exported_ids:
            continue
        exported_ids.add(offer_id)
        offer = create_offer(
            offers_el, prod, site_url, vk_map,
            domain_item=domain_item,
            offer_id=offer_id,
            variant=variant,
            has_variants=True,
            gender=gender,
        )
        add_params_to_description(offer, prod, domain_item, variant)


def _variant_price_rub(variant):
    """Цена варианта в рублях с наценкой — как на сайте (цена варианта бывает в лирах)."""
    price = getattr(variant, "price", None)
    if not price:
        return None
    currency = (getattr(variant, "currency", "") or "RUB").upper()
    if currency == "RUB":
        return price
    from ..utils.currency_converter import currency_converter

    _, _, with_margin = currency_converter.convert_price(
        Decimal(str(price)), currency, "RUB", apply_margin=True
    )
    return with_margin


def create_offer(parent, prod, site_url, vk_map,
                 domain_item=None, offer_id=None, variant=None, has_variants=False, gender=""):
    """
    Строит элемент <offer> с правильным порядком тегов.

    Порядок (согласно спецификации YML):
    url > price > currencyId > categoryId > market_category >
    picture(s) > video > store > pickup > delivery >
    name > vendor > vendorCode > description
    """
    oid = offer_id or str(prod.id)
    is_available = prod.is_available
    # Product rows from iter_yml_feed() have source_offers prefetched when projection
    # is enabled. Disallow fallback queries so a large feed cannot regress to N+1.
    source_projection = resolve_source_offer_catalog_availability(
        prod,
        allow_queries=False,
    )
    if source_projection is not None:
        is_available = is_available and source_projection.is_available
    if variant:
        is_available = variant.is_available and prod.is_available
        if source_projection is not None:
            is_available = is_available and source_projection.is_available

    offer = ET.SubElement(
        parent, "offer",
        id=oid,
        available="true" if is_available else "false",
    )
    if variant:
        # Все варианты товара — одна группа: ВК/Яндекс объединяют их в карточку с вариантами.
        offer.set("group_id", str(prod.id))

    # 1. URL
    p_type = (prod.product_type or "other").lower().replace("_", "-")
    ET.SubElement(offer, "url").text = f"{site_url}/product/{p_type}/{prod.slug}"

    # 2. Цена
    v_price = _variant_price_rub(variant) if variant else None
    raw_price = v_price or prod.get_price_in_currency("RUB") or prod.price or 0
    price_dec = Decimal(str(raw_price)).quantize(Decimal("0.01"))
    price_str = (
        str(int(price_dec))
        if price_dec == price_dec.to_integral_value()
        else str(price_dec)
    )
    ET.SubElement(offer, "price").text = price_str

    # 3. Валюта
    ET.SubElement(offer, "currencyId").text = "RUB"

    # 4. Категория
    cat_name = prod.category.name if prod.category else "Товар"
    if prod.category_id:
        ET.SubElement(offer, "categoryId").text = str(prod.category_id)

    # 5. Категория ВК (из Admin-маппинга по типу и полу или fallback)
    ET.SubElement(offer, "market_category").text = vk_category_path(
        vk_map, prod.product_type, gender, cat_name
    )

    # 6. Изображения
    # Стратегия: максимум картинок для каждого offer без дублей.
    #   Вариант: сначала фото варианта (его цвет), потом галерея родителя (студио, детали).
    #   Без вариантов: всё что есть у родительского товара.
    added_images: set[str] = set()

    def _add_image(url: str):
        """Добавляет <picture> если URL не пустой и не дубль."""
        if url and url not in added_images:
            ET.SubElement(offer, "picture").text = url
            added_images.add(url)

    def _resolve_url(raw: str) -> str:
        # file.url в R2 уже абсолютный, локально — /media/...
        if not raw:
            return ""
        return raw if raw.startswith("http") else f"{site_url}{raw}"

    if variant:
        # 1. Главное фото варианта
        if getattr(variant, "main_image_file", None):
            _add_image(_resolve_url(variant.main_image_file.url))
        elif getattr(variant, "main_image", ""):
            _add_image(_resolve_url(variant.main_image))

        # 2. Галерея варианта
        if hasattr(variant, "images"):
            for vi in variant.images.all():
                _add_image(vi.image_url or (
                    _resolve_url(vi.image_file.url) if vi.image_file else ""
                ))

    # 3. Главное фото родительского товара (и для варианта, и без)
    # Приоритет: domain_item.main_image → prod.main_image
    domain = domain_item if (domain_item and domain_item is not prod) else None
    if domain and getattr(domain, "main_image", ""):
        _add_image(_resolve_url(domain.main_image))
    elif domain and getattr(domain, "main_image_file", None):
        _add_image(_resolve_url(domain.main_image_file.url))
    elif getattr(prod, "main_image", ""):
        _add_image(_resolve_url(prod.main_image))
    elif getattr(prod, "main_image_file", None):
        _add_image(_resolve_url(prod.main_image_file.url))

    # 4. Галерея: сначала domain_item.images (ShoeProductImage и т.п.), потом prod.images
    for image_source in ([domain, prod] if domain else [prod]):
        if image_source and hasattr(image_source, "images"):
            for pi in image_source.images.all():
                _add_image(pi.image_url or (
                    _resolve_url(pi.image_file.url) if pi.image_file else ""
                ))

    # 7. Видео (первое доступное из domain_item или prod)
    video_found = False
    for image_source in ([domain, prod] if domain else [prod]):
        if video_found:
            break
        if image_source and hasattr(image_source, "images"):
            for pi in image_source.images.all():
                v_url = getattr(pi, "video_url", "") or (
                    _resolve_url(pi.video_file.url)
                    if getattr(pi, "video_file", None) else ""
                )
                if v_url:
                    ET.SubElement(offer, "video").text = v_url
                    video_found = True
                    break

    # 8. Флаги доставки
    ET.SubElement(offer, "store").text = "true"
    ET.SubElement(offer, "pickup").text = "true"
    ET.SubElement(offer, "delivery").text = "true"

    # 9. Название; у варианта — с цветом и размером («Кепка LC WAIKIKI, хаки»)
    variant_options = _variant_options(variant) if variant else []
    ET.SubElement(offer, "name").text = _offer_name(prod.name or "", variant_options)

    # 10. Бренд
    if prod.brand:
        ET.SubElement(offer, "vendor").text = prod.brand.name

    # 10a. Артикул = id оффера («538» или «538v1»): не меняется между сборками,
    # по нему ВК должен узнавать уже загруженный товар при повторном импорте.
    ET.SubElement(offer, "vendorCode").text = oid

    # 11. Описание — характеристики и ссылку на сайт допишет add_params_to_description
    desc_el = ET.SubElement(offer, "description")
    desc_el.text = (html_to_text(prod.description) or prod.name or "")[:MAX_DESCRIPTION_CHARS]

    # 12. Свойства варианта — по ним ВК различает варианты в группе
    for param_name, value in variant_options:
        ET.SubElement(offer, "param", name=param_name).text = value

    return offer


def _feed_color(raw_color: str) -> str:
    """
    Цвет по-русски по словарю сайта. Непереведённый цвет («Kum», «Vizon») не выводим:
    лучше без цвета, чем турецкое слово в названии и свойствах ВК.
    """
    from ..utils.tr_vocab import translate_turkish_color

    raw_color = (raw_color or "").strip()
    translated = translate_turkish_color(raw_color, "ru")
    if translated:
        return translated
    return raw_color if _CYRILLIC_RE.search(raw_color) else ""


def _variant_options(variant) -> list[tuple[str, str]]:
    """[("Цвет", "Хаки"), ("Размер", "42")] — цвет по-русски, как на сайте."""
    options = []
    color = _feed_color(getattr(variant, "color", "") or "")
    if color:
        options.append(("Цвет", color))
    size = str(getattr(variant, "size", "") or "").strip()
    if size:
        options.append(("Размер", size))
    return options


def _offer_name(base_name: str, variant_options: list[tuple[str, str]]) -> str:
    name = base_name.strip()
    extras = []
    for param_name, value in variant_options:
        if value.lower() in name.lower():
            continue
        extras.append(value[:1].lower() + value[1:] if param_name == "Цвет" else value)
    if extras:
        suffix = ", " + ", ".join(extras)
        name = name[: 150 - len(suffix)].rstrip(" ,") + suffix
    return name[:150]


_HTML_LINE_BREAK_RE = re.compile(r"<br\s*/?>|</?(?:p|div|h[1-6]|tr|ul|ol)(?:\s[^>]*)?>", re.IGNORECASE)
_HTML_LIST_ITEM_RE = re.compile(r"<li(?:\s[^>]*)?>", re.IGNORECASE)
# Только похожее на тег: «5 < 7 > 3» в тексте не трогаем.
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^<>]*>")


def html_to_text(value: str | None) -> str:
    """
    Описание с HTML (<p>, <br>, <li>…) → обычный текст для ВК: абзацы — переносами,
    пункты списка — «• », сущности (&nbsp;, &amp;) — символами. ВК теги не рендерит.
    """
    import html

    text = _HTML_LINE_BREAK_RE.sub("\n", value or "")
    text = _HTML_LIST_ITEM_RE.sub("\n• ", text)
    text = html.unescape(_HTML_TAG_RE.sub("", text)).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _translated_key_name(key_obj) -> str:
    # translations загружены заранее (_attribute_values_queryset) — без запросов
    by_locale = {t.locale: t.name for t in key_obj.translations.all()}
    return by_locale.get("ru") or by_locale.get("en") or key_obj.slug


def add_params_to_description(offer, prod, domain_item, variant=None):
    """
    Характеристики — в конец описания в читаемом виде: ВК принимает не больше
    двух <param>, их занимают свойства варианта (цвет, размер).
    """
    desc_el = offer.find("description")
    if desc_el is None:
        return

    specs: list[str] = []

    # Вес
    if prod.weight_value:
        specs.append(f"Вес: {prod.weight_value} {prod.weight_unit}")

    # Страна
    if prod.country_of_origin:
        specs.append(f"Страна производства: {prod.country_of_origin}")

    # Параметры варианта
    if variant:
        if getattr(variant, "size", ""):
            specs.append(f"Размер: {variant.size}")
        color = dict(_variant_options(variant)).get("Цвет")
        if color:
            specs.append(f"Цвет: {color}")
        # Артикул поставщика (variant.sku) не показываем: наш артикул — <vendorCode>.

    # Динамические атрибуты из domain_item
    if domain_item and hasattr(domain_item, "dynamic_attributes"):
        seen = {s.split(":")[0] for s in specs}  # не дублируем
        for attr in domain_item.dynamic_attributes.all():
            # Всегда берём русское название ключа — независимо от языка сервера
            attr_name = _translated_key_name(attr.attribute_key)
            attr_value = attr.value_ru or attr.value
            if _SUPPLIER_CODE_RE.search(attr_name or ""):
                continue  # коды поставщика — внутренние
            if attr_name and attr_value and attr_name not in seen:
                specs.append(f"{attr_name}: {attr_value}")
                seen.add(attr_name)

    specs_text = "\n\nХарактеристики:\n" + "\n".join(f"• {s}" for s in specs) if specs else ""

    # Ссылка на карточку: ВК не показывает <url> из фида, поэтому — в конце описания.
    # При лимите сокращается сам текст, затем характеристики; ссылка остаётся целой.
    link = f"\n\nПодробнее и заявка: {offer.findtext('url')}?{VK_LINK_UTM}"
    specs_text = specs_text[: MAX_DESCRIPTION_CHARS - len(link)]
    body = (desc_el.text or "")[: MAX_DESCRIPTION_CHARS - len(link) - len(specs_text)].rstrip()
    desc_el.text = body + specs_text + link


# ----------------------------------------------------------------------
# Готовые файлы фида
# ----------------------------------------------------------------------

def _write_parts(category_slug: str) -> list[tuple]:
    """
    Пишет фид во временные файлы частями не больше MAX_PART_BYTES и MAX_PART_OFFERS.

    Каждая часть — целый YML с тем же деревом категорий. Возвращает
    [(файл, офферов, байт), …]; файлы закрывает вызывающий.
    """
    cats, products = _feed_scope(category_slug)
    head = _feed_head(cats).encode("utf-8")
    tail = FEED_TAIL.encode("utf-8")
    parts: list[list] = []

    def start_part():
        fh = tempfile.TemporaryFile()
        fh.write(head)
        parts.append([fh, 0, len(head)])
        return parts[-1]

    current = start_part()
    for offer in _iter_offers(products, feed_site_url()):
        data = offer.encode("utf-8")
        full = current[1] >= MAX_PART_OFFERS or current[2] + len(data) + len(tail) > MAX_PART_BYTES
        if current[1] and full:
            current[0].write(tail)
            current[2] += len(tail)
            current = start_part()
        current[0].write(data)
        current[1] += 1
        current[2] += len(data)
    current[0].write(tail)
    current[2] += len(tail)
    return [tuple(part) for part in parts]


def _delete_snapshot(snapshot: YMLFeedSnapshot) -> None:
    if snapshot.file:
        snapshot.file.storage.delete(snapshot.file.name)
    snapshot.delete()


def generate_feed_files(category_slug: str = "") -> list[YMLFeedSnapshot]:
    """
    Собирает фид раздела (частями), кладёт файлы в хранилище и переключает YMLFeedSnapshot.

    Старый файл части удаляется только после того, как запись указывает на новый, —
    в любой момент эндпоинт отдаёт целый фид. Лишние части прежней сборки удаляются.
    """
    started = timezone.now()
    stamp = started.strftime("%Y%m%d-%H%M%S")
    name = category_slug or "catalog"
    parts = _write_parts(category_slug)
    snapshots = []
    try:
        for number, (fh, offers_count, size_bytes) in enumerate(parts, start=1):
            fh.seek(0)
            snapshot, _ = YMLFeedSnapshot.objects.get_or_create(category_slug=category_slug, part=number)
            old_name = snapshot.file.name if snapshot.file else ""
            snapshot.file.save(f"{name}-{stamp}-{number}.xml", File(fh, name=f"{name}.xml"), save=False)
            snapshot.generated_at = started
            snapshot.offers_count = offers_count
            snapshot.size_bytes = size_bytes
            snapshot.save()
            if old_name and old_name != snapshot.file.name:
                snapshot.file.storage.delete(old_name)
            snapshots.append(snapshot)
    finally:
        for fh, _, _ in parts:
            fh.close()

    for stale in YMLFeedSnapshot.objects.filter(category_slug=category_slug, part__gt=len(parts)):
        _delete_snapshot(stale)
    logger.info(
        "YML-фид %s: %s частей, %s офферов, %s байт за %.1f с",
        name, len(snapshots), sum(s.offers_count for s in snapshots),
        sum(s.size_bytes for s in snapshots), (timezone.now() - started).total_seconds(),
    )
    return snapshots


def remove_unlisted_feeds(keys: list[str]) -> int:
    """Удаляет готовые фиды разделов, которых больше нет в списке (выключены или заблокированы)."""
    stale = list(YMLFeedSnapshot.objects.exclude(category_slug__in=keys))
    for snapshot in stale:
        _delete_snapshot(snapshot)
    return len(stale)


def iter_snapshot_file(snapshot: YMLFeedSnapshot, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    """
    Читает готовый файл фида кусками.

    S3File из django-storages при чтении скачивает объект целиком в память,
    поэтому для R2 читаем тело ответа boto потоком.
    """
    storage = snapshot.file.storage
    bucket = getattr(storage, "bucket", None)
    if bucket is not None:
        key = storage._normalize_name(snapshot.file.name)
        body = bucket.Object(key).get()["Body"]
        try:
            yield from body.iter_chunks(chunk_size)
        finally:
            body.close()
        return
    with storage.open(snapshot.file.name, "rb") as fh:
        while chunk := fh.read(chunk_size):
            yield chunk
