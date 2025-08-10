from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Product
from .models import Cart, CartItem, Order, OrderItem


class CartItemSerializer(serializers.ModelSerializer):
    """
    Сериализатор позиции корзины
    """
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_slug = serializers.CharField(source='product.slug', read_only=True)

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'product_name', 'product_slug',
            'quantity', 'price', 'currency', 'created_at', 'updated_at'
        ]
        read_only_fields = ['price', 'currency', 'created_at', 'updated_at']


class CartSerializer(serializers.ModelSerializer):
    """
    Сериализатор корзины
    """
    items = CartItemSerializer(many=True, read_only=True)
    items_count = serializers.IntegerField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = [
            'id', 'user', 'session_key', 'currency',
            'items', 'items_count', 'total_amount',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at', 'items', 'items_count', 'total_amount']


class AddToCartSerializer(serializers.Serializer):
    """
    Запрос на добавление товара в корзину
    """
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate(self, attrs):
        try:
            product = Product.objects.get(id=attrs['product_id'], is_active=True)
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

    class Meta:
        model = Order
        fields = [
            'id', 'number', 'status', 'user',
            'subtotal_amount', 'shipping_amount', 'discount_amount', 'total_amount', 'currency',
            'contact_name', 'contact_phone', 'contact_email',
            'shipping_address', 'shipping_address_text', 'shipping_method',
            'payment_method', 'payment_status', 'comment',
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

    def validate_shipping_address(self, value):
        # Валидация адреса доставки будет реализована при наличии пользователя
        return value
