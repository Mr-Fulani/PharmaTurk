"""OpenAPI adapters for project-specific DRF components."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


def canonicalize_compatibility_routes(endpoints):
    """Document only the canonical slash route when both variants exist.

    Several public endpoints intentionally accept both forms for older clients.
    Keeping both in OpenAPI produces duplicate operation IDs and duplicate SDK
    methods even though they represent the same operation.
    """

    canonical_routes = {
        (path.rstrip("/") or "/", method)
        for path, _path_regex, method, _callback in endpoints
        if path != "/" and path.endswith("/")
    }
    return [
        endpoint
        for endpoint in endpoints
        if endpoint[0].endswith("/")
        or (endpoint[0].rstrip("/") or "/", endpoint[2]) not in canonical_routes
    ]


class JWTSafeAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "api.authentication.JWTSafeAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
