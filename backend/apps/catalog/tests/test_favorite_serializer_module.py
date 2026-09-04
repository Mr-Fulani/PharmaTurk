from apps.catalog.favorite_serializers import (
    AddToFavoriteSerializer as ExtractedAddToFavoriteSerializer,
    FavoriteSerializer as ExtractedFavoriteSerializer,
    resolve_product_for_favorites_api as extracted_product_resolver,
)
from apps.catalog.serializers import (
    AddToFavoriteSerializer,
    FavoriteSerializer,
    resolve_product_for_favorites_api,
)


def test_legacy_serializer_imports_reexport_extracted_favorite_contract():
    assert FavoriteSerializer is ExtractedFavoriteSerializer
    assert AddToFavoriteSerializer is ExtractedAddToFavoriteSerializer
    assert resolve_product_for_favorites_api is extracted_product_resolver
