"""HTTP response contract for on-demand supplement market checks."""

from rest_framework import status
from rest_framework.response import Response

from .services.market_check_pricing import attach_public_market_price
from .services.supplement_market_check import (
    SupplementMarketCheckError,
    SupplementMarketCheckService,
)


def build_supplement_market_check_response(*, supplement, request):
    """Preserve the public GET/POST market-check response contract."""
    service = SupplementMarketCheckService()

    def serialize(check):
        return attach_public_market_price(
            service.serialize(supplement, check),
            product=supplement,
            request=request,
        )

    if request.method == "GET":
        return Response(serialize(service.latest_for(supplement)))

    try:
        result = service.request_check(supplement)
    except SupplementMarketCheckError as exc:
        payload = serialize(service.latest_for(supplement))
        payload["error"] = {
            "code": exc.code,
            "message": exc.public_message,
        }
        return Response(payload, status=exc.http_status)

    payload = serialize(result.check)
    payload["queued"] = result.queued
    payload["cached"] = result.cached
    payload["stock_discovery_status"] = result.stock_discovery_status
    return Response(
        payload,
        status=(
            status.HTTP_202_ACCEPTED
            if result.queued
            else status.HTTP_200_OK
        ),
    )
