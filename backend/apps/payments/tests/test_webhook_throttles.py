from apps.payments.throttles import (
    CryptoWebhookBurstThrottle,
    CryptoWebhookSustainedThrottle,
)


def test_crypto_webhook_has_transport_limits():
    assert CryptoWebhookBurstThrottle.rate == "60/min"
    assert CryptoWebhookSustainedThrottle.rate == "1000/day"
