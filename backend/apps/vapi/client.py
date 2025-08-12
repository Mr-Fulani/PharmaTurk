"""HTTP-клиент для Vapi API (vapi.co).

Клиент для работы с API Vademecum Group для получения данных о лекарствах и БАДах.
Поддерживает более 20,000 лекарственных препаратов и 10,000 БАДов.
Все комментарии на русском.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx
from django.core.cache import cache
from django.utils.http import urlencode


def default_timeout() -> httpx.Timeout:
    """Возвращает стандартный таймаут для HTTP-запросов."""
    return httpx.Timeout(30.0, connect=10.0)


@dataclass
class ProductData:
    """Структура данных товара из Vapi API."""
    
    id: str
    name: str
    description: Optional[str] = None
    price: Optional[float] = None
    currency: str = "RUB"
    category: Optional[str] = None
    brand: Optional[str] = None
    images: List[str] = field(default_factory=list)
    url: Optional[str] = None
    availability: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Дополнительные поля для лекарств и БАДов
    active_ingredients: List[str] = field(default_factory=list)
    manufacturer: Optional[str] = None
    dosage_form: Optional[str] = None
    strength: Optional[str] = None
    barcode: Optional[str] = None
    atc_code: Optional[str] = None  # Анатомо-терапевтическая классификация
    rx_required: bool = False  # Требуется рецепт
    contraindications: List[str] = field(default_factory=list)
    side_effects: List[str] = field(default_factory=list)
    interactions: List[str] = field(default_factory=list)


@dataclass
class VapiClient:
    """Клиент для взаимодействия с Vapi API (vapi.co)."""

    base_url: str
    api_key: str
    timeout: httpx.Timeout = field(default_factory=default_timeout)
    default_lang: str = "en"

    @classmethod
    def from_env(cls) -> "VapiClient":
        """Создаёт клиента, читая настройки из переменных окружения.

        Требуемые переменные: VAPI_BASE_URL, VAPI_API_KEY
        """
        base_url = os.getenv("VAPI_BASE_URL", "https://api.vapi.co")
        api_key = os.getenv("VAPI_API_KEY", "")
        default_lang = os.getenv("VAPI_DEFAULT_LANG", "en")
        
        if not api_key:
            raise ValueError("VAPI_API_KEY не установлен в переменных окружения")
        
        return cls(base_url=base_url, api_key=api_key, default_lang=default_lang)

    def _get_headers(self, lang: Optional[str] = None) -> Dict[str, str]:
        """Возвращает заголовки для запросов к Vapi API.

        Args:
            lang: Язык ответа (например, "en" или "ru").
        """
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "TurkExport/1.0"
        }
        # Прокидываем язык, если задан
        headers["Accept-Language"] = (lang or self.default_lang)[:5]
        return headers

    def _cache_key(self, path: str, params: Optional[Dict[str, Any]], lang: Optional[str]) -> str:
        """Строит ключ кэша для GET-запроса."""
        params_str = urlencode(sorted((params or {}).items()))
        return f"vapi:{path}?{params_str}:lang={lang or self.default_lang}"

    def _get_json(self, path: str, params: Optional[Dict[str, Any]], lang: Optional[str], ttl_seconds: int) -> Tuple[Optional[Dict[str, Any]], Optional[int], Optional[str]]:
        """Выполняет GET с кэшем и возвратом JSON.

        Возвращает кортеж: (json, status_code, error_text)
        """
        key = self._cache_key(path, params, lang)
        cached = cache.get(key)
        if cached is not None:
            return cached, 200, None

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}{path}",
                    headers=self._get_headers(lang),
                    params=params or {},
                )
                response.raise_for_status()
                data = response.json()
                cache.set(key, data, ttl_seconds)
                return data, response.status_code, None
        except httpx.HTTPStatusError as e:
            # Логируем, не кэшируем ошибки
            print(f"HTTP error {e.response.status_code} for {path}: {e.response.text}")
            return None, e.response.status_code, e.response.text
        except Exception as e:
            print(f"Request error for {path}: {e}")
            return None, None, str(e)

    def list_products(
        self, 
        page: int = 1, 
        page_size: int = 100,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        search: Optional[str] = None,
        product_type: Optional[str] = None,  # "drug" или "supplement"
        lang: Optional[str] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Загружает список товаров с пагинацией и фильтрами.
        
        Args:
            page: Номер страницы (начиная с 1)
            page_size: Размер страницы (максимум 100)
            category: Фильтр по категории
            brand: Фильтр по бренду
            search: Поисковый запрос
            product_type: Тип продукта ("drug", "supplement")
            lang: Локаль ответа (например, "en", "ru")
            sort: Опциональная сортировка со стороны API (если поддерживается)
            
        Returns:
            Словарь с данными товаров и метаинформацией
        """
        params: Dict[str, Any] = {
            "page": page,
            "limit": page_size,
        }
        
        if category:
            params["category"] = category
        if brand:
            params["brand"] = brand
        if search:
            params["q"] = search
        if product_type:
            params["type"] = product_type
        if sort:
            params["sort"] = sort

        data, status_code, _ = self._get_json("/v1/products", params, lang, ttl_seconds=60 * 60 * 6)
        if data is None:
            return {"data": [], "total": 0, "page": page, "limit": page_size}
        return data

    def get_product(self, product_id: str, lang: Optional[str] = None) -> Optional[ProductData]:
        """Получает детальную информацию о товаре.
        
        Args:
            product_id: Идентификатор товара
            
        Returns:
            Объект ProductData или None при ошибке
        """
        data, _, _ = self._get_json(f"/v1/products/{product_id}", None, lang, ttl_seconds=60 * 60 * 12)
        if not data:
            return None
        return ProductData(
            id=data.get("id", product_id),
            name=data.get("name", ""),
            description=data.get("description"),
            price=data.get("price"),
            currency=data.get("currency", "RUB"),
            category=data.get("category"),
            brand=data.get("brand"),
            images=data.get("images", []),
            url=data.get("url"),
            availability=data.get("availability", True),
            metadata=data.get("metadata", {}),
            active_ingredients=data.get("active_ingredients", []),
            manufacturer=data.get("manufacturer"),
            dosage_form=data.get("dosage_form"),
            strength=data.get("strength"),
            barcode=data.get("barcode"),
            atc_code=data.get("atc_code"),
            rx_required=data.get("rx_required", False),
            contraindications=data.get("contraindications", []),
            side_effects=data.get("side_effects", []),
            interactions=data.get("interactions", [])
        )

    def get_categories(self, lang: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получает список доступных категорий."""
        data, _, _ = self._get_json("/v1/categories", None, lang, ttl_seconds=60 * 60 * 24)
        if not data:
            return []
        return data.get("data", [])

    def get_brands(self, lang: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получает список доступных брендов."""
        data, _, _ = self._get_json("/v1/brands", None, lang, ttl_seconds=60 * 60 * 24)
        if not data:
            return []
        return data.get("data", [])

    def search_products(self, query: str, limit: int = 50, product_type: Optional[str] = None, lang: Optional[str] = None) -> List[ProductData]:
        """Выполняет поиск товаров по запросу.
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            product_type: Тип продукта ("drug", "supplement")
            
        Returns:
            Список товаров
        """
        params: Dict[str, Any] = {"q": query, "limit": limit}
        if product_type:
            params["type"] = product_type

        data, _, _ = self._get_json("/v1/search", params, lang, ttl_seconds=60 * 30)
        if not data:
            return []

        products: List[ProductData] = []
        for item in data.get("data", []):
            products.append(
                ProductData(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    description=item.get("description"),
                    price=item.get("price"),
                    currency=item.get("currency", "RUB"),
                    category=item.get("category"),
                    brand=item.get("brand"),
                    images=item.get("images", []),
                    url=item.get("url"),
                    availability=item.get("availability", True),
                    metadata=item.get("metadata", {}),
                    active_ingredients=item.get("active_ingredients", []),
                    manufacturer=item.get("manufacturer"),
                    dosage_form=item.get("dosage_form"),
                    strength=item.get("strength"),
                    barcode=item.get("barcode"),
                    atc_code=item.get("atc_code"),
                    rx_required=item.get("rx_required", False),
                    contraindications=item.get("contraindications", []),
                    side_effects=item.get("side_effects", []),
                    interactions=item.get("interactions", [])
                )
            )
        return products

    def get_drug_interactions(self, drug_id: str, lang: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получает информацию о взаимодействиях лекарства.
        
        Args:
            drug_id: Идентификатор лекарства
            
        Returns:
            Список взаимодействий
        """
        data, _, _ = self._get_json(f"/v1/products/{drug_id}/interactions", None, lang, ttl_seconds=60 * 60 * 24)
        if not data:
            return []
        return data.get("data", [])

    def get_contraindications(self, product_id: str, lang: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получает противопоказания для продукта.
        
        Args:
            product_id: Идентификатор продукта
            
        Returns:
            Список противопоказаний
        """
        data, _, _ = self._get_json(f"/v1/products/{product_id}/contraindications", None, lang, ttl_seconds=60 * 60 * 24)
        if not data:
            return []
        return data.get("data", [])

