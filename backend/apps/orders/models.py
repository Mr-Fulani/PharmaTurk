from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator

from apps.users.models import User, UserAddress
from apps.catalog.models import Product


class Cart(models.Model):
    """Корзина товаров пользователя или гостя."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="carts", verbose_name=_("Пользователь"))
    session_key = models.CharField(_("Ключ сессии"), max_length=64, blank=True, db_index=True)
    currency = models.CharField(_("Валюта"), max_length=3, default="USD")
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Корзина")
        verbose_name_plural = _("Корзины")
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
        total = sum((item.price * item.quantity for item in self.items.all()))
        return round(total, 2)


class CartItem(models.Model):
    """Позиция в корзине."""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items", verbose_name=_("Корзина"))
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items", verbose_name=_("Товар"))
    quantity = models.PositiveIntegerField(_("Количество"), default=1, validators=[MinValueValidator(1)])
    price = models.DecimalField(_("Цена на момент добавления"), max_digits=10, decimal_places=2)
    currency = models.CharField(_("Валюта"), max_length=3, default="USD")
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Позиция корзины")
        verbose_name_plural = _("Позиции корзины")
        unique_together = ("cart", "product")

    def __str__(self) -> str:
        return f"{self.product.name} x{self.quantity}"


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

    comment = models.TextField(_("Комментарий"), blank=True)

    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Заказ")
        verbose_name_plural = _("Заказы")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Заказ #{self.number}"


class OrderItem(models.Model):
    """Позиция заказа."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items", verbose_name=_("Заказ"))
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items", verbose_name=_("Товар"))
    product_name = models.CharField(_("Название товара"), max_length=500)
    price = models.DecimalField(_("Цена"), max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(_("Количество"), default=1)
    total = models.DecimalField(_("Сумма"), max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = _("Позиция заказа")
        verbose_name_plural = _("Позиции заказа")

    def __str__(self) -> str:
        return f"{self.product_name} x{self.quantity}"
