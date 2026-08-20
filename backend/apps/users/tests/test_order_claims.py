from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.users.order_claims import link_guest_orders_for_verified_user


class GuestOrderClaimTests(SimpleTestCase):
    @patch("apps.orders.models.Order.objects.filter")
    def test_unverified_email_never_claims_orders(self, order_filter):
        user = SimpleNamespace(
            pk=1,
            email="victim@example.com",
            is_verified=False,
        )

        self.assertEqual(link_guest_orders_for_verified_user(user), 0)
        order_filter.assert_not_called()

    @patch("apps.orders.models.Order.objects.filter")
    def test_internal_placeholder_email_never_claims_orders(self, order_filter):
        user = SimpleNamespace(
            pk=1,
            email="tg_123@mudaroba.local",
            is_verified=True,
        )

        self.assertEqual(link_guest_orders_for_verified_user(user), 0)
        order_filter.assert_not_called()

    @patch("apps.orders.models.Order.objects.filter")
    def test_verified_email_claims_only_uncancelled_guest_orders(self, order_filter):
        update = order_filter.return_value.exclude.return_value.update
        update.return_value = 2
        user = SimpleNamespace(
            pk=7,
            email="Buyer@Example.com",
            is_verified=True,
        )

        self.assertEqual(link_guest_orders_for_verified_user(user), 2)
        order_filter.assert_called_once_with(
            user__isnull=True,
            contact_email__iexact="Buyer@Example.com",
        )
        order_filter.return_value.exclude.assert_called_once_with(status="cancelled")
        update.assert_called_once_with(user=user)
