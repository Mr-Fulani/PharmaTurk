import logging
import uuid
from decimal import Decimal
from typing import Optional, Tuple

from django.conf import settings
from django.http import Http404, HttpResponse
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import (
    Product,
    ClothingProduct,
    ClothingProductSize,
    ClothingVariant,
    ClothingVariantSize,
    ShoeProduct,
    ShoeProductSize,
    ShoeVariant,
    ShoeVariantSize,
)
from apps.users.models import UserAddress

from .models import Cart, CartItem, Order, OrderItem, PromoCode

# Crypto payment (lazy to avoid circular import / optional dependency)
def _create_crypto_invoice(number: str, total, cart_currency: str, locale: str = "") -> tuple[dict | None, dict | None]:
    """Создаёт инвойс. Возвращает (invoice_data, payment_data) или (None, None) при ошибке.
    Инвойс создаётся ДО создания заказа, чтобы не терять корзину при ошибке провайдера.
    locale: язык пользователя (ru/en) — для сохранения при редиректе после оплаты.
    """
    from apps.payments.providers.coinremitter import create_invoice
    from apps.payments.providers.dummy import create_invoice_dummy

    site = (getattr(settings, "SITE_URL", None) or "").rstrip("/")
    frontend = (getattr(settings, "FRONTEND_SITE_URL", None) or "").rstrip("/") or site
    notify_url = f"{site}/api/payments/crypto/webhook/" if site else ""
    # Next.js i18n: defaultLocale=en без префикса, ru — с /ru/
    loc = (locale or "").strip().lower()
    if loc not in ("ru", "en"):
        loc = "en"
    path_prefix = f"/{loc}" if loc == "ru" else ""
    success_path = f"{path_prefix}/checkout-success" if path_prefix else "/checkout-success"
    fail_path = f"{path_prefix}/checkout-crypto" if path_prefix else "/checkout-crypto"
    q = f"number={number}&locale={loc}"
    success_url = f"{frontend}{success_path}?{q}" if frontend else ""
    fail_url = f"{frontend}{fail_path}?{q}" if frontend else ""
    fiat_currency = (cart_currency or "USD").upper()[:3]

    invoice_data = create_invoice(
        amount_fiat=float(total),
        fiat_currency=fiat_currency,
        order_number=number,
        notify_url=notify_url,
        success_url=success_url,
        fail_url=fail_url,
        expiry_minutes=30,
        description=f"Order {number}",
    )
    if not invoice_data and getattr(settings, "DEBUG", False):
        logger.warning(
            "CoinRemitter create_invoice failed, using dummy (API key set: %s). "
            "Check COINREMITTER_API_KEY, COINREMITTER_API_PASSWORD and backend logs.",
            bool(getattr(settings, "COINREMITTER_API_KEY", "")),
        )
        invoice_data = create_invoice_dummy(
            amount_fiat=float(total),
            fiat_currency=fiat_currency,
            order_number=number,
            notify_url=notify_url,
            success_url=success_url,
            fail_url=fail_url,
            expiry_minutes=30,
            description=f"Order {number}",
        )
    if not invoice_data:
        return None, None

    expires_at = invoice_data.get("expires_at") or (timezone.now() + timezone.timedelta(minutes=30))
    payment_data = {
        "address": invoice_data["address"],
        "qr_code": invoice_data.get("qr_code") or "",
        "amount": str(invoice_data["amount"]),
        "amount_usd": str(invoice_data["amount_usd"]),
        "currency": fiat_currency,
        "expires_at": expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at),
        "invoice_url": invoice_data.get("invoice_url") or "",
    }
    return invoice_data, payment_data


def _save_crypto_payment(order, invoice_data: dict, cart_currency: str):
    """Сохраняет CryptoPayment после создания заказа."""
    from apps.payments.models import CryptoPayment

    fiat_currency = (cart_currency or "USD").upper()[:3]
    expires_at = invoice_data.get("expires_at") or (timezone.now() + timezone.timedelta(minutes=30))
    provider = "dummy" if invoice_data.get("invoice_id", "").startswith("dummy-") else "coinremitter"

    CryptoPayment.objects.create(
        order=order,
        provider=provider,
        invoice_id=invoice_data["invoice_id"],
        address=invoice_data["address"],
        amount_crypto=invoice_data["amount"],
        amount_fiat=invoice_data["amount_usd"],
        currency=invoice_data.get("currency") or fiat_currency,
        status="pending",
        qr_code_url=invoice_data.get("qr_code") or "",
        invoice_url=invoice_data.get("invoice_url") or "",
        expires_at=expires_at,
    )
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


