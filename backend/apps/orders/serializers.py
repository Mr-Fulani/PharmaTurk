from decimal import Decimal
from urllib.parse import quote

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify

from apps.catalog.models import (
    Product,
    Category,
    ClothingProduct,
    ShoeProduct,
    ElectronicsProduct,
    FurnitureProduct,
    JewelryProduct,
    ClothingVariant,
    ShoeVariant,
    FurnitureVariant,
)
from apps.catalog.utils.currency_converter import currency_converter
from apps.catalog.currency_models import ProductVariantPrice
from django.contrib.contenttypes.models import ContentType
from .models import Cart, CartItem, Order, OrderItem, PromoCode

VARIANT_MODEL_MAP = {
    'clothing': ClothingVariant,
    'shoes': ShoeVariant,
    'electronics': ElectronicsProduct,
    'furniture': FurnitureVariant,
}


def _resolve_media_url(value, request):
    if not value:
        return None
    if 'instagram.f' in value or 'cdninstagram.com' in value:
        if request:
            scheme = request.scheme
            host = request.get_host()
            if 'backend' in host or 'localhost:3001' in host or 'localhost:3000' in host:
                base_url = f"{scheme}://localhost:8000"
            else:
                base_url = f"{scheme}://{host}"
            return f"{base_url}/api/catalog/proxy-image/?url={quote(value)}"
        return f"http://localhost:8000/api/catalog/proxy-image/?url={quote(value)}"
    if not value.startswith('http'):
        if request:
            scheme = request.scheme
            host = request.get_host()
            if 'backend' in host or 'localhost:3001' in host or 'localhost:3000' in host:
                base_url = f"{scheme}://localhost:8000"
            else:
                base_url = f"{scheme}://{host}"
            return f"{base_url}/media/{value}"
        return f"http://localhost:8000/media/{value}"
    return value


def _resolve_file_url(file_field, request):
    if not file_field:
        return None
    if hasattr(file_field, "url"):
        if request:
            return request.build_absolute_uri(file_field.url)
        return file_field.url
    return None

PRODUCT_TYPE_ALIASES = {
    'supplements': 'supplements',
    'medical-equipment': 'medical_equipment',
    'medical_equipment': 'medical_equipment',
    'medical-accessories': 'accessories',
    'medical_accessories': 'accessories',
    'tableware': 'tableware',
    'furniture': 'furniture',
    'accessories': 'accessories',
    'jewelry': 'jewelry',
    'underwear': 'underwear',
    'headwear': 'headwear',
}

BASE_PRODUCT_TYPES = {
    'medicines',
    'supplements',
    'medical_equipment',
    'tableware',
    'furniture',
    'accessories',
    'underwear',
    'headwear',
}


def normalize_product_type(value: str | None) -> str:
    if not value:
        return 'medicines'
    return value.lower()


def ensure_product_from_base(base_obj, product_type: str) -> Product:
    """
    Создает/возвращает базовый Product для карточки обуви/одежды, если Variants отсутствуют.
    """
    slug = base_obj.slug
    desired_old_price = getattr(base_obj, 'old_price', None)
    defaults = {
        'name': getattr(base_obj, 'name', slug),
        'slug': slug,
        'description': getattr(base_obj, 'description', '') or '',
        'price': getattr(base_obj, 'price', None) or 0,
        'currency': getattr(base_obj, 'currency', None) or 'TRY',
        'old_price': desired_old_price,
        'brand': getattr(base_obj, 'brand', None),
        # У обуви/одежды категория в своей модели; у украшений — Category. Передаём если есть.
        'category': getattr(base_obj, 'category', None),
        'product_type': product_type,
        'is_available': getattr(base_obj, 'is_available', True),
        'main_image': getattr(base_obj, 'main_image', '') or '',
        'external_data': {
            'source_type': f'base_{product_type}',
            'source_id': base_obj.id,
            'source_slug': base_obj.slug,
        },
    }
    product, created = Product.objects.get_or_create(slug=slug, defaults=defaults)
    if not created:
        changed = False
        new_price = getattr(base_obj, 'price', None)
        if new_price is not None and product.price != new_price:
            product.old_price = product.price
            product.price = new_price
            changed = True
        new_currency = getattr(base_obj, 'currency', None)
        if new_currency and product.currency != new_currency:
            product.currency = new_currency
            changed = True
        if product.old_price != desired_old_price:
            product.old_price = desired_old_price
            changed = True
        availability = getattr(base_obj, 'is_available', True)
        if product.is_available != availability:
            product.is_available = availability
            changed = True
        main_image = getattr(base_obj, 'main_image', None)
        if main_image and product.main_image != main_image:
            product.main_image = main_image
            changed = True
        brand = getattr(base_obj, 'brand', None)
        if brand and product.brand_id is None:
            product.brand = brand
            changed = True
        if product.product_type != product_type:
            product.product_type = product_type
            changed = True
        if changed:
            product.save()
    return product


def get_or_create_category_for_variant(product_type: str) -> Category | None:
    from apps.catalog.constants import get_or_create_root_category
    if not product_type:
        return None
    slug = str(product_type).replace("_", "-").lower()
    return get_or_create_root_category(slug)


