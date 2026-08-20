from apps.orders.throttles import (
    CheckoutBurstThrottle,
    CheckoutSustainedThrottle,
    ReceiptEmailBurstThrottle,
    ReceiptEmailSustainedThrottle,
)


def test_expensive_order_actions_have_explicit_limits():
    assert CheckoutBurstThrottle.rate == "5/min"
    assert CheckoutSustainedThrottle.rate == "30/day"
    assert ReceiptEmailBurstThrottle.rate == "3/hour"
    assert ReceiptEmailSustainedThrottle.rate == "10/day"
