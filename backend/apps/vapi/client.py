"""HTTP-клиент для Vapi API (vapi.co).

Клиент для работы с API Vademecum Group для получения данных о лекарствах и БАДах.
Поддерживает более 20,000 лекарственных препаратов и 10,000 БАДов.
Все комментарии на русском.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx


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

    @classmethod
    def from_env(cls) -> "VapiClient":
        """Создаёт клиента, читая настройки из переменных окружения.

        Требуемые переменные: VAPI_BASE_URL, VAPI_API_KEY
        """
        base_url = os.getenv("VAPI_BASE_URL", "https://api.vapi.co")
        api_key = os.getenv("VAPI_API_KEY", "")
        
        if not api_key:
            raise ValueError("VAPI_API_KEY не установлен в переменных окружения")
        
        return cls(base_url=base_url, api_key=api_key)

    def _get_headers(self) -> Dict[str, str]:
        """Возвращает заголовки для запросов к Vapi API."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "TurkExport/1.0"
        }

    def list_products(
        self, 
        page: int = 1, 
        page_size: int = 100,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        search: Optional[str] = None,
        product_type: Optional[str] = None  # "drug" или "supplement"
    ) -> Dict[str, Any]:
        """Загружает список товаров с пагинацией и фильтрами.
        
        Args:
            page: Номер страницы (начиная с 1)
            page_size: Размер страницы (максимум 100)
            category: Фильтр по категории
            brand: Фильтр по бренду
            search: Поисковый запрос
            product_type: Тип продукта ("drug", "supplement")
            
        Returns:
            Словарь с данными товаров и метаинформацией
        """
        params = {
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

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/v1/products",
                    headers=self._get_headers(),
                    params=params
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            # Логируем ошибку и возвращаем пустой результат
            print(f"HTTP error {e.response.status_code}: {e.response.text}")
            return {"data": [], "total": 0, "page": page, "limit": page_size}
        except Exception as e:
            print(f"Request error: {e}")
            return {"data": [], "total": 0, "page": page, "limit": page_size}

    def get_product(self, product_id: str) -> Optional[ProductData]:
        """Получает детальную информацию о товаре.
        
        Args:
            product_id: Идентификатор товара
            
        Returns:
            Объект ProductData или None при ошибке
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/v1/products/{product_id}",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                data = response.json()
                
                # Преобразуем в нашу структуру данных
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
        except Exception as e:
            print(f"Error getting product {product_id}: {e}")
            return None

    def get_categories(self) -> List[Dict[str, Any]]:
        """Получает список доступных категорий."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/v1/categories",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json().get("data", [])
        except Exception as e:
            print(f"Error getting categories: {e}")
            return []

    def get_brands(self) -> List[Dict[str, Any]]:
        """Получает список доступных брендов."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/v1/brands",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json().get("data", [])
        except Exception as e:
            print(f"Error getting brands: {e}")
            return []

    def search_products(self, query: str, limit: int = 50, product_type: Optional[str] = None) -> List[ProductData]:
        """Выполняет поиск товаров по запросу.
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            product_type: Тип продукта ("drug", "supplement")
            
        Returns:
            Список товаров
        """
        try:
            params = {"q": query, "limit": limit}
            if product_type:
                params["type"] = product_type
                
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/v1/search",
                    headers=self._get_headers(),
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                # Преобразуем результаты в наши объекты
                products = []
                for item in data.get("data", []):
                    product = ProductData(
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
                    products.append(product)
                
                return products
        except Exception as e:
            print(f"Error searching products: {e}")
            return []

    def get_drug_interactions(self, drug_id: str) -> List[Dict[str, Any]]:
        """Получает информацию о взаимодействиях лекарства.
        
        Args:
            drug_id: Идентификатор лекарства
            
        Returns:
            Список взаимодействий
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/v1/products/{drug_id}/interactions",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json().get("data", [])
        except Exception as e:
            print(f"Error getting drug interactions for {drug_id}: {e}")
            return []

    def get_contraindications(self, product_id: str) -> List[Dict[str, Any]]:
        """Получает противопоказания для продукта.
        
        Args:
            product_id: Идентификатор продукта
            
        Returns:
            Список противопоказаний
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/v1/products/{product_id}/contraindications",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json().get("data", [])
        except Exception as e:
            print(f"Error getting contraindications for {product_id}: {e}")
            return []

