from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify

from apps.catalog.models import (
    Product,
    Category,
    ClothingProduct,
    ShoeProduct,
    ElectronicsProduct,
    ClothingVariant,
    ShoeVariant,
)
from .models import Cart, CartItem, Order, OrderItem, PromoCode

VARIANT_MODEL_MAP = {
    'clothing': ClothingVariant,
    'shoes': ShoeVariant,
    'electronics': ElectronicsProduct,
}

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

CATEGORY_PRESETS = {
    'clothing': ('clothing-general', 'Одежда'),
    'shoes': ('shoes-general', 'Обувь'),
    'electronics': ('electronics-general', 'Электроника'),
    'medical_equipment': ('medical-equipment', 'Медицинская техника'),
}

BASE_PRODUCT_TYPES = {
    'medicines',
    'supplements',
    'medical_equipment',
    'tableware',
    'furniture',
    'accessories',
    'jewelry',
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
    defaults = {
        'name': getattr(base_obj, 'name', slug),
        'slug': slug,
        'description': getattr(base_obj, 'description', '') or '',
        'price': getattr(base_obj, 'price', None) or 0,
        'currency': getattr(base_obj, 'currency', None) or 'TRY',
        'brand': getattr(base_obj, 'brand', None),
        # У базовой модели обуви/одежды категория относится к ShoeCategory/ClothingCategory,
        # поэтому для общего Product оставляем category пустым.
        'category': None,
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
    preset = CATEGORY_PRESETS.get(product_type)
    if not preset:
        return None
    slug, name = preset
    category, _ = Category.objects.get_or_create(
        slug=slug,
        defaults={'name': name, 'description': name, 'is_active': True}
    )
    return category


def ensure_product_from_variant(variant, source_type: str, effective_type: str) -> Product:
    external = variant.external_data or {}
    product = None
    base_product_id = external.get('base_product_id')
    if base_product_id:
        try:
            product = Product.objects.get(id=base_product_id)
        except Product.DoesNotExist:
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

    base_slug = external.get('base_product_slug') or slugify(f"{source_type}-{variant.slug}")
    category = get_or_create_category_for_variant(source_type) or get_or_create_category_for_variant(effective_type)
    parent_product = getattr(variant, "product", None)
    brand = getattr(variant, "brand", None) if hasattr(variant, "brand") else None
    if not brand and parent_product:
        brand = getattr(parent_product, "brand", None)
    main_image_candidate = _variant_main_image(variant) or (getattr(parent_product, "main_image", "") if parent_product else "")
    defaults = {
        'name': variant.name or (parent_product.name if parent_product else ""),
        'slug': base_slug,
        'description': getattr(variant, 'description', '') or (getattr(parent_product, "description", "") if parent_product else ''),
        'price': getattr(variant, 'price', None) or (getattr(parent_product, "price", None) or 0),
        'currency': getattr(variant, 'currency', None) or (getattr(parent_product, "currency", None) or 'TRY'),
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
        availability = getattr(variant, 'is_available', True)
        if product.is_available != availability:
            product.is_available = availability
            changed = True
        main_image = _variant_main_image(variant)
        if main_image and product.main_image != main_image:
            product.main_image = main_image
            changed = True
        # Обновляем тип продукта, если раньше был сохранён неверно (например, остался "medicines")
        if product.product_type != effective_type:
            product.product_type = effective_type
            changed = True
        if category and product.category_id is None:
            product.category = category
            changed = True
        if brand and product.brand_id is None:
            product.brand = brand
            changed = True
        if changed:
            product.save()

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

    # Базовая карточка без вариантов (обувь/одежда), если slug есть в соответствующей модели
    base_model_map = {
        'shoes': ShoeProduct,
        'clothing': ClothingProduct,
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
    chosen_size = serializers.CharField(read_only=True)

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'product_name', 'product_slug', 'product_type', 'product_image_url',
            'quantity', 'price', 'currency', 'chosen_size', 'created_at', 'updated_at'
        ]
        read_only_fields = ['price', 'currency', 'created_at', 'updated_at']
    
    def get_product_image_url(self, obj):
        """Получение URL изображения товара"""
        product = obj.product
        if not product:
            return None
        
        # Сначала проверяем main_image
        if product.main_image:
            return product.main_image
        
        # Затем ищем главное изображение в связанных изображениях
        main_img = product.images.filter(is_main=True).first()
        if main_img:
            return main_img.image_url
        
        # Если нет главного, берем первое изображение
        first_img = product.images.first()
        if first_img:
            return first_img.image_url
        
        return None

    def get_product_slug(self, obj):
        """Для варианта возвращаем исходный slug варианта, если сохранён в external_data."""
        product = obj.product
        if not product:
            return None
        ext = getattr(product, "external_data", {}) or {}
        return ext.get("source_variant_slug") or product.slug


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
        """Валидация кода промокода."""
        try:
            promo_code = PromoCode.objects.get(code=value.upper())
        except PromoCode.DoesNotExist:
            raise serializers.ValidationError(_("Промокод не найден"))
        return value.upper()


class CartSerializer(serializers.ModelSerializer):
    """
    Сериализатор корзины
    """
    items = CartItemSerializer(many=True, read_only=True)
    items_count = serializers.IntegerField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    final_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    promo_code = PromoCodeSerializer(read_only=True)

    class Meta:
        model = Cart
        fields = [
            'id', 'user', 'session_key', 'currency',
            'items', 'items_count', 'total_amount', 'discount_amount', 'final_amount',
            'promo_code',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at', 'items', 'items_count', 'total_amount', 'discount_amount', 'final_amount']


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

        # Сначала пробуем базовый товар по slug (это также покрывает случаи, когда фронт прислал slug родителя)
        base = Product.objects.filter(slug=product_slug, is_active=True).first()
        if base:
            attrs['product'] = base
            attrs['chosen_size'] = chosen_size
            return attrs

        # Проверяем вариант напрямую, чтобы валидировать размер
        variant = None
        normalized = normalize_product_type(effective_type)
        variant_model = VARIANT_MODEL_MAP.get(normalized)
        if variant_model and variant_model in (ClothingVariant, ShoeVariant):
            variant = variant_model.objects.filter(slug=product_slug, is_active=True).first()
            if not variant:
                raise serializers.ValidationError({"detail": _("Вариант не найден по slug")})
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
    
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'product_slug', 'product_image_url', 'chosen_size', 'price', 'quantity', 'total']
        read_only_fields = ['product_name', 'price', 'total', 'product_slug', 'product_image_url']
    
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

    def validate_shipping_address(self, value):
        # Валидация адреса доставки будет реализована при наличии пользователя
        return value
