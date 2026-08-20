from apps.catalog.throttles import YMLExportThrottle
from apps.recommendations.throttles import (
    RecommendationAnonThrottle,
    RecommendationUserThrottle,
)


def test_expensive_public_endpoints_have_explicit_limits():
    assert YMLExportThrottle.rate == "2/min"
    assert RecommendationAnonThrottle.rate == "30/min"
    assert RecommendationUserThrottle.rate == "60/min"
