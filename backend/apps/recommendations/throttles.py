"""Explicit visual-search limits (independent of global DRF rates)."""
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from api.throttles import TrustedIdentMixin


class VisualSearchAnonThrottle(TrustedIdentMixin, AnonRateThrottle):
    scope = "visual_search_anon"
    rate = "5/min"


class VisualSearchUserThrottle(TrustedIdentMixin, UserRateThrottle):
    scope = "visual_search_user"
    rate = "20/min"


class RecommendationAnonThrottle(TrustedIdentMixin, AnonRateThrottle):
    scope = "recommendation_anon"
    rate = "30/min"


class RecommendationUserThrottle(TrustedIdentMixin, UserRateThrottle):
    scope = "recommendation_user"
    rate = "60/min"
