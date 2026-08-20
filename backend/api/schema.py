"""OpenAPI adapters for project-specific DRF components."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class JWTSafeAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "api.authentication.JWTSafeAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
