"""API views for recommendations (search_by_image, personalized, complete_the_look)."""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny


class RecommendationViewSet(viewsets.ViewSet):
    """API for vector recommendations (search by image, personalized, complete the look)."""
    permission_classes = [AllowAny]

    def _get_engine(self):
        from .services.vector_engine import QdrantRecommendationEngine
        return QdrantRecommendationEngine()

    @action(detail=False, methods=["post"])
    def search_by_image(self, request):
        """POST /api/recommendations/search_by_image/ — visual search by image URL."""
        image_url = request.data.get("image_url")
        if not image_url:
            return Response(
                {"error": "image_url required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        n_results = int(request.data.get("limit", 20))
        try:
            engine = self._get_engine()
            results = engine.find_similar_by_image(
                image_url=image_url,
                n_results=n_results,
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        from apps.catalog.models import Product
        from apps.catalog.serializers import ProductSerializer
        product_ids = [r["product_id"] for r in results]
        products = Product.objects.filter(id__in=product_ids)
        product_map = {p.id: p for p in products}
        enriched = []
        for r in results:
            product = product_map.get(r["product_id"])
            if product:
                enriched.append({
                    "product_id": r["product_id"],
                    "similarity": r["score"],
                    "product": ProductSerializer(
                        product, context={"request": request}
                    ).data,
                })
        return Response({"results": enriched})

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
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        from apps.catalog.models import Product
        from apps.catalog.serializers import ProductSerializer
        product_ids = [r["product_id"] for r in recs]
        products = Product.objects.filter(id__in=product_ids)
        product_map = {p.id: p for p in products}
        results = []
        for r in recs:
            product = product_map.get(r["product_id"])
            if product:
                results.append({
                    "product": ProductSerializer(
                        product, context={"request": request}
                    ).data,
                    "similarity_score": r.get("score"),
                })
        return Response({
            "based_on": "your_history",
            "count": len(results),
            "results": results,
        })

    @action(detail=False, methods=["get"])
    def complete_the_look(self, request):
        """GET /api/recommendations/complete_the_look/?product_id=... — complementary products."""
        product_id = request.query_params.get("product_id")
        if not product_id:
            return Response(
                {"error": "product_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from apps.catalog.models import Product
        from django.shortcuts import get_object_or_404
        product = get_object_or_404(Product, pk=product_id)
        complementary = self._get_complementary_categories(product)
        engine = self._get_engine()
        results = []
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
                    "items": similar[:2],
                })
        return Response({
            "base_product_id": int(product_id),
            "complementary_items": results,
        })

    def _get_trending(self, request):
        """Fallback: recent/trending products."""
        from apps.catalog.models import Product
        from apps.catalog.serializers import ProductSerializer
        trending = (
            Product.objects.filter(is_available=True)
            .order_by("-created_at")[:12]
        )
        return Response({
            "based_on": "trending",
            "results": ProductSerializer(
                trending, many=True, context={"request": request}
            ).data,
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
                cat = Category.objects.filter(slug=comp).first()
                if cat:
                    out.append((cat.id, comp))
        return out[:4] if out else []
