"""API views for recommendations (search_by_image, personalized, complete_the_look)."""
import logging

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema

from api.authentication import JWTSafeAuthentication
from apps.catalog.card_payload import compact_card_product_payload
from apps.feedback.review_aggregates import attach_review_aggregates
from .selectors import public_recommendation_products
from .serializers import (
    CompleteTheLookRequestSerializer,
    CompleteTheLookResponseSerializer,
    PersonalizedRecommendationsResponseSerializer,
    RecommendationErrorSerializer,
    VisualSearchRequestSerializer,
    VisualSearchResponseSerializer,
)
from .services.safe_image_fetcher import ImageFetchError, fetch_search_image
from .throttles import (
    RecommendationAnonThrottle,
    RecommendationUserThrottle,
    VisualSearchAnonThrottle,
    VisualSearchUserThrottle,
)


logger = logging.getLogger(__name__)


def _public_card_products(product_ids=None):
    """Canonical public candidates, with legacy variant-shadow rows removed."""
    queryset = public_recommendation_products()
    if product_ids is not None:
        queryset = queryset.filter(id__in=product_ids)
    return (
        queryset.exclude(
            Q(product_type__in=["clothing", "shoes"])
            & (
                Q(external_data__has_key="source_variant_id")
                | Q(external_data__has_key="source_variant_slug")
            )
        )
        .select_related("category", "brand", "price_info")
    )


def _prepare_card_products(queryset):
    """Materialize a small card page and prefetch only its actual domains."""
    products = list(queryset)
    # Runtime import avoids coupling recommendations URL initialization to the
    # catalog view module while keeping one canonical prefetch contract.
    from apps.catalog.views import ProductViewSet

    ProductViewSet._prefetch_card_relations(products)
    return products


