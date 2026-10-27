"""
YML-фид (Yandex Market Language) для ВК Маркета и Яндекс.Маркета.

Фид собирается потоком: товары читаются пачками по ``BATCH_SIZE`` с заранее
загруженными доменными записями, фото, вариантами и атрибутами, XML пишется
по одному <offer>. Так память не растёт с размером каталога и нет запросов
на каждый товар.

Полный каталог и корневые категории собирает задача ``catalog.generate_yml_feeds``
в файлы хранилища (``YMLFeedSnapshot``) — эндпоинт отдаёт готовый файл.
Подкатегории эндпоинт отдаёт потоком на лету (``iter_yml_feed``).

Особенности фида:
- Категории ВК берутся из таблицы VKCategoryMapping (Admin → Маппинги категорий ВК).
- Характеристики товара (цвет, размер, материал) вписываются в описание,
  а НЕ в отдельные <param> — это предотвращает «мусор» в названии в ВК.
- group_id намеренно отключён: с ним ВК автоматически дописывает атрибуты к названию.
- Медиа: все изображения из галереи (ProductImage) и первое видео.
"""
from __future__ import annotations

import logging
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

# Fallback-маппинг если в БД для product_type ещё нет записи.
# Обновляйте этот словарь ТОЛЬКО если не хотите использовать Admin.
# Предпочтительный способ — Admin → Маппинги категорий ВК.
_FALLBACK_VK_MAP = {
    "clothing":          "Одежда, обувь и аксессуары > Мужская одежда",
    "shoes":             "Одежда, обувь и аксессуары > Мужская обувь",
    "jewelry":           "Одежда, обувь и аксессуары > Украшения",
    "electronics":       "Электроника",
    "furniture":         "Мебель и интерьер > Мебель",
    "books":             "Книги",
    "perfumery":         "Красота и здоровье > Парфюмерия",
    "medicines":         "Красота и здоровье > Лекарственные препараты",
    "supplements":       "Красота и здоровье > Витамины, БАДы",
    "medical_equipment": "Красота и здоровье > Медицинская техника и оборудование",
    "tableware":         "Товары для дома > Посуда и кухня",
    "accessories":       "Одежда, обувь и аксессуары > Аксессуары",
    "incense":           "Красота и здоровье > Ароматерапия",
    "sports":            "Спорт и отдых",
    "auto_parts":        "Запчасти и автотовары",
    "headwear":          "Одежда, обувь и аксессуары > Мужская одежда > Аксессуары > Головные уборы > Кепки и бейсболки",
    "underwear":         "Одежда, обувь и аксессуары > Нижнее бельё",
    "islamic_clothing":  "Одежда, обувь и аксессуары > Мужская одежда",
}


def load_vk_mapping() -> dict[str, str]:
    """
    Загружает маппинг из БД и объединяет с fallback.
    Записи из БД имеют приоритет над fallback.
    """
    mapping = dict(_FALLBACK_VK_MAP)
    for m in VKCategoryMapping.objects.all():
        mapping[m.product_type] = m.vk_category_path
    return mapping


def feed_site_url() -> str:
    """Адрес сайта для ссылок на товары и относительных путей картинок."""
    return (getattr(settings, "FRONTEND_SITE_URL", "") or getattr(settings, "SITE_URL", "")).rstrip("/")


def root_category_slug(product_type: str) -> str:
    """Slug корневой категории для product_type: medical_equipment → medical-equipment."""
    return (product_type or "").replace("_", "-")


def prepared_feed_keys() -> list[str]:
    """Фиды, которые собираются заранее: активные корневые категории и полный каталог ("")."""
    roots = list(
        Category.objects.filter(parent__isnull=True, is_active=True)
        .order_by("sort_order", "name")
        .values_list("slug", flat=True)
    )
    return roots + [""]


def is_prepared_feed_key(category_slug: str) -> bool:
    if not category_slug:
        return True
    return Category.objects.filter(slug=category_slug, parent__isnull=True, is_active=True).exists()


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

    products = (
        Product.objects
        .filter(is_active=True)
        .exclude(medicine_item__import_restricted_countries__gt="")  # не рекламируем (TD-024)
        .select_related("brand", "category", "price_info")
        .prefetch_related(*product_prefetches)
        .distinct()
    )

    if not category_slug:
        return Category.objects.filter(is_active=True), products

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


def iter_yml_feed(category_slug: str = "", site_url: str | None = None) -> Iterator[str]:
    """
    Фид по кускам строк. Пустой slug — полный каталог; slug категории — она и её потомки.
    """
    site_url = (site_url or feed_site_url()).rstrip("/")
    vk_map = load_vk_mapping()
    cats, products = _feed_scope(category_slug)

    date = timezone.now().replace(microsecond=0).isoformat()
    yield "<?xml version='1.0' encoding='utf-8'?>\n"
    yield f'<yml_catalog date="{date}"><shop>'

    for tag, text in (("name", "Mudaroba"), ("company", "Mudaroba"), ("url", "https://mudaroba.com/")):
        el = ET.Element(tag)
        el.text = text
        yield _xml(el)

    currencies = ET.Element("currencies")
    ET.SubElement(currencies, "currency", id="RUB", rate="1")
    yield _xml(currencies)

    # Дерево категорий
    categories_el = ET.Element("categories")
    for cat in cats.only("id", "parent_id", "name").iterator():
        cat_el = ET.SubElement(categories_el, "category", id=str(cat.id))
        if cat.parent_id:
            cat_el.set("parentId", str(cat.parent_id))
        cat_el.text = cat.name
    yield _xml(categories_el)

    yield "<offers>"
    exported_ids: set[str] = set()  # защита от дублей
    for batch in _iter_product_batches(products):
        offers_el = ET.Element("offers")
        for prod in batch:
            _add_product_offers(offers_el, prod, site_url, vk_map, exported_ids)
        yield "".join(_xml(offer) for offer in offers_el)
    yield "</offers></shop></yml_catalog>"


