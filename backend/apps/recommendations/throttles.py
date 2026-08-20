"""Explicit visual-search limits (independent of global DRF rates)."""
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class VisualSearchAnonThrottle(AnonRateThrottle):
    rate = "5/min"


class VisualSearchUserThrottle(UserRateThrottle):
    rate = "20/min"


class RecommendationAnonThrottle(AnonRateThrottle):
    rate = "30/min"


class RecommendationUserThrottle(UserRateThrottle):
    rate = "60/min"
