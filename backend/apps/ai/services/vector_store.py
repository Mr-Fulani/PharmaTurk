import logging
from typing import List, Dict, Optional, Any
import os
from django.conf import settings
from qdrant_client import QdrantClient
from qdrant_client.http import models

logger = logging.getLogger(__name__)


def _get_embedding_for_text(text: str) -> List[float]:
    """Получить эмбеддинг для текста (через LLMClient). Вынесено, чтобы избежать циклического импорта при ленивой инициализации."""
    from apps.ai.services.llm_client import LLMClient
    client = LLMClient()
    return client.get_embedding(text)

class QdrantManager:
    """
    Менеджер для работы с векторной базой данных Qdrant.
    Используется для поиска похожих категорий, шаблонов и товаров.
    """
    def __init__(self):
        self.host = os.environ.get("QDRANT_HOST", "qdrant")
        self.port = int(os.environ.get("QDRANT_PORT", 6333))
        self.client = QdrantClient(host=self.host, port=self.port)
        self.vector_size = 1536  # text-embedding-3-small
        self._ensure_collections()

    def _ensure_collections(self):
        """Проверка и создание коллекций."""
        collections = {
            "categories": self.vector_size,
            "templates": self.vector_size,
        }
        
        try:
            existing = [c.name for c in self.client.get_collections().collections]
            
            for name, size in collections.items():
                if name not in existing:
                    self.client.create_collection(
                        collection_name=name,
                        vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE)
                    )
                    logger.info(f"Created Qdrant collection: {name}")
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant collections: {e}")

    def search_similar_categories(self, embedding: List[float], limit: int = 3) -> List[Dict]:
        """Поиск похожих категорий."""
        try:
            response = self.client.query_points(
                collection_name="categories",
                query=embedding,
                limit=limit
            )
            return [
                {"id": hit.id, "score": hit.score, "payload": hit.payload or {}}
                for hit in response.points
            ]
        except Exception as e:
            logger.error(f"Qdrant search error: {e}")
            return []

    def upsert_category(self, category_id: int, embedding: List[float], payload: Dict):
        """Сохранение/обновление вектора категории."""
        try:
            self.client.upsert(
                collection_name="categories",
                points=[
                    models.PointStruct(
                        id=category_id,
                        vector=embedding,
                        payload=payload
                    )
                ]
            )
        except Exception as e:
            logger.error(f"Qdrant upsert error: {e}")

    def upsert_template(self, template_id: int, embedding: List[float], payload: Dict):
        """Сохранение вектора шаблона."""
        try:
            self.client.upsert(
                collection_name="templates",
                points=[
                    models.PointStruct(
                        id=template_id,
                        vector=embedding,
                        payload=payload
                    )
                ]
            )
        except Exception as e:
            logger.error(f"Qdrant template upsert error: {e}")

    def search_similar_categories_by_text(
        self, query_text: str, top_k: int = 5
    ) -> List[Dict]:
        """Поиск похожих категорий по текстовому запросу (RAG)."""
        if not query_text or not query_text.strip():
            return []
        try:
            embedding = _get_embedding_for_text(query_text.strip())
            raw = self.search_similar_categories(embedding, limit=top_k)
            return [
                {
                    "id": r["id"],
                    "score": r["score"],
                    "payload": r.get("payload") or {},
                    "category_name": (r.get("payload") or {}).get("category_name", ""),
                    "parent": (r.get("payload") or {}).get("parent", ""),
                    "examples": (r.get("payload") or {}).get("examples", ""),
                }
                for r in raw
            ]
        except Exception as e:
            logger.error(f"search_similar_categories_by_text error: {e}")
            return []

    def get_relevant_templates_by_text(
        self, product_type: str, top_k: int = 2
    ) -> List[str]:
        """Поиск релевантных шаблонов описаний по типу товара (RAG). Возвращает список текстов контента."""
        if not product_type or not product_type.strip():
            return []
        try:
            embedding = _get_embedding_for_text(product_type.strip())
            response = self.client.query_points(
                collection_name="templates",
                query=embedding,
                limit=top_k,
            )
            out = []
            for hit in response.points:
                payload = hit.payload or {}
                content = payload.get("content") or payload.get("text") or ""
                if content:
                    out.append(content)
            return out
        except Exception as e:
            logger.error(f"get_relevant_templates_by_text error: {e}")
            return []
