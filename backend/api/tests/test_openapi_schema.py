from django.core.management import call_command
from drf_spectacular.drainage import GENERATOR_STATS

from api.schema import canonicalize_compatibility_routes


# Existing serializers predate the OpenAPI contract and still produce many
# type-inference warnings. Keep the debt explicit and prevent it from growing;
# every warning removed can lower this number in the same change.
OPENAPI_UNIQUE_WARNING_BASELINE = 570


def test_openapi_keeps_only_canonical_route_from_compatibility_pair():
    callback = object()
    endpoints = [
        ("/api/example", "api/example", "GET", callback),
        ("/api/example/", "api/example/", "GET", callback),
        ("/api/no-pair", "api/no-pair", "POST", callback),
    ]

    assert canonicalize_compatibility_routes(endpoints) == [
        ("/api/example/", "api/example/", "GET", callback),
        ("/api/no-pair", "api/no-pair", "POST", callback),
    ]


def test_openapi_schema_has_no_generator_errors(tmp_path):
    """Every routed API view must expose enough metadata for OpenAPI generation."""

    schema_path = tmp_path / "schema.yml"
    GENERATOR_STATS.reset()
    try:
        with GENERATOR_STATS.silence():
            call_command(
                "spectacular",
                validate=True,
                file=str(schema_path),
                color=False,
            )

        errors = list(GENERATOR_STATS._error_cache)  # noqa: SLF001
        warnings = list(GENERATOR_STATS._warn_cache)  # noqa: SLF001
        assert errors == []
        assert len(warnings) <= OPENAPI_UNIQUE_WARNING_BASELINE
        assert all("unable to resolve type hint" in warning for warning in warnings)
        assert schema_path.read_text(encoding="utf-8").startswith("openapi: 3.0.3")
    finally:
        GENERATOR_STATS.reset()
