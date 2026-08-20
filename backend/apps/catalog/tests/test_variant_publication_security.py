from unittest.mock import MagicMock, patch


def _helper():
    with patch(
        "apps.catalog.models.service_portfolio_translation_fields_ready",
        return_value=False,
    ):
        from apps.catalog.views import _get_public_variant

    return _get_public_variant


def test_public_variant_resolver_requires_published_parent_product():
    helper = _helper()
    variant_model = MagicMock()
    queryset = variant_model.objects.filter.return_value
    queryset.select_related.return_value.first.return_value = object()

    helper(variant_model, "hidden-parent-variant")

    variant_model.objects.filter.assert_called_once_with(
        slug="hidden-parent-variant",
        is_active=True,
        product__is_active=True,
    )
    queryset.select_related.assert_called_once_with("product")
