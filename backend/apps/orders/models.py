from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.utils import timezone

from apps.users.models import User, UserAddress
from apps.catalog.models import Product
from apps.catalog.utils.currency_converter import currency_converter


class PromoCode(models.Model):
    """Промокод для скидок."""
    class DiscountType(models.TextChoices):
        PERCENT = "percent", _("Процент")
        FIXED = "fixed", _("Фиксированная сумма")

    code = models.CharField(_("Код"), max_length=50, unique=True, db_index=True)
    description = models.TextField(_("Описание"), blank=True)
    discount_type = models.CharField(_("Тип скидки"), max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENT)
    discount_value = models.DecimalField(_("Значение скидки"), max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    min_amount = models.DecimalField(_("Минимальная сумма заказа (RUB)"), max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    max_discount = models.DecimalField(_("Максимальная скидка (RUB)"), max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    max_uses = models.PositiveIntegerField(_("Максимальное количество использований"), null=True, blank=True)
    used_count = models.PositiveIntegerField(_("Количество использований"), default=0)
    valid_from = models.DateTimeField(_("Действителен с"), default=timezone.now)
    valid_to = models.DateTimeField(_("Действителен до"), null=True, blank=True)
    is_active = models.BooleanField(_("Активен"), default=True)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("🛒 Промокод")
        verbose_name_plural = _("🛒 Заказы — Промокоды")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.code} ({self.discount_value}{'%' if self.discount_type == 'percent' else ''})"

    @property
    def base_currency(self) -> str:
        return 'RUB'

    def _convert_money(self, amount, to_currency: str):
        to_currency = (to_currency or self.base_currency).upper()
        if to_currency == self.base_currency:
            return amount
        _orig, converted, _with_margin = currency_converter.convert_price(
            amount=amount,
            from_currency=self.base_currency,
            to_currency=to_currency,
            apply_margin=False,
        )
        return converted

    def get_min_amount(self, currency: str = None):
        return self._convert_money(self.min_amount, currency or self.base_currency)

    def get_max_discount(self, currency: str = None):
        if self.max_discount is None:
            return None
        return self._convert_money(self.max_discount, currency or self.base_currency)

    def get_fixed_discount_value(self, currency: str = None):
        if self.discount_type != self.DiscountType.FIXED:
            return None
        return self._convert_money(self.discount_value, currency or self.base_currency)

    def is_valid(self, user=None, cart_total=0, cart_currency: str = None):
        """Проверка валидности промокода."""
        if not self.is_active:
            return False, _("Промокод неактивен")
        
        if self.valid_to and timezone.now() > self.valid_to:
            return False, _("Промокод истёк")
        
        if timezone.now() < self.valid_from:
            return False, _("Промокод ещё не действителен")
        
        if self.max_uses and self.used_count >= self.max_uses:
            return False, _("Промокод исчерпан")
        
        cart_currency = (cart_currency or self.base_currency).upper()
        min_amount_in_cart_currency = self.get_min_amount(cart_currency)
        if cart_total < float(min_amount_in_cart_currency):
            return False, _("Минимальная сумма заказа не достигнута")
        
        return True, None

    def calculate_discount(self, amount, currency: str = None):
        """Рассчитать размер скидки для указанной суммы."""
        currency = (currency or self.base_currency).upper()

        try:
            amount_dec = Decimal(str(amount))
        except Exception:
            amount_dec = Decimal('0')

        if self.discount_type == self.DiscountType.PERCENT:
            percent = (self.discount_value or Decimal('0')) / Decimal('100')
            discount = amount_dec * percent
            max_discount = self.get_max_discount(currency)
            if max_discount is not None:
                discount = min(discount, Decimal(str(max_discount)))
            return float(discount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

        fixed_value = self.get_fixed_discount_value(currency)
        if fixed_value is None:
            fixed_value = self.discount_value
        try:
            fixed_dec = Decimal(str(fixed_value))
        except Exception:
            fixed_dec = Decimal('0')

        discount = min(fixed_dec, amount_dec)
        max_discount = self.get_max_discount(currency)
        if max_discount is not None:
            discount = min(discount, Decimal(str(max_discount)))
        return float(discount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class Cart(models.Model):
    """Корзина товаров пользователя или гостя."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="carts", verbose_name=_("Пользователь"))
    session_key = models.CharField(_("Ключ сессии"), max_length=64, blank=True, db_index=True)
    currency = models.CharField(_("Валюта"), max_length=3, default="USD")
    promo_code = models.ForeignKey(PromoCode, on_delete=models.SET_NULL, null=True, blank=True, related_name="carts", verbose_name=_("Промокод"))
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("🛒 Корзина")
        verbose_name_plural = _("🛒 Заказы — Корзины")
        indexes = [
            models.Index(fields=["user", "session_key"]),
        ]
        constraints = [
            models.CheckConstraint(check=~(models.Q(user__isnull=True) & models.Q(session_key="")), name="cart_user_or_session"),
        ]

    def __str__(self) -> str:
        return f"Корзина {self.user_id or self.session_key}"

    @property
    def items_count(self) -> int:
        return sum(item.quantity for item in self.items.all())

    @property
    def total_amount(self):
        """Рассчитать общую сумму корзины в предпочитаемой валюте."""
        # Получаем предпочитаемую валюту (по умолчанию RUB)
        preferred_currency = 'RUB'
        
        # Суммируем цены в предпочитаемой валюте
        total = 0
        for item in self.items.all():
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
        
        return round(total, 2)
    
    @property
    def discount_amount(self):
        """Рассчитать скидку по промокоду."""
        if not self.promo_code:
            return 0
        is_valid, error = self.promo_code.is_valid(cart_total=self.total_amount)
        if not is_valid:
            return 0
        return self.promo_code.calculate_discount(self.total_amount)
    
    @property
    def final_amount(self):
        """Итоговая сумма с учётом скидки."""
        return round(self.total_amount - self.discount_amount, 2)


class CartItem(models.Model):
    """Позиция в корзине."""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items", verbose_name=_("Корзина"))
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items", verbose_name=_("Товар"))
    quantity = models.PositiveIntegerField(_("Количество"), default=1, validators=[MinValueValidator(1)])
    price = models.DecimalField(_("Цена на момент добавления"), max_digits=10, decimal_places=2)
    currency = models.CharField(_("Валюта"), max_length=3, default="USD")
    chosen_size = models.CharField(_("Выбранный размер"), max_length=50, blank=True, default="")
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("🛒 Позиция корзины")
        verbose_name_plural = _("🛒 Заказы — Позиции корзины")
        unique_together = ("cart", "product", "chosen_size")

    def __str__(self) -> str:
        return f"{self.product.name} x{self.quantity}"

    @property
    def total(self):
        """Рассчитать сумму позиции в предпочитаемой валюте."""
        # Получаем предпочитаемую валюту (по умолчанию RUB)
        preferred_currency = 'RUB'
        
        try:
            prices = self.product.get_all_prices()
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
                price = self.price
            
            return round(price * self.quantity, 2)
        except Exception:
            # Fallback к старому полю
            return round(self.price * self.quantity, 2)


class Order(models.Model):
    """Заказ пользователя."""
    class OrderStatus(models.TextChoices):
        NEW = "new", _("Новый")
        PENDING_PAYMENT = "pending_payment", _("Ожидает оплаты")
        PAID = "paid", _("Оплачен")
        PROCESSING = "processing", _("В обработке")
        SHIPPED = "shipped", _("Отправлен")
        DELIVERED = "delivered", _("Доставлен")
        CANCELLED = "cancelled", _("Отменен")

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders", verbose_name=_("Пользователь"))
    number = models.CharField(_("Номер заказа"), max_length=32, unique=True)
    status = models.CharField(_("Статус"), max_length=32, choices=OrderStatus.choices, default=OrderStatus.NEW)

    # Суммы
    subtotal_amount = models.DecimalField(_("Сумма товаров"), max_digits=12, decimal_places=2, default=0)
    shipping_amount = models.DecimalField(_("Доставка"), max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(_("Скидка"), max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(_("Итого"), max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(_("Валюта"), max_length=3, default="USD")

    # Контакты/доставка
    contact_name = models.CharField(_("Имя получателя"), max_length=150)
    contact_phone = models.CharField(_("Телефон"), max_length=32)
    contact_email = models.EmailField(_("Email"), blank=True)

    shipping_address = models.ForeignKey(UserAddress, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders", verbose_name=_("Адрес доставки"))
    shipping_address_text = models.TextField(_("Адрес доставки (текст)"), blank=True)
    shipping_method = models.CharField(_("Способ доставки"), max_length=50, blank=True)

    payment_method = models.CharField(_("Способ оплаты"), max_length=50, blank=True)
    payment_status = models.CharField(_("Статус оплаты"), max_length=32, default="unpaid")
    
    promo_code = models.ForeignKey(PromoCode, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders", verbose_name=_("Промокод"))

    comment = models.TextField(_("Комментарий"), blank=True)

    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("🛒 Заказ")
        verbose_name_plural = _("🛒 Заказы — Заказы")
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.status == self.OrderStatus.PAID and self.payment_status != "paid":
            self.payment_status = "paid"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Заказ #{self.number}"


class OrderItem(models.Model):
    """Позиция заказа."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items", verbose_name=_("Заказ"))
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items", verbose_name=_("Товар"))
    product_name = models.CharField(_("Название товара"), max_length=500)
    chosen_size = models.CharField(_("Выбранный размер"), max_length=50, blank=True, default="")
    price = models.DecimalField(_("Цена"), max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(_("Количество"), default=1)
    total = models.DecimalField(_("Сумма"), max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = _("🛒 Позиция заказа")
        verbose_name_plural = _("🛒 Заказы — Позиции заказа")

    def __str__(self) -> str:
        return f"{self.product_name} x{self.quantity}"
