import logging
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, OpenApiExample
import uuid

from apps.catalog.models import Product
logger = logging.getLogger(__name__)
import uuid
from apps.users.models import UserAddress
from .models import Cart, CartItem, Order, OrderItem
from .serializers import (
    CartSerializer, CartItemSerializer, AddToCartSerializer, UpdateCartItemSerializer,
    OrderSerializer, CreateOrderSerializer
)


def _get_or_create_cart(request) -> Cart:
    """Получить или создать корзину для пользователя или сессии.
    Для анонимных клиентов поддерживаем пользовательский ключ из заголовка X-Cart-Session
    и из cookie cart_session (fallback для случаев, когда заголовок не передан).
    """
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None

    # 1) Ключ из заголовка (для фронтенда) или cookie (fallback)
    header_session = request.META.get('HTTP_X_CART_SESSION') or getattr(request, 'headers', {}).get('X-Cart-Session')
    cookie_session = getattr(request, 'COOKIES', {}).get('cart_session')
    custom_session = header_session or cookie_session

    # 2) Стандартная сессия Django
    django_session = None
    if hasattr(request, 'session'):
        django_session = request.session.session_key
        if not django_session:
            # Гарантируем наличие session_key, если потребуется
            request.session.save()
            django_session = request.session.session_key

    session_key = None
    if not user:
        session_key = custom_session or django_session
        if not session_key:
            session_key = str(uuid.uuid4())
            if hasattr(request, 'session'):
                request.session['cart_session_key'] = session_key

    # Если пользователь авторизован, сначала ищем его корзину
    if user:
        cart = Cart.objects.filter(user=user).first()
        
        # Если у пользователя есть корзина, но она пустая, проверяем анонимную корзину для переноса
        if cart and not cart.items.exists() and custom_session:
            anonymous_cart = Cart.objects.filter(session_key=custom_session, user=None).first()
            if anonymous_cart and anonymous_cart.items.exists():
                # Копируем товары из анонимной корзины в существующую корзину пользователя
                for item in anonymous_cart.items.all():
                    CartItem.objects.create(
                        cart=cart,
                        product=item.product,
                        quantity=item.quantity,
                        price=item.price,
                        currency=item.currency
                    )
                # Удаляем анонимную корзину
                anonymous_cart.delete()
                return cart
        
        if cart:
            # Если нашли корзину пользователя, возвращаем её
            return cart
        
        # Если у пользователя нет корзины, но есть анонимная корзина с session_key,
        # то переносим товары из анонимной корзины в корзину пользователя
        if custom_session:
            anonymous_cart = Cart.objects.filter(session_key=custom_session, user=None).first()
            if anonymous_cart and anonymous_cart.items.exists():
                # Создаем новую корзину для пользователя
                cart = Cart.objects.create(user=user, currency=anonymous_cart.currency)
                # Копируем товары из анонимной корзины
                for item in anonymous_cart.items.all():
                    CartItem.objects.create(
                        cart=cart,
                        product=item.product,
                        quantity=item.quantity,
                        price=item.price,
                        currency=item.currency
                    )
                # Удаляем анонимную корзину
                anonymous_cart.delete()
                return cart

    # Создаем новую корзину
    cart, created = Cart.objects.get_or_create(
        user=user if user else None,
        session_key='' if user else session_key,
        defaults={'currency': 'RUB'}  # Изменил на RUB для соответствия товарам
    )
    try:
        logger.info(
            "cart.resolve user=%s header_sid=%s cookie_sid=%s django_sid=%s resolved=%s created=%s",
            getattr(user, 'id', None), header_session, cookie_session, django_session, cart.session_key, created
        )
    except Exception:
        pass
    return cart


