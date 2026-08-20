import importlib
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.test import override_settings
from rest_framework.test import APIRequestFactory

from apps.catalog.models import Product
from apps.recommendations.selectors import (
    is_public_recommendation_product,
    public_recommendation_products,
)
from apps.recommendations.serializers import CompleteTheLookRequestSerializer
from apps.recommendations.services.vector_engine import QdrantRecommendationEngine
from apps.recommendations.tasks import index_product_vectors, remove_product_vectors
from apps.recommendations.views import RecommendationViewSet


@pytest.mark.parametrize("product_id", [None, "", "not-a-number", 0, -1])
def test_complete_the_look_serializer_rejects_invalid_product_ids(product_id):
    data = {} if product_id is None else {"product_id": product_id}
    serializer = CompleteTheLookRequestSerializer(data=data)

    assert not serializer.is_valid()
    assert "product_id" in serializer.errors


def test_public_selector_requires_published_and_available_product():
    sentinel = object()
    with patch.object(Product.objects, "filter", return_value=sentinel) as product_filter:
        assert public_recommendation_products() is sentinel

    product_filter.assert_called_once_with(is_active=True, is_available=True)
    assert is_public_recommendation_product(
        SimpleNamespace(is_active=True, is_available=True)
    )
    assert not is_public_recommendation_product(
        SimpleNamespace(is_active=False, is_available=True)
    )
    assert not is_public_recommendation_product(
        SimpleNamespace(is_active=True, is_available=False)
    )


def _get_complete_the_look(params):
    request = APIRequestFactory().get(
        "/api/recommendations/complete_the_look/",
        params,
    )
    view = RecommendationViewSet.as_view({"get": "complete_the_look"})
    with patch.object(RecommendationViewSet, "get_throttles", return_value=[]):
        return view(request)


@pytest.mark.parametrize(
    ("params", "error"),
    [
        ({}, "product_id required"),
        ({"product_id": "oops"}, "invalid_product_id"),
        ({"product_id": "0"}, "invalid_product_id"),
    ],
)
def test_complete_the_look_rejects_bad_id_before_database_or_qdrant(params, error):
    with patch(
        "apps.recommendations.views.public_recommendation_products"
    ) as public_products, patch.object(
        RecommendationViewSet,
        "_get_engine",
    ) as get_engine:
        response = _get_complete_the_look(params)

    assert response.status_code == 400
    assert response.data == {"error": error}
    public_products.assert_not_called()
    get_engine.assert_not_called()


def test_complete_the_look_returns_generic_503_when_qdrant_is_down():
    product = SimpleNamespace(id=17, category=SimpleNamespace(slug="clothing"))
    public_queryset = MagicMock()
    public_queryset.select_related.return_value = public_queryset

    with patch(
        "apps.recommendations.views.public_recommendation_products",
        return_value=public_queryset,
    ), patch(
        "apps.recommendations.views.get_object_or_404",
        return_value=product,
    ), patch.object(
        RecommendationViewSet,
        "_get_complementary_categories",
        return_value=[(5, "shoes")],
    ), patch.object(
        RecommendationViewSet,
        "_get_engine",
        side_effect=RuntimeError("secret backend detail"),
    ):
        response = _get_complete_the_look({"product_id": "17"})

    assert response.status_code == 503
    assert response.data == {"error": "recommendations_unavailable"}
    assert "secret backend detail" not in str(response.data)


def test_vector_upsert_deindexes_inactive_product_without_writing():
    engine = object.__new__(QdrantRecommendationEngine)
    engine.delete_product = Mock(return_value=True)
    product = SimpleNamespace(id=91, is_active=False, is_available=True)

    result = engine.upsert_product(product=product, text_vector=[0.0])

    assert result is False
    engine.delete_product.assert_called_once_with(91)


def test_failed_qdrant_delete_keeps_local_marker_for_nightly_retry():
    engine = object.__new__(QdrantRecommendationEngine)
    engine.client = Mock()
    engine.client.delete.side_effect = RuntimeError("qdrant down")
    engine._invalidate_similar_cache = Mock()

    with patch(
        "apps.recommendations.services.vector_engine.ProductVector.objects.filter"
    ) as local_filter:
        assert engine.delete_product(44) is False

    local_filter.assert_not_called()
    engine._invalidate_similar_cache.assert_not_called()


@override_settings(
    REDIS_URL="redis://broker.example/0",
    REDIS_CACHE_URL="redis://cache.example/1",
)
def test_vector_cache_invalidation_uses_cache_redis_not_celery_broker():
    engine = object.__new__(QdrantRecommendationEngine)
    redis_client = Mock()
    redis_client.scan_iter.return_value = []

    with patch("redis.from_url", return_value=redis_client) as from_url:
        engine._invalidate_similar_cache(12)

    from_url.assert_called_once_with("redis://cache.example/1")


def test_remove_task_rechecks_publication_before_deleting():
    public_queryset = MagicMock()
    public_queryset.filter.return_value.values_list.return_value = [2]
    engine = Mock()
    engine.delete_product.return_value = True

    with patch(
        "apps.recommendations.tasks.public_recommendation_products",
        return_value=public_queryset,
    ):
        # Patch the lazy import at its source; the task imports it on invocation.
        with patch(
            "apps.recommendations.services.vector_engine.QdrantRecommendationEngine",
            return_value=engine,
        ):
            result = remove_product_vectors([1, 2])

    assert result == {"removed": 1, "skipped_public": 1, "errors": []}
    engine.delete_product.assert_called_once_with(1)


def test_explicit_index_task_deindexes_ids_excluded_by_public_policy():
    product = SimpleNamespace(
        id=1,
        name="Public product",
        description="",
        category=None,
    )
    public_queryset = MagicMock()
    filtered_queryset = MagicMock()
    indexable_queryset = MagicMock()
    prepared_queryset = [product]
    public_queryset.filter.return_value = filtered_queryset
    indexable_queryset.values_list.return_value = [1]
    indexable_queryset.select_related.return_value.prefetch_related.return_value = (
        prepared_queryset
    )

    engine = Mock()
    engine.delete_product.return_value = True
    encoder = Mock()
    encoder.encode.return_value.tolist.return_value = [0.0]
    vector_engine_module = importlib.import_module(
        "apps.recommendations.services.vector_engine"
    )
    text_encoder_module = ModuleType("apps.recommendations.services.text_encoder")
    text_encoder_module.TextEncoder = Mock(return_value=encoder)
    image_encoder_module = ModuleType("apps.recommendations.services.image_encoder")
    image_encoder_module.CLIPEncoder = Mock()

    with patch(
        "apps.recommendations.tasks.public_recommendation_products",
        return_value=public_queryset,
    ), patch(
        "apps.recommendations.tasks._exclude_variant_shadows",
        return_value=indexable_queryset,
    ), patch.object(
        vector_engine_module,
        "QdrantRecommendationEngine",
        return_value=engine,
    ), patch.dict(
        sys.modules,
        {
            text_encoder_module.__name__: text_encoder_module,
            image_encoder_module.__name__: image_encoder_module,
        },
    ), patch(
        "apps.recommendations.tasks._working_product_image_url",
        return_value="",
    ):
        result = index_product_vectors(product_ids=[1, 2])

    assert result == {"indexed": 1, "removed": 1, "errors": [], "remaining": 0}
    engine.delete_product.assert_called_once_with(2)
    engine.upsert_product.assert_called_once()
