from apps.orders.checkout_contract import (
    checkout_cart_fingerprint,
    order_item_source_snapshot,
)
from apps.orders.views import (
    _checkout_cart_fingerprint,
    _order_item_source_snapshot,
)


def test_legacy_checkout_helpers_are_public_contract_aliases():
    assert _checkout_cart_fingerprint is checkout_cart_fingerprint
    assert _order_item_source_snapshot is order_item_source_snapshot
