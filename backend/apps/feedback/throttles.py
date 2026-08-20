"""Limits for authenticated user-generated content mutations."""

from rest_framework.throttling import UserRateThrottle


class FeedbackCreateBurstThrottle(UserRateThrottle):
    rate = "2/hour"


class FeedbackCreateSustainedThrottle(UserRateThrottle):
    rate = "5/day"


TESTIMONIAL_CREATE_THROTTLES = [
    FeedbackCreateBurstThrottle,
    FeedbackCreateSustainedThrottle,
]
