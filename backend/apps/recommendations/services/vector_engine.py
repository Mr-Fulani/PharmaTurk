"""Vector recommendation engine (Qdrant)."""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, List, Optional

import numpy as np
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.catalog.models import Product
from apps.recommendations.models import ProductVector

logger = logging.getLogger(__name__)


def _get_qdrant_client():
    from qdrant_client import QdrantClient
    host = os.environ.get("QDRANT_HOST", "qdrant")
    port = int(os.environ.get("QDRANT_PORT", 6333))
    return QdrantClient(host=host, port=port)


class QdrantRecommendationEngine:
    """
    Vector recommendation engine on Qdrant.
    Supports text, image, and combined vectors.
    """
    COLLECTION_NAME = "product_recommendations"
    TEXT_VECTOR_SIZE = 384
    IMAGE_VECTOR_SIZE = 512
    COMBINED_VECTOR_SIZE = 512  # weighted average of normalized text (padded) + image

    def __init__(self):
        self.client = _get_qdrant_client()
        self._ensure_collection_exists()

    def _ensure_collection_exists(self):
        try:
            from qdrant_client.http import models as qmodels
            existing = [c.name for c in self.client.get_collections().collections]
            if self.COLLECTION_NAME not in existing:
                self._create_collection()
                logger.info("Created Qdrant collection: %s", self.COLLECTION_NAME)
        except Exception as e:
            logger.error("Failed to check/create collection: %s", e)
            raise

    def _create_collection(self):
        from qdrant_client.http import models as qmodels
        self.client.create_collection(
            collection_name=self.COLLECTION_NAME,
            vectors_config={
                "text": qmodels.VectorParams(
                    size=self.TEXT_VECTOR_SIZE,
                    distance=qmodels.Distance.COSINE,
                ),
                "image": qmodels.VectorParams(
                    size=self.IMAGE_VECTOR_SIZE,
                    distance=qmodels.Distance.COSINE,
                ),
                "combined": qmodels.VectorParams(
                    size=self.COMBINED_VECTOR_SIZE,
                    distance=qmodels.Distance.COSINE,
                ),
            },
        )
        for field, schema in [("category_id", "integer"), ("price", "float"), ("is_active", "bool")]:
            try:
                self.client.create_payload_index(
                    collection_name=self.COLLECTION_NAME,
                    field_name=field,
                    field_schema=schema,
                )
            except Exception as e:
                logger.warning("Payload index %s: %s", field, e)

    def _product_payload(self, product: Product, image_url: Optional[str] = None) -> Dict[str, Any]:
        if image_url is None:
            image_url = product.main_image or ""
            if not image_url and hasattr(product, "images"):
                first = product.images.filter(image_url__isnull=False).exclude(image_url="").first()
                if first:
                    image_url = first.image_url or ""
        return {
            "product_id": product.id,
            "title": product.name,
            "category_id": product.category_id or 0,
            "category_name": product.category.name if product.category else None,
            "price": float(product.price) if product.price is not None else 0.0,
            "brand_id": product.brand_id or 0,
            "brand_name": product.brand.name if product.brand else None,
            "color": self._extract_color(product),
            "is_active": product.is_available,
            "created_at": product.created_at.isoformat() if product.created_at else None,
            "image_url": image_url or None,
        }

    def _extract_color(self, product: Product) -> str:
        text = f"{product.name} {product.description or ''}".lower()
        colors = [
            "красный", "синий", "черный", "белый", "розовый", "зеленый",
            "желтый", "серый", "бежевый", "коричневый", "фиолетовый",
            "оранжевый", "голубой", "золотой", "серебряный",
        ]
        for color in colors:
            if color in text:
                return color
        return "unknown"

    def _compute_combined_vector(
        self,
        text_vector: List[float],
        image_vector: List[float],
        text_weight: float = 0.6,
    ) -> List[float]:
        text_arr = np.array(text_vector, dtype=np.float32)
        image_arr = np.array(image_vector, dtype=np.float32)
        if len(text_arr) == self.TEXT_VECTOR_SIZE and len(image_arr) == self.IMAGE_VECTOR_SIZE:
            text_padded = np.zeros(self.IMAGE_VECTOR_SIZE, dtype=np.float32)
            text_padded[: len(text_arr)] = text_arr
            text_norm = text_padded / (np.linalg.norm(text_padded) + 1e-9)
            image_norm = image_arr / (np.linalg.norm(image_arr) + 1e-9)
            combined = text_weight * text_norm + (1 - text_weight) * image_norm
            combined = combined / (np.linalg.norm(combined) + 1e-9)
            return combined.tolist()
        return image_vector

    def upsert_product(
        self,
        product: Product,
        text_vector: List[float],
        image_vector: Optional[List[float]] = None,
        combined_vector: Optional[List[float]] = None,
    ) -> bool:
        from qdrant_client.http import models as qmodels
        payload = self._product_payload(product)
        if combined_vector is None and image_vector is not None:
            combined_vector = self._compute_combined_vector(text_vector, image_vector)
        vectors = {"text": text_vector}
        if image_vector is not None:
            vectors["image"] = image_vector
        if combined_vector is not None:
            vectors["combined"] = combined_vector
        else:
            combined_vector = self._compute_combined_vector(
                text_vector,
                image_vector or list(np.zeros(self.IMAGE_VECTOR_SIZE, dtype=np.float32)),
            )
            vectors["combined"] = combined_vector
        point = qmodels.PointStruct(
            id=product.id,
            vector=vectors,
            payload=payload,
        )
        self.client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[point],
        )
        ProductVector.objects.update_or_create(
            product=product,
            defaults={
                "qdrant_id": str(product.id),
                "category_id": product.category_id,
                "price": product.price,
                "brand_id": product.brand_id,
                "color": payload["color"],
                "is_active": product.is_available,
                "last_synced": timezone.now(),
            },
        )
        self._invalidate_similar_cache(product.id)
        return True

    def _invalidate_similar_cache(self, product_id: int) -> None:
        """Сбрасывает кэш похожих товаров и no_vector после индексации."""
        import redis
        from django.conf import settings
        try:
            redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
            client = redis.from_url(redis_url)
            for pattern in (f"*rec:similar:{product_id}:*", f"*rec:no_vector:{product_id}:*"):
                for key in client.scan_iter(match=pattern, count=50):
                    client.delete(key)
        except Exception as e:
            logger.warning("Failed to invalidate similar cache for product %s: %s", product_id, e)

    def _build_filter(
        self,
        filters: Optional[Dict] = None,
        exclude_product_id: Optional[int] = None,
        exclude_brand_id: Optional[int] = None,
    ):
        from qdrant_client.http import models as qmodels
        must = []
        must_not = []
        must.append(
            qmodels.FieldCondition(
                key="is_active",
                match=qmodels.MatchValue(value=True),
            )
        )
        if exclude_product_id is not None:
            must_not.append(
                qmodels.FieldCondition(
                    key="product_id",
                    match=qmodels.MatchValue(value=exclude_product_id),
                )
            )
        if exclude_brand_id is not None:
            must_not.append(
                qmodels.FieldCondition(
                    key="brand_id",
                    match=qmodels.MatchValue(value=exclude_brand_id),
                )
            )
        if filters:
            if "category_id" in filters:
                must.append(
                    qmodels.FieldCondition(
                        key="category_id",
                        match=qmodels.MatchValue(value=filters["category_id"]),
                    )
                )
            if "price_min" in filters or "price_max" in filters:
                r = qmodels.Range()
                if "price_min" in filters:
                    r.gte = float(filters["price_min"])
                if "price_max" in filters:
                    r.lte = float(filters["price_max"])
                must.append(qmodels.FieldCondition(key="price", range=r))
            if "color" in filters:
                must.append(
                    qmodels.FieldCondition(
                        key="color",
                        match=qmodels.MatchValue(value=str(filters["color"]).lower()),
                    )
                )
            if "brand_id" in filters:
                must.append(
                    qmodels.FieldCondition(
                        key="brand_id",
                        match=qmodels.MatchValue(value=filters["brand_id"]),
                    )
                )
        return qmodels.Filter(must=must, must_not=must_not) if (must or must_not) else None

    def _get_product_vector(self, product_id: int, vector_type: str) -> Optional[List[float]]:
        try:
            result = self.client.retrieve(
                collection_name=self.COLLECTION_NAME,
                ids=[product_id],
                with_vectors=True,
            )
            if not result:
                return None
            vectors = getattr(result[0], "vector", None)
            if vectors is None:
                return None
            if isinstance(vectors, dict):
                return vectors.get(vector_type)
            return vectors
        except Exception as e:
            logger.error("Error retrieving vector for %s: %s", product_id, e)
            return None

    def find_similar(
        self,
        product_id: int,
        vector_type: str = "combined",
        n_results: int = 12,
        filters: Optional[Dict] = None,
        exclude_same_brand: bool = False,
    ) -> List[Dict]:
        cache_key = f"rec:similar:{product_id}:{vector_type}:{hashlib.md5(str(sorted((filters or {}).items())).encode()).hexdigest()}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        no_vector_key = f"rec:no_vector:{product_id}:{vector_type}"
        if cache.get(no_vector_key) is not None:
            return []
        target_vector = self._get_product_vector(product_id, vector_type)
        if target_vector is None:
            logger.warning("No vector found for product %s", product_id)
            cache.set(no_vector_key, 1, 3600)
            return []
        exclude_brand_id = None
        if exclude_same_brand:
            brand_id = Product.objects.filter(pk=product_id).values_list("brand_id", flat=True).first()
            if brand_id is not None:
                exclude_brand_id = brand_id
        qfilter = self._build_filter(
            filters=filters,
            exclude_product_id=product_id,
            exclude_brand_id=exclude_brand_id,
        )
        try:
            results = self.client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=target_vector,
                limit=n_results + 1,
                query_filter=qfilter,
                using=vector_type if vector_type in ("text", "image", "combined") else None,
            )
        except TypeError:
            results = self.client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=target_vector,
                limit=n_results + 1,
                query_filter=qfilter,
            )
        points = getattr(results, "points", results) if hasattr(results, "points") else results
        similar = []
        for hit in points:
            hid = getattr(hit, "id", hit)
            if hid == product_id:
                continue
            score = getattr(hit, "score", None) or 0.0
            payload = getattr(hit, "payload", None) or {}
            similar.append({
                "product_id": hid,
                "score": round(float(score), 4),
                "payload": payload,
                "vector_type": vector_type,
            })
        cache.set(cache_key, similar[:n_results], 1800)
        return similar[:n_results]

    def find_similar_by_image(
        self,
        image_url: str,
        n_results: int = 12,
        filters: Optional[Dict] = None,
    ) -> List[Dict]:
        from .image_encoder import CLIPEncoder
        encoder = CLIPEncoder()
        image_vector = encoder.encode_image_from_url(image_url)
        if image_vector is None:
            return []
        qfilter = self._build_filter(filters=filters)
        try:
            results = self.client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=image_vector.tolist(),
                limit=n_results,
                query_filter=qfilter,
                using="image",
            )
        except TypeError:
            results = self.client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=image_vector.tolist(),
                limit=n_results,
                query_filter=qfilter,
            )
        points = getattr(results, "points", results) if hasattr(results, "points") else results
        return [
            {
                "product_id": getattr(hit, "id", hit),
                "score": round(float(getattr(hit, "score", 0) or 0), 4),
                "payload": getattr(hit, "payload", None) or {},
                "vector_type": "image",
            }
            for hit in points
        ]

    def find_by_text_query(
        self,
        query: str,
        n_results: int = 20,
        filters: Optional[Dict] = None,
    ) -> List[Dict]:
        from .text_encoder import TextEncoder
        encoder = TextEncoder()
        query_vector = encoder.encode(query).tolist()
        qfilter = self._build_filter(filters=filters)
        try:
            results = self.client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=query_vector,
                limit=n_results,
                query_filter=qfilter,
                using="text",
            )
        except TypeError:
            results = self.client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=query_vector,
                limit=n_results,
                query_filter=qfilter,
            )
        points = getattr(results, "points", results) if hasattr(results, "points") else results
        return [
            {
                "product_id": getattr(hit, "id", hit),
                "score": round(float(getattr(hit, "score", 0) or 0), 4),
                "payload": getattr(hit, "payload", None) or {},
                "vector_type": "text_query",
            }
            for hit in points
        ]

    def get_personalized_recommendations(
        self,
        user_vector: List[float],
        viewed_products: List[int],
        n_results: int = 20,
        diversity_factor: float = 0.3,
    ) -> List[Dict]:
        from qdrant_client.http import models as qmodels
        must_not = []
        for pid in viewed_products[:100]:
            must_not.append(
                qmodels.FieldCondition(
                    key="product_id",
                    match=qmodels.MatchValue(value=pid),
                )
            )
        qfilter = qmodels.Filter(must=[qmodels.FieldCondition(key="is_active", match=qmodels.MatchValue(value=True))], must_not=must_not) if must_not else self._build_filter(filters=None)
        try:
            results = self.client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=user_vector,
                limit=n_results * 2,
                query_filter=qfilter,
                using="combined",
            )
        except TypeError:
            results = self.client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=user_vector,
                limit=n_results * 2,
                query_filter=qfilter,
            )
        points = getattr(results, "points", results) if hasattr(results, "points") else results
        return [
            {
                "product_id": getattr(hit, "id", hit),
                "score": round(float(getattr(hit, "score", 0) or 0), 4),
                "payload": getattr(hit, "payload", None) or {},
            }
            for hit in points[:n_results]
        ]

    def delete_product(self, product_id: int) -> None:
        try:
            from qdrant_client.http import models as qmodels
            self.client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=qmodels.PointIdsList(points=[product_id]),
            )
        except Exception as e:
            logger.warning("Qdrant delete product %s: %s", product_id, e)
        ProductVector.objects.filter(product_id=product_id).delete()

    def get_collection_stats(self) -> Dict[str, Any]:
        info = self.client.get_collection(self.COLLECTION_NAME)
        return {
            "vectors_count": getattr(info, "vectors_count", 0),
            "indexed_vectors_count": getattr(info, "indexed_vectors_count", 0),
            "segments_count": getattr(info, "segments_count", 0),
            "status": getattr(info, "status", "unknown"),
        }
