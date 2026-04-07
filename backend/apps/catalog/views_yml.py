"""
YML-экспорт товаров для ВК Маркета и Яндекс.Маркета.

Эндпоинт: GET /api/catalog/export/yml/catalog.yml
Параметры:
  ?category=<slug>  — фильтр по слагу категории (и всем её потомкам)
  (без параметра)   — полный каталог

Категории ВК настраиваются через Django Admin → Маппинги категорий ВК.
"""
import xml.etree.ElementTree as ET
from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .models import Category, Product
from .models_vk import VKCategoryMapping
from .views import _get_category_ids_with_descendants

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


def _load_vk_mapping() -> dict[str, str]:
    """
    Загружает маппинг из БД и объединяет с fallback.
    Записи из БД имеют приоритет над fallback.
    """
    mapping = dict(_FALLBACK_VK_MAP)
    for m in VKCategoryMapping.objects.all():
        mapping[m.product_type] = m.vk_category_path
    return mapping


class YMLExportView(APIView):
    """
    Генерирует YML-фид (Yandex Market Language) для импорта товаров в ВК Маркет.

    Особенности:
    - Категории ВК берутся из таблицы VKCategoryMapping (Admin → Маппинги категорий ВК).
    - Характеристики товара (цвет, размер, материал) вписываются в описание,
      а НЕ в отдельные <param> — это предотвращает «мусор» в названии в ВК.
    - group_id намеренно отключён: с ним ВК автоматически дописывает атрибуты к названию.
    - Медиа: все изображения из галереи (ProductImage) и первое видео.
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        category_slug = request.query_params.get("category")

        # Загружаем маппинг категорий из БД (с fallback)
        vk_map = _load_vk_mapping()

        # Корневой элемент YML
        yml_catalog = ET.Element(
            "yml_catalog",
            date=timezone.now().strftime("%Y-%m-%d %H:%M")
        )
        shop = ET.SubElement(yml_catalog, "shop")

        ET.SubElement(shop, "name").text = "Mudaroba"
        ET.SubElement(shop, "company").text = "Mudaroba"
        ET.SubElement(shop, "url").text = "https://mudaroba.com/"

        currencies = ET.SubElement(shop, "currencies")
        ET.SubElement(currencies, "currency", id="RUB", rate="1")

        categories_el = ET.SubElement(shop, "categories")

        if category_slug:
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
            products = (
                Product.objects
                .filter(category_id__in=all_cat_ids, is_active=True)
                .select_related("brand", "category")
                .prefetch_related("images")
            )
        else:
            cats = Category.objects.filter(is_active=True)
            products = (
                Product.objects
                .filter(is_active=True)
                .select_related("brand", "category")
                .prefetch_related("images")
            )

        # Дерево категорий
        for cat in cats:
            cat_el = ET.SubElement(categories_el, "category", id=str(cat.id))
            if cat.parent_id:
                cat_el.set("parentId", str(cat.parent_id))
            cat_el.text = cat.name

        offers_el = ET.SubElement(shop, "offers")
        site_url = request.build_absolute_uri("/").rstrip("/")

        for prod in products:
            domain_item = prod.domain_item

            variants = []
            if domain_item and hasattr(domain_item, "variants"):
                variants = list(
                    domain_item.variants
                    .filter(is_active=True)
                    .prefetch_related("images")
                )

            if not variants:
                offer = self._create_offer(offers_el, prod, site_url, vk_map)
                self._add_params_to_description(offer, prod, domain_item)
            else:
                # Намеренно БЕЗ group_id — с ним ВК дописывает атрибуты в название
                for variant in variants:
                    offer_id = f"{prod.id}v{variant.id}"
                    offer = self._create_offer(
                        offers_el, prod, site_url, vk_map,
                        offer_id=offer_id,
                        variant=variant,
                    )
                    self._add_params_to_description(offer, prod, domain_item, variant)

        xml_str = ET.tostring(yml_catalog, encoding="utf-8", xml_declaration=True).decode("utf-8")
        return HttpResponse(xml_str, content_type="application/xml")

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    def _create_offer(self, parent, prod, site_url, vk_map,
                      offer_id=None, variant=None):
        """
        Строит элемент <offer> с правильным порядком тегов.

        Порядок (согласно спецификации YML):
        url > price > currencyId > categoryId > market_category >
        picture(s) > video > store > pickup > delivery >
        name > vendor > description
        """
        oid = offer_id or str(prod.id)
        is_available = prod.is_available
        if variant:
            is_available = variant.is_available and prod.is_available

        offer = ET.SubElement(
            parent, "offer",
            id=oid,
            available="true" if is_available else "false",
        )

        # 1. URL
        p_type = (prod.product_type or "other").lower().replace("_", "-")
        ET.SubElement(offer, "url").text = f"{site_url}/product/{p_type}/{prod.slug}"

        # 2. Цена
        v_price = getattr(variant, "price", None) if variant else None
        raw_price = v_price or prod.get_price_in_currency("RUB") or prod.price or 0
        price_dec = Decimal(str(raw_price))
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

        # 6. Изображения (вначале вариантные, затем родительские, без дублей)
        added_images: set[str] = set()

        if variant:
            v_main = ""
            if getattr(variant, "main_image_file", None):
                v_main = f"{site_url}{variant.main_image_file.url}"
            elif getattr(variant, "main_image", ""):
                raw = variant.main_image
                v_main = raw if raw.startswith("http") else f"{site_url}{raw}"
            if v_main:
                ET.SubElement(offer, "picture").text = v_main
                added_images.add(v_main)

            if hasattr(variant, "images"):
                for vi in variant.images.all():
                    url = vi.image_url or (
                        f"{site_url}{vi.image_file.url}" if vi.image_file else ""
                    )
                    if url and url not in added_images:
                        ET.SubElement(offer, "picture").text = url
                        added_images.add(url)

        # Главное фото родительского товара
        main_img = ""
        if getattr(prod, "main_image", ""):
            raw = prod.main_image
            main_img = raw if raw.startswith("http") else f"{site_url}{raw}"
        elif getattr(prod, "main_image_file", None):
            main_img = f"{site_url}{prod.main_image_file.url}"

        if main_img and main_img not in added_images:
            ET.SubElement(offer, "picture").text = main_img
            added_images.add(main_img)

        # Галерея родительского товара
        if hasattr(prod, "images"):
            for pi in prod.images.all():
                url = pi.image_url or (
                    f"{site_url}{pi.image_file.url}" if pi.image_file else ""
                )
                if url and url not in added_images:
                    ET.SubElement(offer, "picture").text = url
                    added_images.add(url)

        # 7. Видео (первое доступное)
        if hasattr(prod, "images"):
            for pi in prod.images.all():
                v_url = pi.video_url or (
                    f"{site_url}{pi.video_file.url}" if pi.video_file else ""
                )
                if v_url:
                    ET.SubElement(offer, "video").text = v_url
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

        # 11. Описание — сохраняем место для характеристик (добавятся в _add_params_to_description)
        desc_el = ET.SubElement(offer, "description")
        desc_el.text = (prod.description or prod.name or "")[:3000]

        return offer

    @staticmethod
    def _add_params_to_description(offer, prod, domain_item, variant=None):
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
            attrs = domain_item.dynamic_attributes.all().select_related("attribute_key")
            seen = {s.split(":")[0] for s in specs}  # не дублируем
            for attr in attrs:
                attr_name = attr.attribute_key.name
                attr_value = attr.value_ru or attr.value
                if attr_name and attr_value and attr_name not in seen:
                    specs.append(f"{attr_name}: {attr_value}")
                    seen.add(attr_name)

        if specs:
            current_desc = desc_el.text or ""
            extra = "\n\nХарактеристики:\n" + "\n".join(f"• {s}" for s in specs)
            desc_el.text = (current_desc + extra)[:3000]
