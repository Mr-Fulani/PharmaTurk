"""Explicit rates for expensive public catalog exports."""

from api.throttles import TrustedProxyIPRateThrottle


class YMLExportThrottle(TrustedProxyIPRateThrottle):
    scope = "catalog_yml_export"
    rate = "2/min"


class _MarketCheckPostThrottle(TrustedProxyIPRateThrottle):
    """Throttle only the mutating intent request; bounded polling stays readable."""

    def allow_request(self, request, view):
        if request.method != "POST":
            return True
        return super().allow_request(request, view)


class MedicineMarketCheckBurstThrottle(_MarketCheckPostThrottle):
    scope = "medicine_market_check_burst"
    rate = "3/min"


class MedicineMarketCheckSustainedThrottle(_MarketCheckPostThrottle):
    scope = "medicine_market_check_sustained"
    rate = "30/day"


MEDICINE_MARKET_CHECK_THROTTLES = [
    MedicineMarketCheckBurstThrottle,
    MedicineMarketCheckSustainedThrottle,
]


class SupplementMarketCheckBurstThrottle(_MarketCheckPostThrottle):
    scope = "supplement_market_check_burst"
    rate = "3/min"


class SupplementMarketCheckSustainedThrottle(_MarketCheckPostThrottle):
    scope = "supplement_market_check_sustained"
    rate = "30/day"


SUPPLEMENT_MARKET_CHECK_THROTTLES = [
    SupplementMarketCheckBurstThrottle,
    SupplementMarketCheckSustainedThrottle,
]
