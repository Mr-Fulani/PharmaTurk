"""Business reranker for recommendation results."""
from typing import Dict, List, Any
from django.utils import timezone
from datetime import timedelta

from apps.catalog.models import Product
from apps.catalog.serializers import ProductSerializer


class BusinessReranker:
    """Rerank candidates by business rules (price proximity, availability, freshness)."""

    def rerank(
        self,
        candidates: List[Dict],
        target_product: Product,
        strategy: str = "balanced",
        request=None,
    ) -> List[Dict]:
        if not candidates:
            return []
        product_ids = [c["product_id"] for c in candidates]
        products = Product.objects.filter(id__in=product_ids).select_related(
            "category", "brand"
        )
        product_map = {p.id: p for p in products}
        enriched = []
        for cand in candidates:
            product = product_map.get(cand["product_id"])
            if not product:
                continue
            score = self._calculate_score(
                candidate=cand,
                candidate_product=product,
                target=target_product,
                strategy=strategy,
            )
            enriched.append({
                **cand,
                "business_score": score,
                "product": product,
            })
        enriched.sort(key=lambda x: x["business_score"], reverse=True)
        return self._serialize_results(enriched, request)

    def _calculate_score(
        self,
        candidate: Dict,
        candidate_product: Product,
        target: Product,
        strategy: str,
    ) -> float:
        base_score = float(candidate.get("score", 0))
        factors = {
            "relevance": base_score,
            "price_proximity": 0.0,
            "availability": 1.0,
            "freshness": 0.3,
            "popularity": 0.0,
        }
        if target.price and candidate_product.price:
            try:
                t_p = float(target.price)
                c_p = float(candidate_product.price)
                if max(t_p, c_p) > 0:
                    price_ratio = min(t_p, c_p) / max(t_p, c_p)
                    factors["price_proximity"] = min(price_ratio, 1.0)
            except (TypeError, ValueError):
                pass
        if getattr(candidate_product, "stock_quantity", None) is not None:
            factors["availability"] = min(
                (candidate_product.stock_quantity or 0) / 10.0, 1.0
            )
        if getattr(candidate_product, "created_at", None):
            days_old = (timezone.now() - candidate_product.created_at).days
            if days_old < 7:
                factors["freshness"] = 1.0
            elif days_old < 30:
                factors["freshness"] = 0.7
            else:
                factors["freshness"] = 0.3
        weights = self._get_strategy_weights(strategy)
        return sum(
            factors.get(k, 0) * weights.get(k, 0) for k in weights
        )

    def _get_strategy_weights(self, strategy: str) -> Dict[str, float]:
        strategies = {
            "relevance": {
                "relevance": 1.0,
                "price_proximity": 0.0,
                "availability": 0.0,
                "freshness": 0.0,
                "popularity": 0.0,
            },
            "balanced": {
                "relevance": 0.4,
                "price_proximity": 0.2,
                "availability": 0.2,
                "freshness": 0.1,
                "popularity": 0.1,
            },
            "trending": {
                "relevance": 0.2,
                "price_proximity": 0.1,
                "availability": 0.2,
                "freshness": 0.3,
                "popularity": 0.2,
            },
        }
        return strategies.get(strategy, strategies["balanced"])

    def _serialize_results(
        self,
        ranked: List[Dict],
        request=None,
    ) -> List[Dict]:
        result = []
        context = {"request": request} if request else {}
        for item in ranked:
            product_data = ProductSerializer(
                item["product"],
                context=context,
            ).data
            result.append({
                "product": product_data,
                "similarity_score": item.get("score"),
                "business_score": round(item["business_score"], 4),
                "reason": self._get_recommendation_reason(item),
            })
        return result

    def _get_recommendation_reason(self, item: Dict) -> str:
        product = item["product"]
        score = item.get("score", 0)
        reasons = []
        if score > 0.9:
            reasons.append("Очень похожий стиль")
        elif score > 0.8:
            reasons.append("Похожий дизайн")
        if getattr(product, "brand", None) and product.brand:
            reasons.append(f"Бренд {product.brand.name}")
        return ", ".join(reasons) if reasons else "Рекомендуем"