class RecommendationViewSet(viewsets.ViewSet):
    """API for vector recommendations (search by image, personalized, complete the look)."""
    permission_classes = [AllowAny]
    throttle_classes = [RecommendationAnonThrottle, RecommendationUserThrottle]

    def _get_engine(self):
        from .services.vector_engine import QdrantRecommendationEngine
        return QdrantRecommendationEngine()

    def get_throttles(self):
        # `search_by_image` also has an explicit no-slash route, so selecting
        # throttles by action protects both router variants.
        if getattr(self, "action", None) == "search_by_image":
            return [VisualSearchAnonThrottle(), VisualSearchUserThrottle()]
        return super().get_throttles()

    @staticmethod
    def _serialize_matches(matches, request):
        """Заменяет устаревающий Qdrant payload актуальной публичной карточкой.

        Цена из векторного индекса нужна для фильтрации/ранжирования, но не должна
        показываться покупателю: она исходная и может не содержать текущую маржу.
        """
        from apps.catalog.serializers import serialize_product_for_card

        ids = [match.get("product_id") for match in matches if match.get("product_id")]
        products = _prepare_card_products(_public_card_products(ids))
        product_map = {product.id: product for product in products}
        result = []
        for match in matches:
            product = product_map.get(match.get("product_id"))
            if product is None:
                continue
            row = dict(match)
            row.pop("payload", None)
            row["product"] = compact_card_product_payload(
                serialize_product_for_card(product, request)
            )
            result.append(row)
        attach_review_aggregates([
            row["product"]
            for row in result
            if isinstance(row.get("product"), dict)
        ])
        return result

    @extend_schema(
        request=VisualSearchRequestSerializer,
        responses={
            200: VisualSearchResponseSerializer,
            400: RecommendationErrorSerializer,
            503: RecommendationErrorSerializer,
        },
    )
    @action(
        detail=False,
        methods=["post"],
        authentication_classes=[JWTSafeAuthentication],
    )
    def search_by_image(self, request):
        """POST /api/recommendations/search_by_image/ — visual search by image URL."""
        if not request.data.get("image_url"):
            return Response(
                {"error": "image_url required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = VisualSearchRequestSerializer(data=request.data)
        if not serializer.is_valid():
            error = "invalid_image_url" if "image_url" in serializer.errors else "invalid_limit"
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        image_url = serializer.validated_data["image_url"]
        n_results = serializer.validated_data["limit"]
        try:
            # Validate and fully decode before loading CLIP or contacting Qdrant.
            image = fetch_search_image(image_url, request=request)
        except ImageFetchError:
            return Response(
                {
                    "error": "invalid_image_url",
                    "message": "Failed to process the image URL. Please ensure it points directly to a valid image file (e.g., .jpg, .png).",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from .services.image_encoder import CLIPEncoder

            image_vector = CLIPEncoder().encode_image(image)
            if image_vector is None:
                raise RuntimeError("image encoder unavailable")
            engine = self._get_engine()
            results = engine.find_similar_by_image_vector(
                image_vector=image_vector,
                n_results=n_results,
            )
        except Exception:
            logger.exception("Visual search backend unavailable")
            return Response(
                {"error": "search_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        from apps.catalog.serializers import serialize_product_for_card
        
        product_ids = [r["product_id"] for r in results]
        products = _prepare_card_products(_public_card_products(product_ids))
        product_map = {p.id: p for p in products}
        enriched = []
        for r in results:
            product = product_map.get(r["product_id"])
            if product:
                enriched.append({
                    "product_id": r["product_id"],
                    "similarity": r["score"],
                    "product": compact_card_product_payload(
                        serialize_product_for_card(product, request)
                    ),
                })
        attach_review_aggregates([
            row["product"]
            for row in enriched
            if isinstance(row.get("product"), dict)
        ])
        return Response({"results": enriched})

    @extend_schema(
        request=None,
        responses={200: PersonalizedRecommendationsResponseSerializer},
    )
    @action(detail=False, methods=["get"])
    def personalized(self, request):
        """GET /api/recommendations/personalized/ — personalized or trending."""
        if not request.user.is_authenticated:
            return self._get_trending(request)
        from .models import UserEmbedding
        user_emb, _ = UserEmbedding.objects.get_or_create(
            user=request.user,
            defaults={"preference_vector": None},
        )
        if user_emb.preference_vector is None:
            return self._get_trending(request)
        viewed = getattr(request, "_viewed_product_ids", []) or []
        try:
            engine = self._get_engine()
            recs = engine.get_personalized_recommendations(
                user_vector=user_emb.preference_vector,
                viewed_products=viewed,
                n_results=20,
                diversity_factor=0.4,
            )
        except Exception:
            logger.exception("Personalized recommendations unavailable")
            return self._get_trending(request)
        from apps.catalog.serializers import serialize_product_for_card
        
        product_ids = [r["product_id"] for r in recs]
        products = _prepare_card_products(_public_card_products(product_ids))
        product_map = {p.id: p for p in products}
        results = []
        for r in recs:
            product = product_map.get(r["product_id"])
            if product:
                results.append({
                    "product": compact_card_product_payload(
                        serialize_product_for_card(product, request)
                    ),
                    "similarity_score": r.get("score"),
                })
        attach_review_aggregates([
            row["product"]
            for row in results
            if isinstance(row.get("product"), dict)
        ])
        return Response({
            "based_on": "your_history",
            "count": len(results),
            "results": results,
        })

    @extend_schema(
        request=None,
        parameters=[CompleteTheLookRequestSerializer],
        responses={
            200: CompleteTheLookResponseSerializer,
            400: RecommendationErrorSerializer,
            404: RecommendationErrorSerializer,
            503: RecommendationErrorSerializer,
        },
    )
    @action(detail=False, methods=["get"])
    def complete_the_look(self, request):
        """GET /api/recommendations/complete_the_look/?product_id=... — complementary products."""
        serializer = CompleteTheLookRequestSerializer(data=request.query_params)
        if not serializer.is_valid():
            error = (
                "product_id required"
                if "product_id" not in request.query_params
                else "invalid_product_id"
            )
            return Response(
                {"error": error},
                status=status.HTTP_400_BAD_REQUEST,
            )
        product_id = serializer.validated_data["product_id"]
        product = get_object_or_404(
            public_recommendation_products().select_related("category"),
            pk=product_id,
        )
        complementary = self._get_complementary_categories(product)
        if not complementary:
            return Response({
                "base_product_id": product.id,
                "complementary_items": [],
            })

        results = []
        try:
            engine = self._get_engine()
            for cat_id, relation_type in complementary:
                if cat_id is None:
                    continue
                similar = engine.find_similar(
                    product_id=product.id,
                    vector_type="combined",
                    n_results=3,
                    filters={"category_id": cat_id},
                )
                if similar:
                    results.append({
                        "relation_type": relation_type,
                        "category_id": cat_id,
                        "items": self._serialize_matches(similar[:2], request),
                    })
        except Exception:
            logger.exception("Complete-the-look recommendations unavailable")
            return Response(
                {"error": "recommendations_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({
            "base_product_id": product.id,
            "complementary_items": results,
        })

    def _get_trending(self, request):
        """Fallback: recent/trending products."""
        from apps.catalog.serializers import serialize_product_for_card
        
        trending = _prepare_card_products(
            _public_card_products()
            .exclude(product_type="jewelry")
            .order_by("-created_at")[:12]
        )
        results = [
            compact_card_product_payload(serialize_product_for_card(p, request))
            for p in trending
        ]
        attach_review_aggregates(results)
        return Response({
            "based_on": "trending",
            "results": results,
        })

    def _get_complementary_categories(self, product):
        """Map product category to complementary category ids."""
        if not product.category:
            return []
        from apps.catalog.models import Category
        mapping = {
            "medicines": ["supplements", "medical_equipment"],
            "supplements": ["medicines"],
            "medical_equipment": ["medicines", "accessories"],
            "clothing": ["shoes", "accessories", "jewelry"],
            "shoes": ["clothing", "accessories"],
            "accessories": ["clothing", "jewelry"],
        }
        slug = getattr(product.category, "slug", None) or ""
        product_type = getattr(product, "product_type", "") or ""
        keys = [slug, product_type]
        out = []
        for key in keys:
            if not key:
                continue
            comps = mapping.get(key, [])
            for comp in comps:
                cat = Category.objects.filter(slug=comp, is_active=True).first()
                if cat:
                    out.append((cat.id, comp))
        return out[:4] if out else []
