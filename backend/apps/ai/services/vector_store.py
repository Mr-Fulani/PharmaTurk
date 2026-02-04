import logging
from typing import List, Dict, Optional, Any
import os
from django.conf import settings
from qdrant_client import QdrantClient
from qdrant_client.http import models

logger = logging.getLogger(__name__)

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
            results = self.client.search(
                collection_name="categories",
                query_vector=embedding,
                limit=limit
            )
            return [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload
                } for hit in results
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
