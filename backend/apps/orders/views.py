import logging
import uuid

from django.http import Http404, HttpResponse
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import Product
from apps.users.models import UserAddress

from .models import Cart, CartItem, Order, OrderItem, PromoCode
from .serializers import (
    AddToCartSerializer,
    ApplyPromoCodeSerializer,
    CartItemSerializer,
    CartSerializer,
    CreateOrderSerializer,
    OrderReceiptSerializer,  # TODO: Функционал чеков временно отключен. Будет доработан позже.
    OrderSerializer,
    PromoCodeSerializer,
    UpdateCartItemSerializer,
)
from .services import build_order_receipt_payload, render_receipt_html  # TODO: Функционал чеков временно отключен. Будет доработан позже.
from .tasks import send_order_receipt_task  # TODO: Функционал чеков временно отключен. Будет доработан позже.

logger = logging.getLogger(__name__)


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
        # Возвращаем корзину с предзагрузкой позиций, товаров и изображений
        from django.db.models import Prefetch
        from apps.catalog.models import ProductImage
        cart = Cart.objects.filter(pk=cart.pk).prefetch_related(
            'items',
            Prefetch('items__product__images', queryset=ProductImage.objects.all().order_by('is_main', 'sort_order'))
        ).get()
        return Response(CartSerializer(cart).data)

    @extend_schema(
        description=(
            "Добавить товар в текущую корзину (анонимно по X-Cart-Session/cookie). "
            "Для базовых товаров передавайте product_id. Для вариантов одежды/обуви "
            "передавайте product_type + product_slug (slug варианта)."
        ),
        request=AddToCartSerializer,
        responses=CartSerializer,
        examples=[
            OpenApiExample(
                'Запрос',
                value={"product_id": 1, "quantity": 1},
                request_only=True
            ),
            OpenApiExample(
                'Запрос (вариант обуви)',
                value={"product_type": "shoes", "product_slug": "nike-air-force-white-42", "quantity": 1},
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
    @action(detail=False, methods=['post'], url_path=r'add/?')
    @extend_schema(
        description="Добавить товар в корзину (для вариантов обуви/одежды требуется размер).",
        request=AddToCartSerializer,
        responses=CartSerializer,
    )
    def add(self, request):
        cart = _get_or_create_cart(request)
        serializer = AddToCartSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as exc:
            # Логируем входящие данные и ошибки для диагностики проблем добавления
            logger.warning(
                "cart.add validation failed",
                extra={"data": dict(request.data), "errors": getattr(exc, "detail", str(exc))}
            )
            raise
        product = serializer.validated_data['product']
        quantity = serializer.validated_data['quantity']
        product_currency = getattr(product, "currency", None) or cart.currency or "USD"

        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            chosen_size=serializer.validated_data.get('chosen_size', ''),
            defaults={
                'quantity': quantity,
                'price': product.price or 0,
                'currency': product_currency,
                'chosen_size': serializer.validated_data.get('chosen_size', ''),
            }
        )
        if not created:
            # Если уже есть, обновляем цену/валюту по актуальному товару
            updated = False
            if item.price != (product.price or item.price):
                item.price = product.price or item.price
                updated = True
            if item.currency != product_currency:
                item.currency = product_currency
                updated = True
            item.quantity += quantity
            if updated:
                item.save(update_fields=['price', 'currency', 'quantity', 'updated_at'])
            else:
                item.save(update_fields=['quantity', 'updated_at'])

        # Синхронизируем валюту корзины под валюту последнего товара (простая модель)
        if cart.currency != product_currency:
            cart.currency = product_currency
            cart.save(update_fields=['currency', 'updated_at'])
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

    @extend_schema(
        description="Применить промокод к корзине",
        request=ApplyPromoCodeSerializer,
        responses=CartSerializer,
        examples=[
            OpenApiExample(
                'Запрос',
                value={"code": "SUMMER2024"},
                request_only=True
            ),
            OpenApiExample(
                'Ответ',
                value={
                    "id": 1,
                    "user": None,
                    "session_key": "abc123",
                    "currency": "USD",
                    "items": [],
                    "items_count": 0,
                    "total_amount": "100.00",
                    "discount_amount": "10.00",
                    "final_amount": "90.00",
                    "promo_code": {
                        "id": 1,
                        "code": "SUMMER2024",
                        "discount_type": "percent",
                        "discount_value": "10.00"
                    }
                },
                response_only=True
            )
        ]
    )
    @action(detail=False, methods=['post'], url_path='apply-promo')
    def apply_promo(self, request):
        """Применить промокод к корзине."""
        cart = _get_or_create_cart(request)
        serializer = ApplyPromoCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        code = serializer.validated_data['code']
        try:
            promo_code = PromoCode.objects.get(code=code)
        except PromoCode.DoesNotExist:
            return Response({"detail": _("Промокод не найден")}, status=404)
        
        # Проверка валидности промокода
        is_valid, error = promo_code.is_valid(user=request.user if request.user.is_authenticated else None, cart_total=float(cart.total_amount))
        if not is_valid:
            return Response({"detail": error}, status=400)
        
        # Применяем промокод
        cart.promo_code = promo_code
        cart.save()
        
        # Возвращаем обновленную корзину
        cart = Cart.objects.filter(pk=cart.pk).prefetch_related('items', 'items__product').get()
        return Response(CartSerializer(cart).data)

    @extend_schema(
        description="Удалить промокод из корзины",
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
                    "total_amount": "100.00",
                    "discount_amount": "0.00",
                    "final_amount": "100.00",
                    "promo_code": None
                },
                response_only=True
            )
        ]
    )
    @action(detail=False, methods=['post'], url_path='remove-promo')
    def remove_promo(self, request):
        """Удалить промокод из корзины."""
        cart = _get_or_create_cart(request)
        cart.promo_code = None
        cart.save()
        
        # Возвращаем обновленную корзину
        cart = Cart.objects.filter(pk=cart.pk).prefetch_related('items', 'items__product').get()
        return Response(CartSerializer(cart).data)