def _add_product_offers(offers_el, prod, site_url, vk_map, exported_ids: set[str]) -> None:
    domain_item = getattr(prod, "yml_domain_item", prod)
    variants = list(getattr(domain_item, "yml_active_variants", None) or [])

    if not variants:
        oid = str(prod.id)
        if oid in exported_ids:
            return
        exported_ids.add(oid)
        offer = create_offer(
            offers_el, prod, site_url, vk_map,
            domain_item=domain_item,
            has_variants=False,
        )
        add_params_to_description(offer, prod, domain_item)
        return

    # Намеренно БЕЗ group_id — с ним ВК дописывает атрибуты в название.
    # Каждый вариант — отдельный offer с ТОЛЬКО своими изображениями.
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
                 domain_item=None, offer_id=None, variant=None, has_variants=False):
    """
    Строит элемент <offer> с правильным порядком тегов.

    Порядок (согласно спецификации YML):
    url > price > currencyId > categoryId > market_category >
    picture(s) > video > store > pickup > delivery >
    name > vendor > description
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

    # 5. Категория ВК (из Admin-маппинга или fallback)
    p_type_raw = (prod.product_type or "other").lower()
    market_cat = vk_map.get(
        p_type_raw,
        f"Товары > {cat_name}",
    )
    ET.SubElement(offer, "market_category").text = market_cat

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

    # 9. Название — ТОЛЬКО название, без атрибутов
    ET.SubElement(offer, "name").text = (prod.name or "")[:150]

    # 10. Бренд
    if prod.brand:
        ET.SubElement(offer, "vendor").text = prod.brand.name

    # 11. Описание — сохраняем место для характеристик (добавятся в add_params_to_description)
    desc_el = ET.SubElement(offer, "description")
    desc_el.text = (prod.description or prod.name or "")[:3000]

    return offer


def _translated_key_name(key_obj) -> str:
    # translations загружены заранее (_attribute_values_queryset) — без запросов
    by_locale = {t.locale: t.name for t in key_obj.translations.all()}
    return by_locale.get("ru") or by_locale.get("en") or key_obj.slug


def add_params_to_description(offer, prod, domain_item, variant=None):
    """
    Вместо тегов <param> (которые ВК дописывает в название) —
    добавляем характеристики прямо в конец описания в читаемом виде.
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
        if getattr(variant, "color", ""):
            specs.append(f"Цвет: {variant.color}")
        if getattr(variant, "sku", ""):
            specs.append(f"Артикул: {variant.sku}")

    # Динамические атрибуты из domain_item
    if domain_item and hasattr(domain_item, "dynamic_attributes"):
        seen = {s.split(":")[0] for s in specs}  # не дублируем
        for attr in domain_item.dynamic_attributes.all():
            # Всегда берём русское название ключа — независимо от языка сервера
            attr_name = _translated_key_name(attr.attribute_key)
            attr_value = attr.value_ru or attr.value
            if attr_name and attr_value and attr_name not in seen:
                specs.append(f"{attr_name}: {attr_value}")
                seen.add(attr_name)

    if specs:
        current_desc = desc_el.text or ""
        extra = "\n\nХарактеристики:\n" + "\n".join(f"• {s}" for s in specs)
        desc_el.text = (current_desc + extra)[:3000]


# ----------------------------------------------------------------------
# Готовые файлы фида
# ----------------------------------------------------------------------

def generate_feed_file(category_slug: str = "") -> YMLFeedSnapshot:
    """
    Собирает фид во временный файл, кладёт в хранилище и переключает YMLFeedSnapshot.

    Старый файл удаляется только после того, как запись указывает на новый, —
    в любой момент эндпоинт отдаёт целый фид.
    """
    started = timezone.now()
    offers_count = 0
    with tempfile.TemporaryFile() as fh:
        for chunk in iter_yml_feed(category_slug):
            offers_count += chunk.count("<offer ")
            fh.write(chunk.encode("utf-8"))
        size_bytes = fh.tell()
        fh.seek(0)

        snapshot, _ = YMLFeedSnapshot.objects.get_or_create(category_slug=category_slug)
        old_name = snapshot.file.name if snapshot.file else ""
        stamp = started.strftime("%Y%m%d-%H%M%S")
        snapshot.file.save(
            f"{category_slug or 'catalog'}-{stamp}.xml",
            File(fh, name=f"{category_slug or 'catalog'}.xml"),
            save=False,
        )

    snapshot.generated_at = started
    snapshot.offers_count = offers_count
    snapshot.size_bytes = size_bytes
    snapshot.save()

    if old_name and old_name != snapshot.file.name:
        snapshot.file.storage.delete(old_name)
    logger.info(
        "YML-фид %s: %s офферов, %s байт за %.1f с",
        category_slug or "catalog", offers_count, size_bytes,
        (timezone.now() - started).total_seconds(),
    )
    return snapshot


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
