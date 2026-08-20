"""Transport-level protection for public payment callbacks."""

from api.throttles import TrustedProxyIPRateThrottle


class CryptoWebhookBurstThrottle(TrustedProxyIPRateThrottle):
    scope = "crypto_webhook_burst"
    rate = "60/min"


class CryptoWebhookSustainedThrottle(TrustedProxyIPRateThrottle):
    scope = "crypto_webhook_sustained"
    rate = "1000/day"


CRYPTO_WEBHOOK_THROTTLES = [
    CryptoWebhookBurstThrottle,
    CryptoWebhookSustainedThrottle,
]