def _get_preferred_currency(request, fallback: str = 'RUB') -> str:
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
    return fallback


def _get_product_price_for_currency(product, currency: str):
    currency = (currency or 'RUB').upper()
    try:
        prices = product.get_all_prices() or {}
        if currency in prices:
            value = prices[currency].get('price_with_margin')
            if value is not None:
                return Decimal(str(value))
    except Exception:
        pass
    try:
        return Decimal(str(getattr(product, 'price', 0) or 0))
    except Exception:
        return Decimal('0')


def _get_stock_for_cart_product(product: Product, chosen_size: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """Возвращает доступный остаток (или None, если лимита нет) и человеко-читаемый источник.

    Приоритет:
    1) Размер варианта одежды/обуви (если есть source_variant_id и задан chosen_size)
    2) Вариант одежды/обуви (если есть source_variant_id)
    3) Базовый Product.stock_quantity

    None означает "не ограничено".
    """
    external = getattr(product, "external_data", None) or {}
    source_variant_id = external.get("source_variant_id")
    source_type = (external.get("source_type") or "").lower()
    source_id = external.get("source_id")

    normalized_type = (getattr(product, "product_type", None) or "").lower()
    size_value = (chosen_size or "").strip()

    if source_variant_id and normalized_type in {"clothing", "shoes"}:
        if normalized_type == "clothing":
            variant = ClothingVariant.objects.filter(id=source_variant_id, is_active=True).first()
            if not variant:
                return product.stock_quantity, "product"
            if size_value:
                size_obj = ClothingVariantSize.objects.filter(variant=variant, size=size_value).first()
                if size_obj and size_obj.stock_quantity is not None:
                    return size_obj.stock_quantity, "variant_size"
            if variant.stock_quantity is not None:
                return variant.stock_quantity, "variant"
        if normalized_type == "shoes":
            variant = ShoeVariant.objects.filter(id=source_variant_id, is_active=True).first()
            if not variant:
                return product.stock_quantity, "product"
            if size_value:
                size_obj = ShoeVariantSize.objects.filter(variant=variant, size=size_value).first()
                if size_obj and size_obj.stock_quantity is not None:
                    return size_obj.stock_quantity, "variant_size"
            if variant.stock_quantity is not None:
                return variant.stock_quantity, "variant"

    if source_type == "base_clothing":
        base_obj = ClothingProduct.objects.filter(id=source_id, is_active=True).first()
        if base_obj and size_value:
            size_obj = ClothingProductSize.objects.filter(product=base_obj, size=size_value).first()
            if size_obj and size_obj.stock_quantity is not None:
                return size_obj.stock_quantity, "product_size"

    if source_type == "base_shoes":
        base_obj = ShoeProduct.objects.filter(id=source_id, is_active=True).first()
        if base_obj and size_value:
            size_obj = ShoeProductSize.objects.filter(product=base_obj, size=size_value).first()
            if size_obj and size_obj.stock_quantity is not None:
                return size_obj.stock_quantity, "product_size"

    return product.stock_quantity, "product"


def _decrement_stock_for_cart_item(product: Product, chosen_size: Optional[str], quantity: int) -> None:
    """Атомарно списывает остаток (если он ограничен).

    Должно вызываться внутри transaction.atomic().
    """
    if quantity <= 0:
        return

    external = getattr(product, "external_data", None) or {}
    source_variant_id = external.get("source_variant_id")
    source_type = (external.get("source_type") or "").lower()
    source_id = external.get("source_id")
    normalized_type = (getattr(product, "product_type", None) or "").lower()
    size_value = (chosen_size or "").strip()

    if source_variant_id and normalized_type in {"clothing", "shoes"}:
        if normalized_type == "clothing":
            variant = ClothingVariant.objects.select_for_update().filter(id=source_variant_id, is_active=True).first()
            if not variant:
                source_variant_id = None
            else:
                if size_value:
                    size_obj = ClothingVariantSize.objects.select_for_update().filter(variant=variant, size=size_value).first()
                    if size_obj and size_obj.stock_quantity is not None:
                        if size_obj.stock_quantity < quantity:
                            raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                        size_obj.stock_quantity = size_obj.stock_quantity - quantity
                        if size_obj.stock_quantity == 0:
                            size_obj.is_available = False
                        size_obj.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                        return
                if variant.stock_quantity is not None:
                    if variant.stock_quantity < quantity:
                        raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                    variant.stock_quantity = variant.stock_quantity - quantity
                    if variant.stock_quantity == 0:
                        variant.is_available = False
                    variant.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                    return

        if normalized_type == "shoes":
            variant = ShoeVariant.objects.select_for_update().filter(id=source_variant_id, is_active=True).first()
            if not variant:
                source_variant_id = None
            else:
                if size_value:
                    size_obj = ShoeVariantSize.objects.select_for_update().filter(variant=variant, size=size_value).first()
                    if size_obj and size_obj.stock_quantity is not None:
                        if size_obj.stock_quantity < quantity:
                            raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                        size_obj.stock_quantity = size_obj.stock_quantity - quantity
                        if size_obj.stock_quantity == 0:
                            size_obj.is_available = False
                        size_obj.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                        return
                if variant.stock_quantity is not None:
                    if variant.stock_quantity < quantity:
                        raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                    variant.stock_quantity = variant.stock_quantity - quantity
                    if variant.stock_quantity == 0:
                        variant.is_available = False
                    variant.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                    return

    if source_type == "base_clothing":
        base_obj = ClothingProduct.objects.select_for_update().filter(id=source_id, is_active=True).first()
        if base_obj and size_value:
            size_obj = ClothingProductSize.objects.select_for_update().filter(
                product=base_obj, size=size_value
            ).first()
            if size_obj and size_obj.stock_quantity is not None:
                if size_obj.stock_quantity < quantity:
                    raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                size_obj.stock_quantity = size_obj.stock_quantity - quantity
                if size_obj.stock_quantity == 0:
                    size_obj.is_available = False
                size_obj.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                return

    if source_type == "base_shoes":
        base_obj = ShoeProduct.objects.select_for_update().filter(id=source_id, is_active=True).first()
        if base_obj and size_value:
            size_obj = ShoeProductSize.objects.select_for_update().filter(
                product=base_obj, size=size_value
            ).first()
            if size_obj and size_obj.stock_quantity is not None:
                if size_obj.stock_quantity < quantity:
                    raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                size_obj.stock_quantity = size_obj.stock_quantity - quantity
                if size_obj.stock_quantity == 0:
                    size_obj.is_available = False
                size_obj.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                return

    # fallback: Product
    locked_product = Product.objects.select_for_update().get(pk=product.pk)
    if locked_product.stock_quantity is None:
        return
    if locked_product.stock_quantity < quantity:
        raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
    locked_product.stock_quantity = locked_product.stock_quantity - quantity
    if locked_product.stock_quantity == 0:
        locked_product.is_available = False
    locked_product.save(update_fields=["stock_quantity", "is_available", "updated_at"])


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
        return Response(CartSerializer(cart, context={'request': request}).data)

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
        preferred_currency = _get_preferred_currency(request, fallback=cart.currency or 'RUB')
        item_price = _get_product_price_for_currency(product, preferred_currency)
        chosen_size = serializer.validated_data.get('chosen_size', '')

        # Проверка остатка (учитываем суммарное количество в корзине)
        existing = CartItem.objects.filter(cart=cart, product=product, chosen_size=chosen_size).first()
        new_total_qty = quantity + (existing.quantity if existing else 0)
        available_stock, _source = _get_stock_for_cart_product(product, chosen_size)
        if available_stock is not None and new_total_qty > available_stock:
            raise serializers.ValidationError({
                "detail": _("Недостаточно товара в наличии"),
                "available": available_stock,
            })

        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            chosen_size=chosen_size,
            defaults={
                'quantity': quantity,
                'price': item_price,
                'currency': preferred_currency,
                'chosen_size': chosen_size,
            }
        )
        if not created:
            # Если уже есть, обновляем цену/валюту по актуальному товару
            updated = False
            if item.price != item_price:
                item.price = item_price
                updated = True
            if item.currency != preferred_currency:
                item.currency = preferred_currency
                updated = True
            item.quantity += quantity
            if updated:
                item.save(update_fields=['price', 'currency', 'quantity', 'updated_at'])
            else:
                item.save(update_fields=['quantity', 'updated_at'])

        # Синхронизируем валюту корзины под валюту последнего товара (простая модель)
        if cart.currency != preferred_currency:
            cart.currency = preferred_currency
            cart.save(update_fields=['currency', 'updated_at'])
        # Возвращаем свежую корзину с позициями
        cart = Cart.objects.filter(pk=cart.pk).prefetch_related('items', 'items__product').get()
        return Response(CartSerializer(cart, context={'request': request}).data)

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

        desired_qty = serializer.validated_data['quantity']
        available_stock, _source = _get_stock_for_cart_product(item.product, item.chosen_size)
        if available_stock is not None and desired_qty > available_stock:
            raise serializers.ValidationError({
                "detail": _("Недостаточно товара в наличии"),
                "available": available_stock,
            })

        item.quantity = desired_qty
        item.save()
        cart = Cart.objects.filter(pk=cart.pk).prefetch_related('items', 'items__product').get()
        return Response(CartSerializer(cart, context={'request': request}).data)

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
        logger.info("apply_promo: request.data=%s", request.data)
        serializer = ApplyPromoCodeSerializer(data=request.data)
        if not serializer.is_valid():
            err_msg = serializer.errors.get("code", [serializer.errors])[0]
            if isinstance(err_msg, list):
                err_msg = err_msg[0] if err_msg else _("Неверные данные")
            logger.warning("apply_promo: validation failed: %s", serializer.errors)
            return Response({"detail": str(err_msg)}, status=400)
        
        code = serializer.validated_data['code']
        try:
            promo_code = PromoCode.objects.get(code__iexact=code)
        except PromoCode.DoesNotExist:
            return Response({"detail": _("Промокод не найден")}, status=404)
        
        # Для валидности промокода используем те же числа, что и при create_from_cart:
        # сумму по сохранённым CartItem.price (цена на момент добавления).
        cart_total = float(sum((i.price * i.quantity for i in cart.items.all())))
        cart_currency = cart.currency

        # Проверка валидности промокода
        is_valid, error = promo_code.is_valid(
            user=request.user if request.user.is_authenticated else None,
            cart_total=cart_total,
            cart_currency=cart_currency,
        )
        if not is_valid:
            logger.info("apply_promo: promo %s invalid: %s (cart_total=%s, currency=%s)", code, error, cart_total, cart_currency)
            return Response({"detail": error}, status=400)
        
        # Применяем промокод
        cart.promo_code = promo_code
        cart.save()
        
        # Возвращаем обновленную корзину
        cart = Cart.objects.filter(pk=cart.pk).prefetch_related('items', 'items__product').get()
        return Response(CartSerializer(cart, context={'request': request}).data)

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
        return Response(OrderSerializer(orders, many=True, context={'request': request}).data)

    def retrieve(self, request, pk=None):
        order = Order.objects.filter(user=request.user, pk=pk).prefetch_related('items').first()
        if not order:
            raise Http404(_("Заказ не найден"))
        return Response(OrderSerializer(order, context={'request': request}).data)

    @extend_schema(description="Получить заказ по номеру", responses=OrderSerializer)
    @action(detail=False, methods=['get'], url_path=r'by-number/(?P<number>[^/]+)')
    def by_number(self, request, number: str):
        order = self._get_order_for_user(request.user, number)
        data = OrderSerializer(order, context={'request': request}).data
        if order.payment_method == 'crypto' and order.status == Order.OrderStatus.PENDING_PAYMENT:
            try:
                from apps.payments.models import CryptoPayment
                cp = CryptoPayment.objects.get(order=order)
                if cp.status == 'pending':
                    data['payment_data'] = {
                        'address': cp.address,
                        'qr_code': cp.qr_code_url,
                        'amount': str(cp.amount_crypto),
                        'amount_usd': str(cp.amount_fiat),
                        'currency': cp.currency,
                        'expires_at': cp.expires_at.isoformat() if cp.expires_at else '',
                        'invoice_url': cp.invoice_url or '',
                    }
            except Exception:
                pass
        return Response(data)

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
        
        # Расчет стоимости доставки на основе вариантов в корзине
        shipping = 0
        from apps.catalog.currency_models import ProductVariantPrice
        from django.contrib.contenttypes.models import ContentType
        
        for item in cart.items.all():
            # Проверяем, есть ли у товара внешний источник (вариант)
            if item.product.external_data and 'source_variant_id' in item.product.external_data:
                try:
                    # Определяем тип варианта по типу продукта
                    variant_model = None
                    if item.product.product_type == 'clothing':
                        from apps.catalog.models import ClothingVariant
                        variant_model = ClothingVariant
                    elif item.product.product_type == 'shoes':
                        from apps.catalog.models import ShoeVariant
                        variant_model = ShoeVariant
                    elif item.product.product_type == 'jewelry':
                        from apps.catalog.models import JewelryVariant
                        variant_model = JewelryVariant
                    elif item.product.product_type == 'furniture':
                        from apps.catalog.models import FurnitureVariant
                        variant_model = FurnitureVariant
                    elif item.product.product_type == 'books':
                        from apps.catalog.models import BookVariant
                        variant_model = BookVariant
                    
                    if variant_model:
                        # Получаем вариант
                        variant = variant_model.objects.filter(
                            id=item.product.external_data['source_variant_id']
                        ).first()
                        
                        if variant:
                            # Получаем цену варианта
                            content_type = ContentType.objects.get_for_model(variant)
                            variant_price = ProductVariantPrice.objects.filter(
                                content_type=content_type,
                                object_id=variant.id
                            ).first()
                            
                            if variant_price:
                                # Определяем метод доставки и соответствующую стоимость
                                shipping_method = serializer.validated_data.get('shipping_method', '').lower()
                                if 'air' in shipping_method or 'авиа' in shipping_method:
                                    if variant_price.air_shipping_cost:
                                        shipping += float(variant_price.air_shipping_cost) * item.quantity
                                elif 'sea' in shipping_method or 'мор' in shipping_method:
                                    if variant_price.sea_shipping_cost:
                                        shipping += float(variant_price.sea_shipping_cost) * item.quantity
                                else:
                                    # По умолчанию используем наземную доставку
                                    if variant_price.ground_shipping_cost:
                                        shipping += float(variant_price.ground_shipping_cost) * item.quantity
                except Exception as e:
                    # В случае ошибки продолжаем без учета доставки для этого товара
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error calculating shipping for item {item}: {str(e)}")
        
        discount = 0
        promo_code = None

        # Проверка и применение промокода из корзины или из запроса
        promo_code_value = serializer.validated_data.get('promo_code') or (cart.promo_code.code if cart.promo_code else None)
        if promo_code_value:
            try:
                promo_code = PromoCode.objects.get(code__iexact=promo_code_value)
                # Проверка валидности промокода
                is_valid, error = promo_code.is_valid(user=request.user, cart_total=float(subtotal), cart_currency=cart.currency)
                if is_valid:
                    discount = promo_code.calculate_discount(float(subtotal), currency=cart.currency)
                    # Увеличиваем счетчик использований
                    promo_code.used_count += 1
                    promo_code.save(update_fields=['used_count'])
                else:
                    promo_code = None
            except PromoCode.DoesNotExist:
                pass

        total = subtotal + Decimal(str(shipping)) - Decimal(str(discount))

        # Генерация номера заказа
        number = uuid.uuid4().hex[:12].upper()
        payment_method = (serializer.validated_data.get('payment_method') or '').strip().lower()
        is_crypto = payment_method == 'crypto'

        # Крипто: создаём инвойс ДО заказа, чтобы не терять корзину при ошибке провайдера
        if is_crypto:
            locale = (serializer.validated_data.get("locale") or "").strip() or request.META.get("HTTP_ACCEPT_LANGUAGE", "").split(",")[0].split("-")[0] or "en"
            if locale not in ("ru", "en"):
                locale = "en"
            invoice_data, payment_data = _create_crypto_invoice(number, total, cart.currency, locale=locale)
            if not invoice_data:
                return Response(
                    {"detail": _("Не удалось создать платёжную ссылку. Попробуйте позже или выберите другой способ оплаты.")},
                    status=503,
                )

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
            status=Order.OrderStatus.PENDING_PAYMENT if is_crypto else Order.OrderStatus.NEW,
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

        if is_crypto:
            # Крипто: сохраняем CryptoPayment, позиции заказа без списания остатка
            _save_crypto_payment(order, invoice_data, cart.currency)
            for item in cart.items.select_related('product').all():
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    product_name=item.product.name,
                    chosen_size=item.chosen_size,
                    price=item.price,
                    quantity=item.quantity,
                    total=item.price * item.quantity,
                )
            cart.items.all().delete()
            response_data = OrderSerializer(order).data
            response_data["payment_data"] = payment_data
            return Response(response_data, status=201)
        else:
            # Позиции заказа + атомарное списание остатка
            for item in cart.items.select_related('product').all():
                _decrement_stock_for_cart_item(item.product, item.chosen_size, item.quantity)
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    product_name=item.product.name,
                    chosen_size=item.chosen_size,
                    price=item.price,
                    quantity=item.quantity,
                    total=item.price * item.quantity,
                )
            cart.items.all().delete()
            return Response(OrderSerializer(order).data, status=201)
