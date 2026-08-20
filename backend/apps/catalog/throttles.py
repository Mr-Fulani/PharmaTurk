"""Explicit rates for expensive public catalog exports."""

from api.throttles import TrustedProxyIPRateThrottle


class YMLExportThrottle(TrustedProxyIPRateThrottle):
    scope = "catalog_yml_export"
    rate = "2/min"
