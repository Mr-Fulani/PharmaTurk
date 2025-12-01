from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify

from apps.catalog.models import (
    Product,
    Category,
    ClothingProduct,
    ShoeProduct,
    ElectronicsProduct,
)
from .models import Cart, CartItem, Order, OrderItem, PromoCode

VARIANT_MODEL_MAP = {
    'clothing': ClothingProduct,
    'shoes': ShoeProduct,
    'electronics': ElectronicsProduct,
}

PRODUCT_TYPE_ALIASES = {
    'supplements': 'medicines',
    'tableware': 'clothing',
    'furniture': 'clothing',
    'medical-equipment': 'medicines',
}

CATEGORY_PRESETS = {
    'clothing': ('clothing-general', 'Одежда'),
    'shoes': ('shoes-general', 'Обувь'),
    'electronics': ('electronics-general', 'Электроника'),
    'tableware': ('tableware-serveware', 'Посуда'),
    'furniture': ('furniture-living', 'Мебель'),
    'medical-equipment': ('medical-equipment', 'Медицинское оборудование'),
}

BASE_PRODUCT_TYPES = {'medicines', 'supplements', 'medical-equipment'}


def normalize_product_type(value: str | None) -> str:
    if not value:
        return 'medicines'
    return value.lower()


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
    base_product_id = external.get('base_product_id')
    if base_product_id:
        try:
            return Product.objects.get(id=base_product_id)
        except Product.DoesNotExist:
            pass

    base_slug = external.get('base_product_slug') or slugify(f"{source_type}-{variant.slug}")
    category = get_or_create_category_for_variant(source_type) or get_or_create_category_for_variant(effective_type)
    defaults = {
        'name': variant.name,
        'slug': base_slug,
        'description': getattr(variant, 'description', '') or '',
        'price': getattr(variant, 'price', None) or 0,
        'currency': getattr(variant, 'currency', None) or 'TRY',
        'brand': getattr(variant, 'brand', None),
        'category': category,
        'is_available': getattr(variant, 'is_available', True),
        'main_image': getattr(variant, 'main_image', '') or '',
        'external_data': {
            'source_type': source_type,
            'effective_type': effective_type,
            'source_variant_id': variant.id,
            'source_variant_slug': variant.slug,
        },
    }
    product, created = Product.objects.get_or_create(slug=base_slug, defaults=defaults)
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
        main_image = getattr(variant, 'main_image', None)
        if main_image and product.main_image != main_image:
            product.main_image = main_image
            changed = True
        if category and product.category_id is None:
            product.category = category
            changed = True
        if getattr(variant, 'brand', None) and product.brand_id is None:
            product.brand = variant.brand
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
    product_slug = serializers.CharField(source='product.slug', read_only=True)
    product_image_url = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'product_name', 'product_slug', 'product_image_url',
            'quantity', 'price', 'currency', 'created_at', 'updated_at'
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
    Запрос на добавление товара в корзину
    """
    product_id = serializers.IntegerField(required=False)
    product_type = serializers.CharField(required=False)
    product_slug = serializers.CharField(required=False)
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate(self, attrs):
        product_id = attrs.get('product_id')
        product_type = attrs.get('product_type')
        product_slug = attrs.get('product_slug')

        if product_id:
            try:
                product = Product.objects.get(id=product_id, is_active=True)
            except Product.DoesNotExist:
                raise serializers.ValidationError(_("Товар не найден"))
            attrs['product'] = product
            return attrs

        if not product_type or not product_slug:
            raise serializers.ValidationError(_("Не удалось определить товар для добавления в корзину"))

        try:
            product = resolve_variant_product(product_type, product_slug)
        except Product.DoesNotExist:
            raise serializers.ValidationError(_("Товар не найден"))

        attrs['product'] = product
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
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'price', 'quantity', 'total']
        read_only_fields = ['product_name', 'price', 'total']


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
