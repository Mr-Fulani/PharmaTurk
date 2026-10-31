from django.contrib import admin
from django.test import RequestFactory, SimpleTestCase

from apps.catalog.admin import PriceHistoryAdmin, ProductImageAdmin
from apps.catalog.models import PriceHistory, ProductImage
from apps.orders.admin import (
    CartAdmin,
    CartItemAdmin,
    CartItemInline,
    OrderItemAdmin,
    OrderItemInline,
)
from apps.orders.models import Cart, CartItem, Order, OrderItem
from apps.scrapers.admin import ScrapedProductLogAdmin
from apps.scrapers.models import ScrapedProductLog


class OrderItemInlineTests(SimpleTestCase):
    def test_empty_product_widget_renders_without_loading_catalog(self):
        """Пустая строка заказа не должна запрашивать весь каталог товаров."""
        inline = OrderItemInline(Order, admin.site)
        field = inline.formfield_for_foreignkey(
            OrderItem._meta.get_field("product"),
            RequestFactory().get("/admin/orders/order/add/"),
        )

        # SimpleTestCase запрещает запросы к БД при формировании пустого поля.
        html = field.widget.render("product", None)

        self.assertIn("admin-autocomplete", html)
        self.assertIn('data-ajax--url="/admin/autocomplete/"', html)
        self.assertLessEqual(html.count("<option"), 1)


class CartAdminTests(SimpleTestCase):
    def test_cart_product_widgets_render_without_loading_catalog(self):
        """Карточка корзины и позиции не должны строить список из всего каталога."""
        request = RequestFactory().get("/admin/orders/cart/1/change/")
        fields = [
            CartItemInline(Cart, admin.site).formfield_for_foreignkey(
                CartItem._meta.get_field("product"), request
            ),
            CartItemAdmin(CartItem, admin.site).formfield_for_foreignkey(
                CartItem._meta.get_field("product"), request
            ),
            CartAdmin(Cart, admin.site).formfield_for_foreignkey(
                Cart._meta.get_field("user"), request
            ),
            *[
                model_admin(model, admin.site).formfield_for_foreignkey(
                    model._meta.get_field("product"), request
                )
                for model_admin, model in (
                    (OrderItemAdmin, OrderItem),
                    (ProductImageAdmin, ProductImage),
                    (PriceHistoryAdmin, PriceHistory),
                    (ScrapedProductLogAdmin, ScrapedProductLog),
                )
            ],
        ]

        for field in fields:
            # SimpleTestCase запрещает запросы к БД при формировании пустого поля.
            html = field.widget.render("field", None)
            self.assertIn("admin-autocomplete", html)
            self.assertLessEqual(html.count("<option"), 1)