class CartViewSet(viewsets.ViewSet):
    """Управление корзиной."""
    permission_classes = [AllowAny]

    @extend_schema(
        description="Получить текущую корзину",
        responses=CartSerializer,
        examples=[
            OpenApiExample(
                'Пример корзины',
                value={
                    "id": 1,
                    "user": None,
                    "session_key": "abc123",
                    "currency": "USD",
                    "items": [
                        {
                            "id": 10,
                            "product": 1,
                            "product_name": "Test Product",
                            "product_slug": "test-product",
                            "quantity": 2,
                            "price": "10.00",
                            "currency": "USD"
                        }
                    ],
                    "items_count": 2,
                    "total_amount": "20.00"
                },
                response_only=True
            )
        ]
    )
    def list(self, request):
        cart = _get_or_create_cart(request)
        # Возвращаем корзину с предзагрузкой позиций и товаров
        cart = Cart.objects.filter(pk=cart.pk).prefetch_related('items', 'items__product').get()
        return Response(CartSerializer(cart).data)

    @extend_schema(
        description="Добавить товар в текущую корзину (анонимно по X-Cart-Session/cookie)",
        request=AddToCartSerializer,
        responses=CartSerializer,
        examples=[
            OpenApiExample(
                'Запрос',
                value={"product_id": 1, "quantity": 1},
                request_only=True
            ),
            OpenApiExample(
                'Ответ',
                value={
                    "id": 1,
                    "user": None,
                    "session_key": "abc123",
                    "currency": "USD",
                    "items": [
                        {
                            "id": 11,
                            "product": 1,
                            "product_name": "Test Product",
                            "product_slug": "test-product",
                            "quantity": 1,
                            "price": "10.00",
                            "currency": "USD"
                        }
                    ],
                    "items_count": 1,
                    "total_amount": "10.00"
                },
                response_only=True
            )
        ]
    )
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
        # Возвращаем свежую корзину с позициями
        cart = Cart.objects.filter(pk=cart.pk).prefetch_related('items', 'items__product').get()
        return Response(CartSerializer(cart).data)

    @extend_schema(
        description="Изменить количество позиции корзины",
        request=UpdateCartItemSerializer,
        responses=CartSerializer,
        examples=[
            OpenApiExample('Запрос', value={"quantity": 3}, request_only=True),
            OpenApiExample(
                'Ответ',
                value={
                    "id": 1,
                    "user": None,
                    "session_key": "abc123",
                    "currency": "USD",
                    "items": [
                        {
                            "id": 11,
                            "product": 1,
                            "product_name": "Test Product",
                            "product_slug": "test-product",
                            "quantity": 3,
                            "price": "10.00",
                            "currency": "USD"
                        }
                    ],
                    "items_count": 3,
                    "total_amount": "30.00"
                },
                response_only=True
            ),
        ]
    )
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
        cart = Cart.objects.filter(pk=cart.pk).prefetch_related('items', 'items__product').get()
        return Response(CartSerializer(cart).data)

    @extend_schema(
        description="Удалить позицию из корзины",
        responses=CartSerializer,
        examples=[
            OpenApiExample(
                'Ответ',
                value={
                    "id": 1,
                    "user": None,
                    "session_key": "abc123",
                    "currency": "USD",
                    "items": [],
                    "items_count": 0,
                    "total_amount": "0.00"
                },
                response_only=True
            )
        ]
    )
    @action(detail=True, methods=['delete'], url_path='remove')
    def remove_item(self, request, pk=None):
        cart = _get_or_create_cart(request)
        try:
            item = cart.items.get(pk=pk)
        except CartItem.DoesNotExist:
            return Response({"detail": _("Позиция не найдена")}, status=404)
        item.delete()
        cart = Cart.objects.filter(pk=cart.pk).prefetch_related('items', 'items__product').get()
        return Response(CartSerializer(cart).data)

    @extend_schema(
        description="Очистить корзину",
        responses=CartSerializer,
        examples=[
            OpenApiExample(
                'Ответ',
                value={
                    "id": 1,
                    "user": None,
                    "session_key": "abc123",
                    "currency": "USD",
                    "items": [],
                    "items_count": 0,
                    "total_amount": "0.00"
                },
                response_only=True
            )
        ]
    )
    @action(detail=False, methods=['post'], url_path='clear')
    def clear(self, request):
        cart = _get_or_create_cart(request)
        cart.items.all().delete()
        cart = Cart.objects.filter(pk=cart.pk).prefetch_related('items', 'items__product').get()
        return Response(CartSerializer(cart).data)


class OrderViewSet(viewsets.ViewSet):
    """Управление заказами."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        description="Список заказов текущего пользователя",
        responses=OrderSerializer(many=True),
        examples=[
            OpenApiExample(
                'Пример списка заказов',
                value=[
                    {
                        "id": 100,
                        "number": "ABC123456789",
                        "status": "new",
                        "subtotal_amount": "30.00",
                        "shipping_amount": "0.00",
                        "discount_amount": "0.00",
                        "total_amount": "30.00",
                        "currency": "USD",
                        "items": [
                            {"id": 1, "product": 1, "product_name": "Test Product", "price": "10.00", "quantity": 3, "total": "30.00"}
                        ]
                    }
                ],
                response_only=True
            )
        ]
    )
    def list(self, request):
        orders = Order.objects.filter(user=request.user).order_by('-created_at')
        return Response(OrderSerializer(orders, many=True).data)

    @extend_schema(
        description="Создать заказ из корзины",
        request=CreateOrderSerializer,
        responses=OrderSerializer,
        examples=[
            OpenApiExample(
                'Запрос',
                value={
                    "contact_name": "Иван Иванов",
                    "contact_phone": "+79990000000",
                    "contact_email": "ivan@example.com",
                    "shipping_address_text": "Москва, ул. Пушкина д.1",
                    "payment_method": "card",
                    "comment": "Позвонить курьеру"
                },
                request_only=True
            ),
            OpenApiExample(
                'Ответ',
                value={
                    "id": 101,
                    "number": "ZXC987654321",
                    "status": "new",
                    "subtotal_amount": "30.00",
                    "shipping_amount": "0.00",
                    "discount_amount": "0.00",
                    "total_amount": "30.00",
                    "currency": "USD",
                    "items": [
                        {"id": 1, "product": 1, "product_name": "Test Product", "price": "10.00", "quantity": 3, "total": "30.00"}
                    ]
                },
                response_only=True
            )
        ]
    )
    @action(detail=False, methods=['post'], url_path='create-from-cart')
    @transaction.atomic
    def create_from_cart(self, request):
        """Создание заказа из текущей корзины.
        Требует аутентификацию. Примеры запросов в Swagger.
        """
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
