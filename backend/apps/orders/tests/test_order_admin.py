from django.contrib import admin
from django.test import RequestFactory, SimpleTestCase

from apps.orders.admin import OrderItemInline
from apps.orders.models import Order, OrderItem


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
