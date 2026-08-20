"""Security-sensitive, IP-based throttles for authentication endpoints."""
from __future__ import annotations

import ipaddress

from rest_framework.throttling import SimpleRateThrottle


def get_trusted_client_ip(request) -> str | None:
    """Read Nginx's trusted effective IP, never a raw forwarding chain.

    Without upstream real-IP normalization this is deliberately the immediate
    peer (for example a Cloudflare edge), trading bucket precision for spoofing
    resistance.
    """
    for raw_ident in (
        request.META.get("HTTP_X_REAL_IP"),
        request.META.get("REMOTE_ADDR"),
    ):
        try:
            return str(ipaddress.ip_address(str(raw_ident).strip()))
        except ValueError:
            continue
    return None


class TrustedProxyIPRateThrottle(SimpleRateThrottle):
    """Use nginx's overwritten X-Real-IP, falling back to REMOTE_ADDR.

    Production compose does not expose Django directly. The project nginx
    replaces X-Real-IP, so a client-supplied X-Forwarded-For value cannot mint
    arbitrary throttle identities here. Deployments behind an edge proxy must
    normalize the real IP at a source-restricted ingress or rate-limit there.
    """

    def get_cache_key(self, request, view):
        ident = get_trusted_client_ip(request)
        if ident is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LoginBurstThrottle(TrustedProxyIPRateThrottle):
    scope = "auth_login_burst"
    rate = "5/min"


class LoginSustainedThrottle(TrustedProxyIPRateThrottle):
    scope = "auth_login_sustained"
    rate = "50/day"


class TokenBurstThrottle(TrustedProxyIPRateThrottle):
    scope = "auth_token_burst"
    rate = "30/min"


class TokenSustainedThrottle(TrustedProxyIPRateThrottle):
    scope = "auth_token_sustained"
    rate = "500/day"


class RegistrationBurstThrottle(TrustedProxyIPRateThrottle):
    scope = "auth_registration_burst"
    rate = "3/hour"


class RegistrationSustainedThrottle(TrustedProxyIPRateThrottle):
    scope = "auth_registration_sustained"
    rate = "10/day"


class VerificationBurstThrottle(TrustedProxyIPRateThrottle):
    scope = "auth_verification_burst"
    rate = "5/min"


class VerificationSustainedThrottle(TrustedProxyIPRateThrottle):
    scope = "auth_verification_sustained"
    rate = "30/day"


class CookieConsentBurstThrottle(TrustedProxyIPRateThrottle):
    """Prevent a public client from flooding the consent audit table."""

    scope = "cookie_consent_burst"
    rate = "10/min"


class CookieConsentSustainedThrottle(TrustedProxyIPRateThrottle):
    """Bound long-running cookie-consent write amplification per client IP."""

    scope = "cookie_consent_sustained"
    rate = "100/day"


LOGIN_THROTTLES = [LoginBurstThrottle, LoginSustainedThrottle]
TOKEN_THROTTLES = [TokenBurstThrottle, TokenSustainedThrottle]
REGISTRATION_THROTTLES = [RegistrationBurstThrottle, RegistrationSustainedThrottle]
VERIFICATION_THROTTLES = [VerificationBurstThrottle, VerificationSustainedThrottle]
COOKIE_CONSENT_THROTTLES = [
    CookieConsentBurstThrottle,
    CookieConsentSustainedThrottle,
]
