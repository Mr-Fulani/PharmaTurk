from apps.feedback.throttles import (
    FeedbackCreateBurstThrottle,
    FeedbackCreateSustainedThrottle,
)


def test_testimonial_creation_has_explicit_user_limits():
    assert FeedbackCreateBurstThrottle.rate == "2/hour"
    assert FeedbackCreateSustainedThrottle.rate == "5/day"
