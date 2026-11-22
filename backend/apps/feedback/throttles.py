"""Limits for authenticated user-generated content mutations."""

from rest_framework.throttling import UserRateThrottle


class FeedbackCreateBurstThrottle(UserRateThrottle):
    scope = "testimonial_create_burst"
    rate = "2/hour"


class FeedbackCreateSustainedThrottle(UserRateThrottle):
    scope = "testimonial_create_sustained"
    rate = "5/day"


TESTIMONIAL_CREATE_THROTTLES = [
    FeedbackCreateBurstThrottle,
    FeedbackCreateSustainedThrottle,
]


class ProductFeedbackBurstThrottle(UserRateThrottle):
    scope = "product_feedback_burst"
    rate = "10/hour"


class ProductFeedbackSustainedThrottle(UserRateThrottle):
    scope = "product_feedback_sustained"
    rate = "30/day"


# Отзывы и вопросы к товарам: файлы и уведомление администратору появляются
# сразу при отправке, до модерации, поэтому частота ограничена на аккаунт.
PRODUCT_FEEDBACK_WRITE_THROTTLES = [
    ProductFeedbackBurstThrottle,
    ProductFeedbackSustainedThrottle,
]
