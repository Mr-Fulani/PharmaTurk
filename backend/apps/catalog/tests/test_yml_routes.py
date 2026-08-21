import pytest
from django.urls import resolve


@pytest.mark.parametrize(
    "path",
    (
        "/api/catalog/export/yml",
        "/api/catalog/export/yml/",
        "/api/catalog/export/yml/catalog.xml",
        "/api/catalog/export/yml/catalog.yml",
    ),
)
def test_yml_compatibility_routes_do_not_expose_regex_capture_kwargs(path):
    match = resolve(path)

    assert match.url_name == "export-yml"
    assert match.kwargs == {}