def ensure_product_from_variant(variant, source_type: str, effective_type: str) -> Product:
    parent_product = getattr(variant, "product", None)
    external = variant.external_data or {}
    product = None
    base_product_id = external.get('base_product_id')
    if base_product_id:
        try:
            product = Product.objects.get(id=base_product_id)
        except Product.DoesNotExist:
            product = None
    if product is not None:
        product_external = product.external_data or {}
        if product_external.get("source_variant_id") != variant.id:
            product = None
    def _variant_main_image(v):
        if getattr(v, "main_image", ""):
            return v.main_image
        images_qs = getattr(v, "images", None)
        if images_qs is not None:
            main_img = images_qs.filter(is_main=True).first()
            if main_img:
                return main_img.image_url
            first_img = images_qs.first()
            if first_img:
                return first_img.image_url
        return None
    base_slug = external.get('base_product_slug')
    if source_type in ("clothing", "shoes") or not base_slug:
        base_slug = slugify(f"{source_type}-{variant.slug}")
    category = get_or_create_category_for_variant(source_type) or get_or_create_category_for_variant(effective_type)
    brand = getattr(variant, "brand", None) if hasattr(variant, "brand") else None
    if not brand and parent_product:
        brand = getattr(parent_product, "brand", None)
    main_image_candidate = _variant_main_image(variant) or (getattr(parent_product, "main_image", "") if parent_product else "")
    desired_old_price = getattr(variant, 'old_price', None)
    if desired_old_price is None and parent_product is not None:
        desired_old_price = getattr(parent_product, 'old_price', None)
    # Проверяем, есть ли цена для варианта с учетом маржи
    variant_price_with_margin = None
    variant_currency = getattr(variant, 'currency', None) or 'TRY'
    
    try:
        content_type = ContentType.objects.get_for_model(variant)
        variant_price_obj = ProductVariantPrice.objects.filter(
            content_type=content_type,
            object_id=variant.id
        ).first()
        
        if variant_price_obj:
            # Используем цену с маржой из ProductVariantPrice
            if variant_currency == 'RUB' and variant_price_obj.rub_price_with_margin:
                variant_price_with_margin = variant_price_obj.rub_price_with_margin
            elif variant_currency == 'USD' and variant_price_obj.usd_price_with_margin:
                variant_price_with_margin = variant_price_obj.usd_price_with_margin
            elif variant_currency == 'KZT' and variant_price_obj.kzt_price_with_margin:
                variant_price_with_margin = variant_price_obj.kzt_price_with_margin
            elif variant_currency == 'EUR' and variant_price_obj.eur_price_with_margin:
                variant_price_with_margin = variant_price_obj.eur_price_with_margin
            elif variant_currency == 'TRY' and variant_price_obj.try_price_with_margin:
                variant_price_with_margin = variant_price_obj.try_price_with_margin
            else:
                # Если цена с маржой не найдена, используем обычную цену
                variant_price_with_margin = getattr(variant, 'price', None)
        else:
            # Если ProductVariantPrice не найден, используем обычную цену варианта
            variant_price_with_margin = getattr(variant, 'price', None)
    except Exception as e:
        # В случае ошибки используем обычную цену варианта
        variant_price_with_margin = getattr(variant, 'price', None)
    
    defaults = {
        'name': variant.name or (parent_product.name if parent_product else ""),
        'slug': base_slug,
        'description': getattr(variant, 'description', '') or (getattr(parent_product, "description", "") if parent_product else ''),
        'price': variant_price_with_margin or (getattr(parent_product, "price", None) or 0),
        'currency': variant_currency,
        'old_price': desired_old_price,
        'product_type': effective_type,
        'brand': brand,
        'category': category,
        'is_available': getattr(variant, 'is_available', True),
        'main_image': main_image_candidate,
        'external_data': {
            'source_type': source_type,
            'effective_type': effective_type,
            'source_variant_id': variant.id,
            'source_variant_slug': variant.slug,
        },
    }
    variant_external_payload = {
        'source_type': source_type,
        'effective_type': effective_type,
        'source_variant_id': variant.id,
        'source_variant_slug': variant.slug,
    }
    if product is None:
        product, created = Product.objects.get_or_create(slug=base_slug, defaults=defaults)
    else:
        created = False
    if not created:
        changed = False
        new_price = getattr(variant, 'price', None)
        if new_price is not None and product.price != new_price:
            product.old_price = product.price
            product.price = new_price
            changed = True
        new_currency = getattr(variant, 'currency', None)
        if new_currency and product.currency != new_currency:
            product.currency = new_currency
            changed = True
        if product.old_price != desired_old_price:
            product.old_price = desired_old_price
            changed = True
        availability = getattr(variant, 'is_available', True)
        if product.is_available != availability:
            product.is_available = availability
            changed = True
        main_image = _variant_main_image(variant)
        if main_image and product.main_image != main_image:
            product.main_image = main_image
            changed = True
        if product.product_type != effective_type:
            product.product_type = effective_type
            changed = True
        if category and product.category_id is None:
            product.category = category
            changed = True
        if brand and product.brand_id is None:
            product.brand = brand
            changed = True
        product_external = product.external_data or {}
        merged_ext = {**product_external, **variant_external_payload}
        if product.external_data != merged_ext:
            product.external_data = merged_ext
            changed = True
        if changed:
            product.save()
    else:
        product.external_data = {**(product.external_data or {}), **variant_external_payload}
        product.save(update_fields=['external_data'])
    external['base_product_id'] = product.id
    external['base_product_slug'] = product.slug
    variant.external_data = external
    variant.save(update_fields=['external_data'])
    return product


def resolve_variant_product(product_type: str, product_slug: str) -> Product:
    normalized = normalize_product_type(product_type)
    effective_type = PRODUCT_TYPE_ALIASES.get(normalized, normalized)
    if effective_type in BASE_PRODUCT_TYPES:
        return Product.objects.get(slug=product_slug, is_active=True)

    # Базовая карточка без вариантов (обувь/одежда/украшения), если slug есть в соответствующей модели
    base_model_map = {
        'shoes': ShoeProduct,
        'clothing': ClothingProduct,
        'jewelry': JewelryProduct,
    }
    base_model = base_model_map.get(effective_type)
    if base_model:
        base_obj = base_model.objects.filter(slug=product_slug, is_active=True).first()
        if base_obj:
            return ensure_product_from_base(base_obj, effective_type)

    model = VARIANT_MODEL_MAP.get(effective_type)
    if not model:
        return Product.objects.get(slug=product_slug, is_active=True)

    try:
        variant = model.objects.get(slug=product_slug, is_active=True)
    except model.DoesNotExist:
        raise Product.DoesNotExist()
    return ensure_product_from_variant(variant, normalized, effective_type)