class OrderViewSet(viewsets.ViewSet):
    """Управление заказами."""
    permission_classes = [IsAuthenticated]

    def _get_order_for_user(self, user, number: str) -> Order:
        try:
            return (
                Order.objects.filter(user=user, number=number)
                .select_related('user', 'shipping_address', 'promo_code')
                .prefetch_related('items')
                .get()
            )
        except Order.DoesNotExist:
            raise Http404(_("Заказ не найден"))

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
        from django.db.models import Prefetch
        from apps.catalog.models import ProductImage
        
        orders = (
            Order.objects
            .filter(user=request.user)
            .select_related('promo_code')
            .prefetch_related(
                Prefetch(
                    'items__product__images',
                    queryset=ProductImage.objects.all().order_by('is_main', 'sort_order')
                )
            )
            .order_by('-created_at')
        )
        return Response(OrderSerializer(orders, many=True).data)

    def retrieve(self, request, pk=None):
        order = Order.objects.filter(user=request.user, pk=pk).prefetch_related('items').first()
        if not order:
            raise Http404(_("Заказ не найден"))
        return Response(OrderSerializer(order).data)

    @extend_schema(description="Получить заказ по номеру", responses=OrderSerializer)
    @action(detail=False, methods=['get'], url_path=r'by-number/(?P<number>[^/]+)')
    def by_number(self, request, number: str):
        order = self._get_order_for_user(request.user, number)
        return Response(OrderSerializer(order).data)

    # TODO: Функционал чеков временно отключен. Будет доработан позже.
    # Включает: формирование чека, отправку по email, интеграцию с админкой.
    @extend_schema(description="Получить подготовленный чек по заказу", responses=OrderReceiptSerializer)
    @action(detail=False, methods=['get'], url_path=r'receipt/(?P<number>[^/]+)')
    def receipt(self, request, number: str):
        order = self._get_order_for_user(request.user, number)
        receipt = build_order_receipt_payload(order)
        if request.query_params.get('format') == 'html':
            html = render_receipt_html(order, receipt)
            return HttpResponse(html)
        serializer = OrderReceiptSerializer(receipt)
        return Response(serializer.data)

    # TODO: Функционал чеков временно отключен. Будет доработан позже.
    # Включает: формирование чека, отправку по email, интеграцию с админкой.
    @extend_schema(description="Отправить чек по email", request=None, responses=None)
    @action(detail=False, methods=['post'], url_path=r'send-receipt/(?P<number>[^/]+)')
    def send_receipt(self, request, number: str):
        order = self._get_order_for_user(request.user, number)
        email = request.data.get('email') or order.contact_email or (order.user.email if order.user else None)
        if not email:
            return Response({"detail": _("Не указан email для отправки чека")}, status=400)
        try:
            email = serializers.EmailField().to_internal_value(email)
        except serializers.ValidationError:
            return Response({"detail": _("Укажите корректный email")}, status=400)
        send_order_receipt_task.delay(order.id, email)
        return Response({"detail": _("Чек будет отправлен на %(email)s") % {"email": email}})

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

        # Расчет сумм
        subtotal = sum((i.price * i.quantity for i in cart.items.all()))
        shipping = 0
        discount = 0
        promo_code = None

        # Проверка и применение промокода из корзины или из запроса
        promo_code_value = serializer.validated_data.get('promo_code') or (cart.promo_code.code if cart.promo_code else None)
        if promo_code_value:
            try:
                promo_code = PromoCode.objects.get(code=promo_code_value.upper())
                # Проверка валидности промокода
                is_valid, error = promo_code.is_valid(user=request.user, cart_total=float(subtotal))
                if is_valid:
                    discount = promo_code.calculate_discount(subtotal)
                    # Увеличиваем счетчик использований
                    promo_code.used_count += 1
                    promo_code.save(update_fields=['used_count'])
                else:
                    promo_code = None
            except PromoCode.DoesNotExist:
                pass

        total = subtotal + shipping - discount

        # Генерация номера заказа
        number = uuid.uuid4().hex[:12].upper()

        order = Order.objects.create(
            user=request.user,
            number=number,
            subtotal_amount=subtotal,
            shipping_amount=shipping,
            discount_amount=discount,
            total_amount=total,
            currency=cart.currency,
            promo_code=promo_code,
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
                chosen_size=item.chosen_size,
                price=item.price,
                quantity=item.quantity,
                total=item.price * item.quantity,
            )

        # Очищаем корзину
        cart.items.all().delete()

        return Response(OrderSerializer(order).data, status=201)
