"""Explicit limits for cart writes and expensive order actions."""

from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle

from api.throttles import get_trusted_client_ip


class TrustedUserOrProxyIPRateThrottle(SimpleRateThrottle):
    """Key authenticated requests by user and anonymous requests by trusted IP."""

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            ident = f"user:{user.pk}"
        else:
            # REMOTE_ADDR is present on real WSGI requests. Sharing one bounded
            # fallback bucket is safer than disabling throttling on malformed
            # synthetic/proxy requests.
            ident = f"ip:{get_trusted_client_ip(request) or 'unknown'}"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class CartMutationBurstThrottle(TrustedUserOrProxyIPRateThrottle):
    scope = "cart_mutation_burst"
    rate = "60/min"


class CartMutationSustainedThrottle(TrustedUserOrProxyIPRateThrottle):
    scope = "cart_mutation_sustained"
    rate = "1000/day"


class CheckoutBurstThrottle(UserRateThrottle):
    rate = "5/min"


class CheckoutSustainedThrottle(UserRateThrottle):
    rate = "30/day"


class ReceiptEmailBurstThrottle(UserRateThrottle):
    rate = "3/hour"


class ReceiptEmailSustainedThrottle(UserRateThrottle):
    rate = "10/day"


CART_MUTATION_THROTTLES = [
    CartMutationBurstThrottle,
    CartMutationSustainedThrottle,
]
CHECKOUT_THROTTLES = [CheckoutBurstThrottle, CheckoutSustainedThrottle]
RECEIPT_EMAIL_THROTTLES = [ReceiptEmailBurstThrottle, ReceiptEmailSustainedThrottle]