class CartItemSerializer(serializers.ModelSerializer):
    """
    Сериализатор позиции корзины
    """
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_slug = serializers.SerializerMethodField()
    product_type = serializers.CharField(source='product.product_type', read_only=True)
    product_image_url = serializers.SerializerMethodField()
    product_video_url = serializers.SerializerMethodField()
    chosen_size = serializers.CharField(read_only=True)
    
    # Добавляем поля из новой системы ценообразования
    price = serializers.SerializerMethodField()  # Изменено на метод
    currency = serializers.SerializerMethodField()  # Изменено на метод
    old_price = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    converted_price_rub = serializers.SerializerMethodField()  # Новое поле
    converted_price_usd = serializers.SerializerMethodField()  # Новое поле
    final_price_rub = serializers.SerializerMethodField()  # Новое поле
    final_price_usd = serializers.SerializerMethodField()  # Новое поле
    margin_percent_applied = serializers.SerializerMethodField()  # Новое поле
    prices_in_currencies = serializers.SerializerMethodField()  # Новое поле

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'product_name', 'product_slug', 'product_type', 'product_image_url', 'product_video_url',
            'quantity', 'price', 'currency', 'old_price', 'old_price_formatted', 'chosen_size', 'created_at', 'updated_at',
            # Новые поля из системы ценообразования
            'converted_price_rub', 'converted_price_usd', 'final_price_rub', 'final_price_usd',
            'margin_percent_applied', 'prices_in_currencies', 'total'
        ]
        read_only_fields = ['price', 'currency', 'created_at', 'updated_at', 
                           'converted_price_rub', 'converted_price_usd', 'final_price_rub', 'final_price_usd',
                           'margin_percent_applied', 'prices_in_currencies', 'total']
    
    def get_product_image_url(self, obj):
        """Получение URL изображения товара (с запасным поиском по варианту)."""
        product = obj.product
        if not product:
            return None
        request = self.context.get('request')
        
        # Сначала проверяем main_image
        file_url = _resolve_file_url(getattr(product, "main_image_file", None), request)
        if file_url:
            return file_url
        if product.main_image:
            return _resolve_media_url(product.main_image, request)

        # Затем ищем главное изображение в связанных изображениях продукта
        main_img = product.images.filter(is_main=True).first()
        if main_img:
            file_url = _resolve_file_url(getattr(main_img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(main_img.image_url, request)

        first_img = product.images.first()
        if first_img:
            file_url = _resolve_file_url(getattr(first_img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(first_img.image_url, request)

        # Для отдельных типов пробуем базовую модель по slug (если Product пустой)
        try:
            base_models = {
                "shoes": ShoeProduct,
                "clothing": ClothingProduct,
                "jewelry": JewelryProduct,
                "electronics": ElectronicsProduct,
                "furniture": FurnitureProduct,
            }
            base_model = base_models.get(product.product_type)
            if base_model:
                base_obj = (
                    base_model.objects.filter(slug=product.slug, is_active=True)
                    .prefetch_related("images", "variants__images")
                    .first()
                )
                if base_obj:
                    file_url = _resolve_file_url(getattr(base_obj, "main_image_file", None), request)
                    if file_url:
                        return file_url
                    if getattr(base_obj, "main_image", ""):
                        return _resolve_media_url(base_obj.main_image, request)
                    base_main = base_obj.images.filter(is_main=True).first()
                    if base_main:
                        file_url = _resolve_file_url(getattr(base_main, "image_file", None), request)
                        if file_url:
                            return file_url
                        return _resolve_media_url(base_main.image_url, request)
                    base_first = base_obj.images.first()
                    if base_first:
                        file_url = _resolve_file_url(getattr(base_first, "image_file", None), request)
                        if file_url:
                            return file_url
                        return _resolve_media_url(base_first.image_url, request)
                    # Фолбэк к первому варианту базового товара
                    first_variant = base_obj.variants.filter(is_active=True).order_by("sort_order", "id").first()
                    if first_variant:
                        file_url = _resolve_file_url(getattr(first_variant, "main_image_file", None), request)
                        if file_url:
                            return file_url
                        if first_variant.main_image:
                            return _resolve_media_url(first_variant.main_image, request)
                        v_main = first_variant.images.filter(is_main=True).first()
                        if v_main:
                            file_url = _resolve_file_url(getattr(v_main, "image_file", None), request)
                            if file_url:
                                return file_url
                            return _resolve_media_url(v_main.image_url, request)
                        v_first = first_variant.images.first()
                        if v_first:
                            file_url = _resolve_file_url(getattr(v_first, "image_file", None), request)
                            if file_url:
                                return file_url
                            return _resolve_media_url(v_first.image_url, request)
        except Exception:
            pass

        # Фолбэк: пробуем подтянуть изображение из варианта по сохранённым external_data
        ext = getattr(product, "external_data", {}) or {}
        variant_slug = ext.get("source_variant_slug")
        effective_type = ext.get("effective_type") or ext.get("source_type")
        if not effective_type:
            effective_type = product.product_type
        if not variant_slug:
            # Старые записи могли сохраниться без external_data.
            # Для обуви/одежды slug базовой карточки создавался как "{type}-{variant_slug}".
            if effective_type in ("shoes", "clothing"):
                prefix = f"{effective_type}-"
                if product.slug.startswith(prefix):
                    variant_slug = product.slug.replace(prefix, "", 1)
            if not variant_slug:
                variant_slug = product.slug

        variant_model = VARIANT_MODEL_MAP.get(effective_type)
        if variant_model and variant_model in (ClothingVariant, ShoeVariant):
            variant = variant_model.objects.filter(slug=variant_slug, is_active=True).prefetch_related("images").first()
            if variant:
                file_url = _resolve_file_url(getattr(variant, "main_image_file", None), request)
                if file_url:
                    return file_url
                if variant.main_image:
                    return _resolve_media_url(variant.main_image, request)
                v_main = variant.images.filter(is_main=True).first()
                if v_main:
                    file_url = _resolve_file_url(getattr(v_main, "image_file", None), request)
                    if file_url:
                        return file_url
                    return _resolve_media_url(v_main.image_url, request)
                v_first = variant.images.first()
                if v_first:
                    file_url = _resolve_file_url(getattr(v_first, "image_file", None), request)
                    if file_url:
                        return file_url
                    return _resolve_media_url(v_first.image_url, request)

        # Дополнительный фолбэк: пробуем найти базовую карточку обуви/одежды и взять первую активную вариацию
        try:
            if product.product_type == 'shoes':
                base_shoe = ShoeProduct.objects.filter(slug=product.slug, is_active=True).prefetch_related('variants__images').first()
                if base_shoe:
                    v = base_shoe.variants.filter(is_active=True).order_by('sort_order', 'id').first()
                    if v:
                        file_url = _resolve_file_url(getattr(v, "main_image_file", None), request)
                        if file_url:
                            return file_url
                        if v.main_image:
                            return _resolve_media_url(v.main_image, request)
                        v_main = v.images.filter(is_main=True).first()
                        if v_main:
                            file_url = _resolve_file_url(getattr(v_main, "image_file", None), request)
                            if file_url:
                                return file_url
                            return _resolve_media_url(v_main.image_url, request)
                        v_first = v.images.first()
                        if v_first:
                            file_url = _resolve_file_url(getattr(v_first, "image_file", None), request)
                            if file_url:
                                return file_url
                            return _resolve_media_url(v_first.image_url, request)
            if product.product_type == 'clothing':
                base_cloth = ClothingProduct.objects.filter(slug=product.slug, is_active=True).prefetch_related('variants__images').first()
                if base_cloth:
                    v = base_cloth.variants.filter(is_active=True).order_by('sort_order', 'id').first()
                    if v:
                        file_url = _resolve_file_url(getattr(v, "main_image_file", None), request)
                        if file_url:
                            return file_url
                        if v.main_image:
                            return _resolve_media_url(v.main_image, request)
                        v_main = v.images.filter(is_main=True).first()
                        if v_main:
                            file_url = _resolve_file_url(getattr(v_main, "image_file", None), request)
                            if file_url:
                                return file_url
                            return _resolve_media_url(v_main.image_url, request)
                        v_first = v.images.first()
                        if v_first:
                            file_url = _resolve_file_url(getattr(v_first, "image_file", None), request)
                            if file_url:
                                return file_url
                            return _resolve_media_url(v_first.image_url, request)
        except Exception:
            pass

        return None

    def get_product_video_url(self, obj):
        """URL главного видео товара (для карточек в корзине/заказе)."""
        product = obj.product
        if not product:
            return None
        request = self.context.get('request')
        # Product (медикаменты и т.д.)
        file_url = _resolve_file_url(getattr(product, "main_video_file", None), request)
        if file_url:
            return file_url
        raw_url = getattr(product, "video_url", None) or ""
        if raw_url and raw_url.strip():
            path_lower = raw_url.split("?")[0].lower()
            if not path_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg")):
                return _resolve_media_url(raw_url, request)
        # Базовая модель (jewelry, clothing, shoes)
        base_models = {
            "shoes": ShoeProduct,
            "clothing": ClothingProduct,
            "jewelry": JewelryProduct,
            "electronics": ElectronicsProduct,
            "furniture": FurnitureProduct,
        }
        base_model = base_models.get(product.product_type)
        if base_model:
            base_obj = base_model.objects.filter(slug=product.slug, is_active=True).first()
            if base_obj:
                file_url = _resolve_file_url(getattr(base_obj, "main_video_file", None), request)
                if file_url:
                    return file_url
                raw_url = getattr(base_obj, "video_url", None) or ""
                if raw_url and raw_url.strip():
                    path_lower = raw_url.split("?")[0].lower()
                    if not path_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg")):
                        return _resolve_media_url(raw_url, request)
        return None

    def get_product_slug(self, obj):
        """Для варианта возвращаем исходный slug варианта, если сохранён в external_data."""
        product = obj.product
        if not product:
            return None
        ext = getattr(product, "external_data", {}) or {}
        return ext.get("source_variant_slug") or product.slug
    
    def _get_preferred_currency(self, request):
        """Определяет валюту по приоритетам: explicit -> user -> язык -> default."""
        default_currency = 'RUB'
        if not request:
            return default_currency

        # Явный выбор валюты имеет приоритет
        preferred_currency = request.headers.get('X-Currency')
        if preferred_currency:
            return preferred_currency.upper()
        preferred_currency = request.query_params.get('currency')
        if preferred_currency:
            return preferred_currency.upper()

        if getattr(request, 'user', None) and request.user.is_authenticated:
            user_currency = getattr(request.user, 'currency', None)
            if user_currency:
                return user_currency.upper()

        language_code = getattr(request, 'LANGUAGE_CODE', None)
        language_currency_map = {
            'en': 'USD',
            'ru': 'RUB',
        }
        return language_currency_map.get(language_code, default_currency)
    
    def get_price(self, obj):
        """Получает цену в предпочитаемой валюте."""
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        
        # Получаем цену в предпочитаемой валюте
        try:
            prices = obj.product.get_all_prices()
            if prices and preferred_currency in prices:
                return prices[preferred_currency].get('price_with_margin')
            elif prices:
                # Если предпочитаемой валюты нет, вернем базовую
                for currency, data in prices.items():
                    if data.get('is_base_price'):
                        return data.get('price_with_margin')
                # Или просто первую
                first_currency = list(prices.keys())[0]
                return prices[first_currency].get('price_with_margin')
        except Exception:
            pass
        
        # Fallback к старому полю
        return obj.price
    
    def get_currency(self, obj):
        """Получает валюту товара из новой системы."""
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        
        # Получаем валюту из новой системы
        try:
            prices = obj.product.get_all_prices()
            if prices and preferred_currency in prices:
                return preferred_currency
            elif prices:
                # Если предпочитаемой валюты нет, вернем базовую
                for currency, data in prices.items():
                    if data.get('is_base_price'):
                        return currency
                # Или просто первую
                return list(prices.keys())[0]
        except Exception:
            pass
        
        # Fallback к старому полю
        return obj.currency if obj.currency else 'RUB'

    def get_old_price(self, obj):
        product = obj.product
        if not product:
            return None
        old_price = product.old_price
        from_currency = (product.currency or 'RUB').upper()
        if old_price is None:
            ext = getattr(product, "external_data", {}) or {}
            variant_slug = ext.get("source_variant_slug")
            effective_type = ext.get("effective_type") or ext.get("source_type")
            variant_model = VARIANT_MODEL_MAP.get(effective_type)
            if variant_slug and variant_model in (ClothingVariant, ShoeVariant, FurnitureVariant):
                variant = variant_model.objects.filter(slug=variant_slug, is_active=True).first()
                if variant:
                    if variant.old_price is not None:
                        old_price = variant.old_price
                        from_currency = (variant.currency or product.currency or 'RUB').upper()
                    elif getattr(variant, "product", None) is not None:
                        parent_product = variant.product
                        if parent_product.old_price is not None:
                            old_price = parent_product.old_price
                            from_currency = (parent_product.currency or variant.currency or product.currency or 'RUB').upper()
        if old_price is None:
            return None
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        if preferred_currency != from_currency:
            try:
                _, _, price_with_margin = currency_converter.convert_price(
                    Decimal(old_price),
                    from_currency,
                    preferred_currency,
                    apply_margin=True,
                )
                return price_with_margin
            except Exception:
                pass
        return old_price

    def get_old_price_formatted(self, obj):
        product = obj.product
        if not product:
            return None
        old_price = product.old_price
        from_currency = (product.currency or 'RUB').upper()
        if old_price is None:
            ext = getattr(product, "external_data", {}) or {}
            variant_slug = ext.get("source_variant_slug")
            effective_type = ext.get("effective_type") or ext.get("source_type")
            variant_model = VARIANT_MODEL_MAP.get(effective_type)
            if variant_slug and variant_model in (ClothingVariant, ShoeVariant, FurnitureVariant):
                variant = variant_model.objects.filter(slug=variant_slug, is_active=True).first()
                if variant:
                    if variant.old_price is not None:
                        old_price = variant.old_price
                        from_currency = (variant.currency or product.currency or 'RUB').upper()
                    elif getattr(variant, "product", None) is not None:
                        parent_product = variant.product
                        if parent_product.old_price is not None:
                            old_price = parent_product.old_price
                            from_currency = (parent_product.currency or variant.currency or product.currency or 'RUB').upper()
        if old_price is None:
            return None
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        
        # Применяем маржу даже если валюта совпадает (особенно для рублей)
        try:
            _, _, price_with_margin = currency_converter.convert_price(
                Decimal(old_price),
                from_currency,
                preferred_currency,
                apply_margin=True,
            )
            return f"{price_with_margin} {preferred_currency}"
        except Exception:
            # Fallback на исходное значение если конвертация не удалась
            return f"{old_price} {from_currency}"
    
    def get_converted_price_rub(self, obj):
        """Получает конвертированную цену в RUB."""
        try:
            prices = obj.product.get_all_prices()
            if 'RUB' in prices:
                return prices['RUB'].get('converted_price')
        except Exception:
            pass
        return None
    
    def get_converted_price_usd(self, obj):
        """Получает конвертированную цену в USD."""
        try:
            prices = obj.product.get_all_prices()
            if 'USD' in prices:
                return prices['USD'].get('converted_price')
        except Exception:
            pass
        return None
    
    def get_final_price_rub(self, obj):
        """Получает финальную цену в RUB с маржой."""
        try:
            prices = obj.product.get_all_prices()
            if 'RUB' in prices:
                return prices['RUB'].get('price_with_margin')
        except Exception:
            pass
        return None
    
    def get_final_price_usd(self, obj):
        """Получает финальную цену в USD с маржой."""
        try:
            prices = obj.product.get_all_prices()
            if 'USD' in prices:
                return prices['USD'].get('price_with_margin')
        except Exception:
            pass
        return None
    
    def get_margin_percent_applied(self, obj):
        """Получает примененную маржу."""
        try:
            prices = obj.product.get_all_prices()
            if prices:
                # Найдем базовую валюту
                for currency, data in prices.items():
                    if data.get('is_base_price'):
                        return 0  # Для базовой валюты маржа 0%
                
                # Для других валют можно взять среднюю маржу
                margins = []
                for currency, data in prices.items():
                    if not data.get('is_base_price') and data.get('price_with_margin') and data.get('converted_price'):
                        if data['converted_price'] > 0:
                            margin = ((data['price_with_margin'] - data['converted_price']) / data['converted_price']) * 100
                            margins.append(margin)
                
                if margins:
                    return sum(margins) / len(margins)
        except Exception:
            pass
        return 0
    
    def get_prices_in_currencies(self, obj):
        """Получает цены во всех валютах."""
        try:
            return obj.product.get_all_prices()
        except Exception:
            return {}


class PromoCodeSerializer(serializers.ModelSerializer):
    """
    Сериализатор промокода
    """
    class Meta:
        model = PromoCode
        fields = [
            'id', 'code', 'description', 'discount_type', 'discount_value',
            'min_amount', 'max_discount', 'max_uses', 'used_count',
            'valid_from', 'valid_to', 'is_active'
        ]
        read_only_fields = ['used_count']


class ApplyPromoCodeSerializer(serializers.Serializer):
    """
    Запрос на применение промокода
    """
    code = serializers.CharField(max_length=50)

    def validate_code(self, value):
        """Валидация кода промокода (поиск без учёта регистра)."""
        try:
            PromoCode.objects.get(code__iexact=value.strip())
        except PromoCode.DoesNotExist:
            raise serializers.ValidationError(_("Промокод не найден"))
        return value.strip().upper()


class CartSerializer(serializers.ModelSerializer):
    """
    Сериализатор корзины
    """
    items = CartItemSerializer(many=True, read_only=True)
    items_count = serializers.IntegerField(read_only=True)
    total_amount = serializers.SerializerMethodField()
    discount_amount = serializers.SerializerMethodField()
    final_amount = serializers.SerializerMethodField()
    promo_code = PromoCodeSerializer(read_only=True)
    currency = serializers.SerializerMethodField()  # Изменено на метод

    class Meta:
        model = Cart
        fields = [
            'id', 'user', 'session_key', 'currency',
            'items', 'items_count', 'total_amount', 'discount_amount', 'final_amount',
            'promo_code',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at', 'items', 'items_count', 'total_amount', 'discount_amount', 'final_amount', 'currency']

    def _get_preferred_currency(self, request):
        """Определяет валюту по приоритетам: explicit -> user -> язык -> default."""
        default_currency = 'RUB'
        if not request:
            return default_currency

        # Явный выбор валюты имеет приоритет
        preferred_currency = request.headers.get('X-Currency')
        if preferred_currency:
            return preferred_currency.upper()
        preferred_currency = request.query_params.get('currency')
        if preferred_currency:
            return preferred_currency.upper()

        if getattr(request, 'user', None) and request.user.is_authenticated:
            user_currency = getattr(request.user, 'currency', None)
            if user_currency:
                return user_currency.upper()

        language_code = getattr(request, 'LANGUAGE_CODE', None)
        language_currency_map = {
            'en': 'USD',
            'ru': 'RUB',
        }
        return language_currency_map.get(language_code, default_currency)

    def get_currency(self, obj):
        """Получает валюту корзины (предпочитаемая валюта)."""
        request = self.context.get('request')
        return self._get_preferred_currency(request)
    
    def get_total_amount(self, obj):
        """Рассчитать общую сумму корзины в предпочитаемой валюте."""
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        
        total = 0
        for item in obj.items.all():
            try:
                prices = item.product.get_all_prices()
                if prices and preferred_currency in prices:
                    price = prices[preferred_currency].get('price_with_margin', 0)
                elif prices:
                    # Если предпочитаемой валюты нет, используем базовую
                    for currency, data in prices.items():
                        if data.get('is_base_price'):
                            price = data.get('price_with_margin', 0)
                            break
                    else:
                        # Если базовой нет, берем первую
                        first_currency = list(prices.keys())[0]
                        price = prices[first_currency].get('price_with_margin', 0)
                else:
                    # Fallback к старому полю
                    price = item.price
                
                total += price * item.quantity
            except Exception:
                # Fallback к старому полю
                total += item.price * item.quantity
        
        return float(round(total, 2))
    
    def get_discount_amount(self, obj):
        """Рассчитать скидку по промокоду."""
        if not obj.promo_code:
            return 0

        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        total = float(self.get_total_amount(obj))
        is_valid, error = obj.promo_code.is_valid(cart_total=total, cart_currency=preferred_currency)
        if not is_valid:
            return 0
        return obj.promo_code.calculate_discount(total, currency=preferred_currency)
    
    def get_final_amount(self, obj):
        """Итоговая сумма с учётом скидки."""
        from decimal import Decimal, ROUND_HALF_UP

        try:
            total_dec = Decimal(str(self.get_total_amount(obj)))
        except Exception:
            total_dec = Decimal('0')

        try:
            discount_dec = Decimal(str(self.get_discount_amount(obj)))
        except Exception:
            discount_dec = Decimal('0')

        return float((total_dec - discount_dec).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class AddToCartSerializer(serializers.Serializer):
    """
    Запрос на добавление товара в корзину.
    - Базовые товары: product_id
    - Варианты (одежда/обувь): product_type + product_slug (slug варианта цвета) + size
    """
    product_id = serializers.IntegerField(required=False)
    product_type = serializers.CharField(required=False)
    product_slug = serializers.CharField(required=False)
    size = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate(self, attrs):
        product_id = attrs.get('product_id')
        product_type = attrs.get('product_type')
        product_slug = attrs.get('product_slug')
        chosen_size = attrs.get('size') or ""

        # Конфликт: оба идентификатора одновременно
        if product_id and product_slug:
            raise serializers.ValidationError({"detail": _("Укажите либо product_id, либо product_slug (вариант), но не оба.")})

        # Базовый товар по ID
        if product_id:
            try:
                product = Product.objects.get(id=product_id, is_active=True)
            except Product.DoesNotExist:
                raise serializers.ValidationError({"detail": _("Товар не найден по product_id")})
            attrs['product'] = product
            attrs['chosen_size'] = chosen_size
            return attrs

        # Вариант по type + slug (или fallback на базовый по slug)
        if not product_slug:
            raise serializers.ValidationError({"detail": _("Не указан product_slug или product_id")})

        # Если тип не передан, считаем базовым
        effective_type = product_type or 'medicines'

        normalized = normalize_product_type(effective_type)

        # Проверяем вариант напрямую, чтобы валидировать размер (для одежды/обуви)
        variant = None
        variant_model = VARIANT_MODEL_MAP.get(normalized)
        if variant_model and variant_model in (ClothingVariant, ShoeVariant):
            variant = variant_model.objects.filter(slug=product_slug, is_active=True).first()
            if variant:
                has_size_grid = variant.sizes.exists()
                if has_size_grid:
                    if not chosen_size:
                        raise serializers.ValidationError({"detail": _("Укажите размер для этого варианта")})
                    size_obj = variant.sizes.filter(size=chosen_size).first()
                    if not size_obj:
                        raise serializers.ValidationError({"detail": _("Размер не найден для выбранного цвета")})
                    if not size_obj.is_available:
                        raise serializers.ValidationError({"detail": _("Размер недоступен для покупки")})
                attrs['chosen_size'] = chosen_size
            else:
                base_model_map = {
                    'clothing': ClothingProduct,
                    'shoes': ShoeProduct,
                }
                base_model = base_model_map.get(normalized)
                if base_model:
                    base_obj = base_model.objects.filter(slug=product_slug, is_active=True).first()
                    if base_obj and base_obj.sizes.exists():
                        if not chosen_size:
                            raise serializers.ValidationError({"detail": _("Укажите размер для этого товара")})
                        size_obj = base_obj.sizes.filter(size=chosen_size).first()
                        if not size_obj:
                            raise serializers.ValidationError({"detail": _("Размер не найден")})
                        if not size_obj.is_available:
                            raise serializers.ValidationError({"detail": _("Размер недоступен для покупки")})
        else:
            # Базовые типы (без вариантов) — пробуем найти продукт по slug сразу
            base = Product.objects.filter(slug=product_slug, is_active=True).first()
            if base:
                attrs['product'] = base
                attrs['chosen_size'] = chosen_size
                return attrs

        # Если базового нет — пробуем как вариант/базовую карточку одежды/обуви
        try:
            product = resolve_variant_product(effective_type, product_slug)
        except Product.DoesNotExist:
            raise serializers.ValidationError({"detail": _("Товар не найден по slug")})

        attrs['product'] = product
        attrs['chosen_size'] = chosen_size
        return attrs


class UpdateCartItemSerializer(serializers.Serializer):
    """
    Запрос на изменение количества позиции в корзине
    """
    quantity = serializers.IntegerField(min_value=1)


class OrderItemSerializer(serializers.ModelSerializer):
    """
    Сериализатор позиции заказа
    """
    product_slug = serializers.CharField(source='product.slug', read_only=True)
    product_image_url = serializers.SerializerMethodField()
    product_video_url = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'product_slug', 'product_image_url', 'product_video_url', 'chosen_size', 'price', 'quantity', 'total']
        read_only_fields = ['product_name', 'price', 'total', 'product_slug', 'product_image_url', 'product_video_url']

    def _get_preferred_currency(self, request, fallback: str = 'RUB') -> str:
        if not request:
            return fallback
        preferred_currency = request.headers.get('X-Currency')
        if preferred_currency:
            return preferred_currency.upper()
        preferred_currency = request.query_params.get('currency')
        if preferred_currency:
            return preferred_currency.upper()
        if getattr(request, 'user', None) and request.user.is_authenticated:
            user_currency = getattr(request.user, 'currency', None)
            if user_currency:
                return user_currency.upper()
        language_code = getattr(request, 'LANGUAGE_CODE', None)
        language_currency_map = {
            'en': 'USD',
            'ru': 'RUB',
        }
        return language_currency_map.get(language_code, fallback)

    def _convert_money(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        if from_currency == to_currency:
            return amount
        _orig, converted, _with_margin = currency_converter.convert_price(
            amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            apply_margin=False,
        )
        return converted

    def get_price(self, obj):
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request, fallback=getattr(obj.order, 'currency', 'RUB'))
        order_currency = getattr(obj.order, 'currency', 'RUB')
        try:
            amount = Decimal(str(obj.price))
            return self._convert_money(amount, order_currency, preferred_currency)
        except Exception:
            return obj.price

    def get_total(self, obj):
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request, fallback=getattr(obj.order, 'currency', 'RUB'))
        order_currency = getattr(obj.order, 'currency', 'RUB')
        try:
            amount = Decimal(str(obj.total))
            return self._convert_money(amount, order_currency, preferred_currency)
        except Exception:
            return obj.total
    
    def get_product_image_url(self, obj):
        """Получение URL изображения товара"""
        if not obj.product:
            return None
        
        product = obj.product
        # Сначала проверяем main_image
        if product.main_image:
            return product.main_image
        
        # Затем ищем главное изображение в связанных изображениях
        try:
            from apps.catalog.models import ProductImage
            main_img = product.images.filter(is_main=True).first()
            if main_img:
                return main_img.image_url
            
            # Если нет главного, берем первое изображение
            first_img = product.images.first()
            if first_img:
                return first_img.image_url
        except Exception:
            pass
        
        return None

    def get_product_video_url(self, obj):
        """URL главного видео товара для позиции заказа."""
        if not obj.product:
            return None
        product = obj.product
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(product, "main_video_file", None), request)
        if file_url:
            return file_url
        raw_url = getattr(product, "video_url", None) or ""
        if raw_url and raw_url.strip():
            path_lower = raw_url.split("?")[0].lower()
            if not path_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg")):
                return _resolve_media_url(raw_url, request)
        base_models = {
            "shoes": ShoeProduct,
            "clothing": ClothingProduct,
            "jewelry": JewelryProduct,
            "electronics": ElectronicsProduct,
            "furniture": FurnitureProduct,
        }
        base_model = base_models.get(product.product_type)
        if base_model:
            base_obj = base_model.objects.filter(slug=product.slug, is_active=True).first()
            if base_obj:
                file_url = _resolve_file_url(getattr(base_obj, "main_video_file", None), request)
                if file_url:
                    return file_url
                raw_url = getattr(base_obj, "video_url", None) or ""
                if raw_url and raw_url.strip():
                    path_lower = raw_url.split("?")[0].lower()
                    if not path_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg")):
                        return _resolve_media_url(raw_url, request)
        return None


# TODO: Функционал чеков временно отключен. Будет доработан позже.
# Включает: формирование чека, отправку по email, интеграцию с админкой.
class OrderReceiptItemSerializer(serializers.Serializer):
    """Позиция в чеке заказа."""
    id = serializers.IntegerField()
    product_name = serializers.CharField()
    quantity = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()


# TODO: Функционал чеков временно отключен. Будет доработан позже.
# Включает: формирование чека, отправку по email, интеграцию с админкой.
class OrderReceiptSerializer(serializers.Serializer):
    """Структура данных чека заказа."""
    number = serializers.CharField()
    status = serializers.CharField()
    currency = serializers.CharField()
    issued_at = serializers.DateTimeField()
    items = OrderReceiptItemSerializer(many=True)
    seller = serializers.DictField()
    customer = serializers.DictField()
    shipping = serializers.DictField()
    payment = serializers.DictField()
    totals = serializers.DictField()
    meta = serializers.DictField()
    promo_code = serializers.CharField(allow_null=True, required=False)


class OrderSerializer(serializers.ModelSerializer):
    """
    Сериализатор заказа
    """
    items = OrderItemSerializer(many=True, read_only=True)
    promo_code = PromoCodeSerializer(read_only=True)
    currency = serializers.SerializerMethodField()
    subtotal_amount = serializers.SerializerMethodField()
    shipping_amount = serializers.SerializerMethodField()
    discount_amount = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'number', 'status', 'user',
            'subtotal_amount', 'shipping_amount', 'discount_amount', 'total_amount', 'currency',
            'contact_name', 'contact_phone', 'contact_email',
            'shipping_address', 'shipping_address_text', 'shipping_method',
            'payment_method', 'payment_status', 'comment',
            'promo_code',
            'items',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['number', 'status', 'user', 'subtotal_amount', 'total_amount', 'currency', 'created_at', 'updated_at']

    def _get_preferred_currency(self, request, fallback: str = 'RUB') -> str:
        if not request:
            return fallback
        preferred_currency = request.headers.get('X-Currency')
        if preferred_currency:
            return preferred_currency.upper()
        preferred_currency = request.query_params.get('currency')
        if preferred_currency:
            return preferred_currency.upper()
        if getattr(request, 'user', None) and request.user.is_authenticated:
            user_currency = getattr(request.user, 'currency', None)
            if user_currency:
                return user_currency.upper()
        language_code = getattr(request, 'LANGUAGE_CODE', None)
        language_currency_map = {
            'en': 'USD',
            'ru': 'RUB',
        }
        return language_currency_map.get(language_code, fallback)

    def _convert_money(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        if from_currency == to_currency:
            return amount
        _orig, converted, _with_margin = currency_converter.convert_price(
            amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            apply_margin=False,
        )
        return converted

    def get_currency(self, obj):
        request = self.context.get('request')
        return self._get_preferred_currency(request, fallback=getattr(obj, 'currency', 'RUB'))

    def get_subtotal_amount(self, obj):
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request, fallback=getattr(obj, 'currency', 'RUB'))
        try:
            return self._convert_money(Decimal(str(obj.subtotal_amount)), obj.currency, preferred_currency)
        except Exception:
            return obj.subtotal_amount

    def get_shipping_amount(self, obj):
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request, fallback=getattr(obj, 'currency', 'RUB'))
        try:
            return self._convert_money(Decimal(str(obj.shipping_amount)), obj.currency, preferred_currency)
        except Exception:
            return obj.shipping_amount

    def get_discount_amount(self, obj):
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request, fallback=getattr(obj, 'currency', 'RUB'))
        try:
            return self._convert_money(Decimal(str(obj.discount_amount)), obj.currency, preferred_currency)
        except Exception:
            return obj.discount_amount

    def get_total_amount(self, obj):
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request, fallback=getattr(obj, 'currency', 'RUB'))
        try:
            return self._convert_money(Decimal(str(obj.total_amount)), obj.currency, preferred_currency)
        except Exception:
            return obj.total_amount

    def get_fields(self):
        fields = super().get_fields()
        # Прокидываем context (request) внутрь OrderItemSerializer, чтобы он тоже конвертировал.
        if 'items' in fields and hasattr(fields['items'], 'child'):
            fields['items'].child.context.update(self.context)
        return fields


class CreateOrderSerializer(serializers.Serializer):
    """
    Запрос на создание заказа из корзины
    """
    contact_name = serializers.CharField(max_length=150)
    contact_phone = serializers.CharField(max_length=32)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    shipping_address = serializers.IntegerField(required=False)
    shipping_address_text = serializers.CharField(required=False, allow_blank=True)
    shipping_method = serializers.CharField(required=False, allow_blank=True)
    payment_method = serializers.CharField(required=False, allow_blank=True)
    comment = serializers.CharField(required=False, allow_blank=True)
    promo_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    locale = serializers.CharField(required=False, allow_blank=True, max_length=10)

    def validate_shipping_address(self, value):
        # Валидация адреса доставки будет реализована при наличии пользователя
        return value
