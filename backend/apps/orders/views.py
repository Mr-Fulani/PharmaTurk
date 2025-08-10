from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
import uuid

from apps.catalog.models import Product
from apps.users.models import UserAddress
from .models import Cart, CartItem, Order, OrderItem
from .serializers import (
    CartSerializer, CartItemSerializer, AddToCartSerializer, UpdateCartItemSerializer,
    OrderSerializer, CreateOrderSerializer
)


def _get_or_create_cart(request) -> Cart:
    """Получить или создать корзину для пользователя или сессии."""
    user = request.user if request.user.is_authenticated else None
    session_key = request.session.session_key
    if not session_key:
        session_key = str(uuid.uuid4())
        request.session['cart_session_key'] = session_key
    
    cart, _ = Cart.objects.get_or_create(
        user=user if user else None,
        session_key='' if user else session_key,
        defaults={'currency': 'USD'}
    )
    return cart


class CartViewSet(viewsets.ViewSet):
    """Управление корзиной."""
    permission_classes = [AllowAny]

    @extend_schema(responses=CartSerializer)
    def list(self, request):
        cart = _get_or_create_cart(request)
        return Response(CartSerializer(cart).data)

    @extend_schema(request=AddToCartSerializer, responses=CartSerializer)
    @action(detail=False, methods=['post'], url_path='add')
    def add(self, request):
        cart = _get_or_create_cart(request)
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data['product']
        quantity = serializer.validated_data['quantity']

        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={
                'quantity': quantity,
                'price': product.price or 0,
                'currency': cart.currency,
            }
        )
        if not created:
            item.quantity += quantity
            item.save()
        return Response(CartSerializer(cart).data)

    @extend_schema(request=UpdateCartItemSerializer, responses=CartSerializer)
    @action(detail=True, methods=['post'], url_path='update')
    def update_item(self, request, pk=None):
        cart = _get_or_create_cart(request)
        try:
            item = cart.items.get(pk=pk)
        except CartItem.DoesNotExist:
            return Response({"detail": _("Позиция не найдена")}, status=404)
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item.quantity = serializer.validated_data['quantity']
        item.save()
        return Response(CartSerializer(cart).data)

    @extend_schema(responses=CartSerializer)
    @action(detail=True, methods=['delete'], url_path='remove')
    def remove_item(self, request, pk=None):
        cart = _get_or_create_cart(request)
        try:
            item = cart.items.get(pk=pk)
        except CartItem.DoesNotExist:
            return Response({"detail": _("Позиция не найдена")}, status=404)
        item.delete()
        return Response(CartSerializer(cart).data)

    @extend_schema(responses=CartSerializer)
    @action(detail=False, methods=['post'], url_path='clear')
    def clear(self, request):
        cart = _get_or_create_cart(request)
        cart.items.all().delete()
        return Response(CartSerializer(cart).data)


class OrderViewSet(viewsets.ViewSet):
    """Управление заказами."""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OrderSerializer(many=True))
    def list(self, request):
        orders = Order.objects.filter(user=request.user).order_by('-created_at')
        return Response(OrderSerializer(orders, many=True).data)

    @extend_schema(request=CreateOrderSerializer, responses=OrderSerializer)
    @action(detail=False, methods=['post'], url_path='create-from-cart')
    @transaction.atomic
    def create_from_cart(self, request):
        cart = _get_or_create_cart(request)
        if cart.items.count() == 0:
            return Response({"detail": _("Корзина пуста")}, status=400)
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Генерация номера заказа
        number = uuid.uuid4().hex[:12].upper()

        order = Order.objects.create(
            user=request.user,
            number=number,
            subtotal_amount=sum((i.price * i.quantity for i in cart.items.all())),
            shipping_amount=0,
            discount_amount=0,
            total_amount=sum((i.price * i.quantity for i in cart.items.all())),
            currency=cart.currency,
            contact_name=serializer.validated_data.get('contact_name'),
            contact_phone=serializer.validated_data.get('contact_phone'),
            contact_email=serializer.validated_data.get('contact_email', ''),
            shipping_method=serializer.validated_data.get('shipping_method', ''),
            payment_method=serializer.validated_data.get('payment_method', ''),
            comment=serializer.validated_data.get('comment', ''),
        )

        # Адрес доставки
        shipping_address_id = serializer.validated_data.get('shipping_address')
        if shipping_address_id:
            try:
                addr = UserAddress.objects.get(id=shipping_address_id, user=request.user)
                order.shipping_address = addr
                order.shipping_address_text = f"{addr.country}, {addr.city}, {addr.street} {addr.house}"
                order.save()
            except UserAddress.DoesNotExist:
                pass
        else:
            order.shipping_address_text = serializer.validated_data.get('shipping_address_text', '')
            order.save()

        # Позиции заказа
        for item in cart.items.all():
            OrderItem.objects.create(
                order=order,
                product=item.product,
                product_name=item.product.name,
                price=item.price,
                quantity=item.quantity,
                total=item.price * item.quantity,
            )

        # Очищаем корзину
        cart.items.all().delete()

        return Response(OrderSerializer(order).data, status=201)
