"""Сериализаторы для API каталога товаров."""

from urllib.parse import quote
from decimal import Decimal
from django.db.models import Count
from rest_framework import serializers
from .models import (
    Category, CategoryTranslation, Brand, BrandTranslation, Product, ProductTranslation, ProductImage, ProductAttribute, PriceHistory, Favorite,
    ClothingProduct, ClothingProductTranslation, ClothingProductImage, ClothingVariant, ClothingVariantImage, ClothingVariantSize, ClothingProductSize,
    ShoeProduct, ShoeProductTranslation, ShoeProductImage, ShoeVariant, ShoeVariantImage, ShoeVariantSize, ShoeProductSize,
    ElectronicsProduct, ElectronicsProductTranslation, ElectronicsProductImage,
    FurnitureProduct, FurnitureProductTranslation, FurnitureVariant, FurnitureVariantImage,
    Service, ServiceTranslation,
    Banner, BannerMedia, Author, ProductAuthor,
)


def _resolve_media_url(value, request):
    if not value:
        return None
    if 'instagram.f' in value or 'cdninstagram.com' in value:
        if request:
            scheme = request.scheme
            host = request.get_host()
            if 'backend' in host or 'localhost:3001' in host or 'localhost:3000' in host:
                base_url = f"{scheme}://localhost:8000"
            else:
                base_url = f"{scheme}://{host}"
            return f"{base_url}/api/catalog/proxy-image/?url={quote(value)}"
        return f"http://localhost:8000/api/catalog/proxy-image/?url={quote(value)}"
    if not value.startswith('http'):
        if request:
            scheme = request.scheme
            host = request.get_host()
            if 'backend' in host or 'localhost:3001' in host or 'localhost:3000' in host:
                base_url = f"{scheme}://localhost:8000"
            else:
                base_url = f"{scheme}://{host}"
            return f"{base_url}/media/{value}"
        return f"http://localhost:8000/media/{value}"
    return value


def _resolve_file_url(file_field, request):
    if not file_field:
        return None
    if hasattr(file_field, "url"):
        if request:
            return request.build_absolute_uri(file_field.url)
        return file_field.url
    return None


class CategoryTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов категорий."""
    
    class Meta:
        model = CategoryTranslation
        fields = ['locale', 'name', 'description']


class BrandTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов брендов."""
    
    class Meta:
        model = BrandTranslation
        fields = ['locale', 'name', 'description']


class ProductTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов товаров."""
    
    class Meta:
        model = ProductTranslation
        fields = ['locale', 'description']


class FurnitureProductTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов товаров мебели."""
    
    class Meta:
        model = FurnitureProductTranslation
        fields = ['locale', 'description']


class ServiceTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов услуг."""
    
    class Meta:
        model = ServiceTranslation
        fields = ['locale', 'name', 'description']


class ClothingProductTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов товаров одежды."""
    
    class Meta:
        model = ClothingProductTranslation
        fields = ['locale', 'description']


class ShoeProductTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов товаров обуви."""
    
    class Meta:
        model = ShoeProductTranslation
        fields = ['locale', 'description']


class ElectronicsProductTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов товаров электроники."""
    
    class Meta:
        model = ElectronicsProductTranslation
        fields = ['locale', 'description']


class CategorySerializer(serializers.ModelSerializer):
    """Сериализатор для категорий."""
    
    children_count = serializers.SerializerMethodField()
    card_media_url = serializers.SerializerMethodField()
    category_type = serializers.SerializerMethodField()
    category_type_slug = serializers.SerializerMethodField()
    gender_display = serializers.SerializerMethodField()
    translations = CategoryTranslationSerializer(many=True, read_only=True)
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'card_media_url', 'parent',
            'external_id', 'is_active', 'sort_order',
            'children_count', 'created_at', 'updated_at',
            'category_type', 'category_type_slug', 'translations',
            'gender', 'gender_display', 'clothing_type', 'shoe_type', 'device_type',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_children_count(self, obj):
        """Количество подкатегорий."""
        return obj.children.filter(is_active=True).count()

    def get_card_media_url(self, obj):
        """Полный URL медиа-файла карточки категории."""
        url = obj.get_card_media_url()
        if not url:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(url)
        return url

    def get_category_type(self, obj):
        """Название типа категории."""
        if not obj.category_type_id:
            return None
        return obj.category_type.name

    def get_category_type_slug(self, obj):
        """Slug типа категории."""
        if not obj.category_type_id:
            return None
        return obj.category_type.slug
    
    def get_gender_display(self, obj):
        """Отображение значения gender."""
        if obj.gender:
            return obj.get_gender_display()
        return None


class BrandSerializer(serializers.ModelSerializer):
    """Сериализатор для брендов."""
    
    products_count = serializers.SerializerMethodField()
    card_media_url = serializers.SerializerMethodField()
    primary_category_slug = serializers.SerializerMethodField()
    translations = BrandTranslationSerializer(many=True, read_only=True)
    
    class Meta:
        model = Brand
        fields = [
            'id', 'name', 'slug', 'description', 'logo', 'website', 'card_media_url',
            'primary_category_slug',
            'external_id', 'is_active', 'products_count', 
            'translations',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_products_count(self, obj):
        """Количество товаров бренда."""
        return obj.products.filter(is_active=True).count()

    def get_card_media_url(self, obj):
        """Полный URL медиа-файла карточки бренда."""
        url = obj.get_card_media_url()
        if not url:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(url)
        return url

    def get_primary_category_slug(self, obj):
        """Slug основной категории бренда, с fallback на товары бренда."""
        if obj.primary_category_slug:
            return obj.primary_category_slug

        allowed_map = {
            "medicines": "medicines",
            "supplements": "supplements",
            "medical_equipment": "medical-equipment",
            "medical-equipment": "medical-equipment",
            "clothing": "clothing",
            "underwear": "underwear",
            "headwear": "headwear",
            "shoes": "shoes",
            "electronics": "electronics",
            "furniture": "furniture",
            "tableware": "tableware",
            "accessories": "accessories",
            "jewelry": "jewelry",
        }

        def normalize(slug: str | None) -> str | None:
            if not slug:
                return None
            slug = slug.replace("_", "-").lower()
            return allowed_map.get(slug, slug)

        # 1) Считаем самые частые категории (берём корневой/родительский slug если есть)
        products_qs = obj.products.filter(is_active=True).select_related("category__parent")
        category_counts = (
            products_qs
            .values("category__slug", "category__parent__slug")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")
        )
        for row in category_counts:
            slug_candidate = row.get("category__parent__slug") or row.get("category__slug")
            norm = normalize(slug_candidate)
            if norm in allowed_map.values():
                return norm

        # 2) Если по категориям не нашли — берём самые частые product_type
        product_type_counts = (
            products_qs
            .values("product_type")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")
        )
        for row in product_type_counts:
            norm = normalize(row.get("product_type"))
            if norm in allowed_map.values():
                return norm

        return None


class ProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор для изображений товара."""
    
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class ProductAttributeSerializer(serializers.ModelSerializer):
    """Сериализатор для атрибутов товара."""
    
    attribute_type_display = serializers.CharField(source='get_attribute_type_display', read_only=True)
    
    class Meta:
        model = ProductAttribute
        fields = ['id', 'attribute_type', 'attribute_type_display', 'name', 'value', 'sort_order']


class PriceHistorySerializer(serializers.ModelSerializer):
    """Сериализатор для истории цен."""
    
    class Meta:
        model = PriceHistory
        fields = ['price', 'currency', 'recorded_at', 'source']


class AuthorSerializer(serializers.ModelSerializer):
    """Сериализатор для авторов."""
    full_name = serializers.ReadOnlyField()
    
    class Meta:
        model = Author
        fields = ['id', 'first_name', 'last_name', 'full_name', 'bio', 'photo', 'birth_date', 'created_at']


class ProductAuthorSerializer(serializers.ModelSerializer):
    """Сериализатор для связи товаров с авторами."""
    author = AuthorSerializer(read_only=True)
    
    class Meta:
        model = ProductAuthor
        fields = ['id', 'author', 'created_at']


class ProductSerializer(serializers.ModelSerializer):
    """Сериализатор для товаров (краткая информация)."""
    
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()  # Изменено на метод
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()  # Изменено на метод
    converted_price_rub = serializers.SerializerMethodField()  # Изменено на метод
    converted_price_usd = serializers.SerializerMethodField()  # Изменено на метод
    final_price_rub = serializers.SerializerMethodField()  # Изменено на метод
    final_price_usd = serializers.SerializerMethodField()  # Изменено на метод
    margin_percent_applied = serializers.SerializerMethodField()  # Изменено на метод
    prices_in_currencies = serializers.SerializerMethodField()
    current_price = serializers.SerializerMethodField()
    price_breakdown = serializers.SerializerMethodField()
    translations = ProductTranslationSerializer(many=True, read_only=True)
    book_authors = ProductAuthorSerializer(many=True, read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'description',
            'category', 'brand',
            'product_type',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'converted_price_rub', 'converted_price_usd',
            'final_price_rub', 'final_price_usd', 'margin_percent_applied',
            'prices_in_currencies', 'current_price', 'price_breakdown',
            'availability_status', 'is_available', 'stock_quantity',
            'min_order_quantity', 'pack_quantity',
            'country_of_origin', 'gtin', 'mpn',
            'weight_value', 'weight_unit', 'length', 'width', 'height', 'dimensions_unit',
            # Поля специфичные для книг
            'isbn', 'publisher', 'publication_date', 'pages', 'language',
            'cover_type', 'rating', 'reviews_count', 'is_bestseller', 'is_new',
            'book_authors',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
            'main_image_url', 'video_url',
            'is_featured', 'created_at', 'updated_at', 'translations'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        """URL главного изображения."""
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "main_image_file", None), request)
        if file_url:
            return file_url
        
        # Сначала проверяем main_image
        if obj.main_image:
            # Если это Instagram URL, используем прокси
            if 'instagram.f' in obj.main_image or 'cdninstagram.com' in obj.main_image:
                if request:
                    scheme = request.scheme
                    host = request.get_host()
                    if 'backend' in host or 'localhost:3001' in host or 'localhost:3000' in host:
                        base_url = f"{scheme}://localhost:8000"
                    else:
                        base_url = f"{scheme}://{host}"
                    return f"{base_url}/api/catalog/proxy-image/?url={quote(obj.main_image)}"
                return f"http://localhost:8000/api/catalog/proxy-image/?url={quote(obj.main_image)}"
            # Если это локальный файл (не начинается с http), добавляем /media/
            elif not obj.main_image.startswith('http'):
                if request:
                    scheme = request.scheme
                    host = request.get_host()
                    if 'backend' in host or 'localhost:3001' in host or 'localhost:3000' in host:
                        base_url = f"{scheme}://localhost:8000"
                    else:
                        base_url = f"{scheme}://{host}"
                    return f"{base_url}/media/{obj.main_image}"
                return f"http://localhost:8000/media/{obj.main_image}"
            return obj.main_image
        
        # Затем ищем главное изображение в связанных изображениях
        main_img = obj.images.filter(is_main=True).first()
        if main_img:
            file_url = _resolve_file_url(getattr(main_img, "image_file", None), request)
            if file_url:
                return file_url
            if 'instagram.f' in main_img.image_url or 'cdninstagram.com' in main_img.image_url:
                if request:
                    scheme = request.scheme
                    host = request.get_host()
                    if 'backend' in host or 'localhost:3001' in host or 'localhost:3000' in host:
                        base_url = f"{scheme}://localhost:8000"
                    else:
                        base_url = f"{scheme}://{host}"
                    return f"{base_url}/api/catalog/proxy-image/?url={quote(main_img.image_url)}"
                return f"http://localhost:8000/api/catalog/proxy-image/?url={quote(main_img.image_url)}"
            return main_img.image_url
        
        # Если нет главного, берем первое изображение
        first_img = obj.images.first()
        if first_img:
            file_url = _resolve_file_url(getattr(first_img, "image_file", None), request)
            if file_url:
                return file_url
            if 'instagram.f' in first_img.image_url or 'cdninstagram.com' in first_img.image_url:
                if request:
                    scheme = request.scheme
                    host = request.get_host()
                    if 'backend' in host or 'localhost:3001' in host or 'localhost:3000' in host:
                        base_url = f"{scheme}://localhost:8000"
                    else:
                        base_url = f"{scheme}://{host}"
                    return f"{base_url}/api/catalog/proxy-image/?url={quote(first_img.image_url)}"
                return f"http://localhost:8000/api/catalog/proxy-image/?url={quote(first_img.image_url)}"
            return first_img.image_url
        
        # Если изображений нет, возвращаем None
        return None
    
    def get_price_formatted(self, obj):
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        if obj.price is not None:
            from_currency = (obj.currency or 'RUB').upper()
            if preferred_currency != from_currency:
                try:
                    from .utils.currency_converter import currency_converter
                    _, _, price_with_margin = currency_converter.convert_price(
                        Decimal(obj.price),
                        from_currency,
                        preferred_currency,
                        apply_margin=True,
                    )
                    return f"{price_with_margin} {preferred_currency}"
                except Exception:
                    pass
            return f"{obj.price} {from_currency}"
        return None
    
    def get_old_price_formatted(self, obj):
        """Форматированная старая цена."""
        if obj.old_price is not None:
            request = self.context.get('request')
            preferred_currency = self._get_preferred_currency(request)
            from_currency = (obj.currency or 'RUB').upper()
            if preferred_currency != from_currency:
                try:
                    from .utils.currency_converter import currency_converter
                    _, _, price_with_margin = currency_converter.convert_price(
                        Decimal(obj.old_price),
                        from_currency,
                        preferred_currency,
                        apply_margin=True,
                    )
                    return f"{price_with_margin} {preferred_currency}"
                except Exception:
                    pass
            return f"{obj.old_price} {from_currency}"
        return None

    def _get_preferred_currency(self, request):
        """Определяет валюту по приоритетам: explicit -> язык -> default."""
        default_currency = 'RUB'
        if not request:
            return default_currency

        # Явный выбор валюты имеет приоритет
        preferred_currency = request.headers.get('X-Currency')
        if preferred_currency:
            return preferred_currency.upper()
        preferred_currency = request.query_params.get('currency')
        if preferred_currency:
            return preferred_currency.upper()

        if getattr(request, 'user', None) and request.user.is_authenticated:
            user_currency = getattr(request.user, 'currency', None)
            if user_currency:
                return user_currency.upper()

        language_code = getattr(request, 'LANGUAGE_CODE', None)
        language_currency_map = {
            'en': 'USD',
            'ru': 'RUB',
        }
        return language_currency_map.get(language_code, default_currency)
    
    def get_price(self, obj):
        """Получает цену в предпочитаемой валюте."""
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        
        # Получаем цену в предпочитаемой валюте
        try:
            prices = obj.get_all_prices()
            if prices and preferred_currency in prices:
                return prices[preferred_currency].get('price_with_margin')
            elif prices:
                # Если предпочитаемой валюты нет, вернем базовую
                for currency, data in prices.items():
                    if data.get('is_base_price'):
                        return data.get('price_with_margin')
                # Или просто первую
                first_currency = list(prices.keys())[0]
                return prices[first_currency].get('price_with_margin')
        except Exception:
            pass
        
        # Fallback к старому полю
        return obj.price
    
    def get_currency(self, obj):
        """Получает валюту товара."""
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        
        # Получаем валюту из новой системы
        try:
            prices = obj.get_all_prices()
            if prices and preferred_currency in prices:
                return preferred_currency
            elif prices:
                # Если предпочитаемой валюты нет, вернем базовую
                for currency, data in prices.items():
                    if data.get('is_base_price'):
                        return currency
                # Или просто первую
                return list(prices.keys())[0]
        except Exception:
            pass
        
        # Fallback к старому полю
        return obj.currency if obj.currency else 'RUB'
    
    def get_converted_price_rub(self, obj):
        """Получает конвертированную цену в RUB."""
        try:
            prices = obj.get_all_prices()
            if 'RUB' in prices:
                return prices['RUB'].get('converted_price')
        except Exception:
            pass
        return None
    
    def get_converted_price_usd(self, obj):
        """Получает конвертированную цену в USD."""
        try:
            prices = obj.get_all_prices()
            if 'USD' in prices:
                return prices['USD'].get('converted_price')
        except Exception:
            pass
        return None
    
    def get_final_price_rub(self, obj):
        """Получает финальную цену в RUB с маржой."""
        try:
            prices = obj.get_all_prices()
            if 'RUB' in prices:
                return prices['RUB'].get('price_with_margin')
        except Exception:
            pass
        return None
    
    def get_final_price_usd(self, obj):
        """Получает финальную цену в USD с маржой."""
        try:
            prices = obj.get_all_prices()
            if 'USD' in prices:
                return prices['USD'].get('price_with_margin')
        except Exception:
            pass
        return None
    
    def get_margin_percent_applied(self, obj):
        """Получает примененную маржу."""
        try:
            prices = obj.get_all_prices()
            if prices:
                # Найдем базовую валюту
                for currency, data in prices.items():
                    if data.get('is_base_price'):
                        # Если это базовая валюта, маржа 0%
                        return 0
                
                # Для других валют можно взять среднюю маржу
                margins = []
                for currency, data in prices.items():
                    if not data.get('is_base_price') and data.get('price_with_margin') and data.get('converted_price'):
                        if data['converted_price'] > 0:
                            margin = ((data['price_with_margin'] - data['converted_price']) / data['converted_price']) * 100
                            margins.append(margin)
                
                if margins:
                    return sum(margins) / len(margins)
        except Exception:
            pass
        return 0
    
    def get_prices_in_currencies(self, obj):
        """Получает цены во всех валютах."""
        try:
            return obj.get_all_prices()
        except Exception:
            # Если ошибка, вернем базовую цену
            if obj.price and obj.currency:
                return {
                    obj.currency: {
                        'original_price': obj.price,
                        'converted_price': obj.price,
                        'price_with_margin': obj.price,
                        'is_base_price': True
                    }
                }
            return {}
    
    def get_current_price(self, obj):
        """Получает текущую цену в предпочитаемой валюте."""
        request = self.context.get('request')
        preferred_currency = 'RUB'  # По умолчанию
        
        # Можно определить предпочитаемую валюту из заголовков или параметров запроса
        if request:
            # Проверяем заголовок X-Currency
            preferred_currency = request.headers.get('X-Currency', 'RUB')
            # Или параметр запроса currency
            preferred_currency = request.query_params.get('currency', preferred_currency)
        
        price, currency = obj.get_current_price(preferred_currency)
        
        if price:
            return {
                'amount': price,
                'currency': currency,
                'formatted': f"{price} {currency}"
            }
        
        return None
    
    def get_price_breakdown(self, obj):
        """Получает детализацию цены для базовой валюты товара."""
        if obj.price and obj.currency:
            breakdown = obj.get_price_breakdown('RUB')  # По умолчанию для RUB
            if breakdown:
                return breakdown
        return None


class ProductDetailSerializer(ProductSerializer):
    """Сериализатор для товаров (детальная информация)."""
    
    images = ProductImageSerializer(many=True, read_only=True)
    attributes = ProductAttributeSerializer(many=True, read_only=True)
    price_history = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()
    
    class Meta(ProductSerializer.Meta):
        fields = ProductSerializer.Meta.fields + [
            'images', 'attributes', 'price_history', 'external_id',
            'external_url', 'sku', 'barcode', 'last_synced_at'
        ]
    
    def get_price_history(self, obj):
        """История цен (последние 10 записей)."""
        history = obj.price_history.all()[:10]
        return PriceHistorySerializer(history, many=True).data
    
    def get_og_image_url(self, obj):
        """OG изображение с прокси для Instagram."""
        request = self.context.get('request')
        
        # Если og_image_url заполнен, используем его
        if obj.og_image_url:
            if 'instagram.f' in obj.og_image_url or 'cdninstagram.com' in obj.og_image_url:
                if request:
                    scheme = request.scheme
                    host = request.get_host()
                    if 'backend' in host or 'localhost:3001' in host or 'localhost:3000' in host:
                        base_url = f"{scheme}://localhost:8000"
                    else:
                        base_url = f"{scheme}://{host}"
                    return f"{base_url}/api/catalog/proxy-image/?url={quote(obj.og_image_url)}"
                return f"http://localhost:8000/api/catalog/proxy-image/?url={quote(obj.og_image_url)}"
            return obj.og_image_url
        
        # Иначе используем main_image
        return self.get_main_image_url(obj)


class ProductSearchSerializer(serializers.ModelSerializer):
    """Сериализатор для поиска товаров."""
    
    category_name = serializers.CharField(source='category.name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    price_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'category_name', 'brand_name',
            'product_type',
            'price', 'price_formatted', 'currency', 'is_available',
            'main_image', 'is_featured'
        ]
    
    def get_price_formatted(self, obj):
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None


class CatalogStatsSerializer(serializers.Serializer):
    """Сериализатор для статистики каталога."""
    
    total_products = serializers.IntegerField()
    total_categories = serializers.IntegerField()
    total_brands = serializers.IntegerField()
    available_products = serializers.IntegerField()
    featured_products = serializers.IntegerField()
    last_sync = serializers.DateTimeField(allow_null=True)


class FavoriteSerializer(serializers.ModelSerializer):
    """Сериализатор для избранного."""
    
    product = serializers.SerializerMethodField()
    
    class Meta:
        model = Favorite
        fields = ['id', 'product', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_product(self, obj):
        """Сериализация товара в зависимости от его типа."""
        product = obj.product
        request = self.context.get('request')
        
        # Определяем тип товара по модели
        product_type = 'medicines'  # По умолчанию
        if isinstance(product, ClothingProduct):
            product_type = 'clothing'
            product_data = ClothingProductSerializer(product, context={'request': request}).data
        elif isinstance(product, ShoeProduct):
            product_type = 'shoes'
            product_data = ShoeProductSerializer(product, context={'request': request}).data
        elif isinstance(product, ElectronicsProduct):
            product_type = 'electronics'
            product_data = ElectronicsProductSerializer(product, context={'request': request}).data
        elif isinstance(product, FurnitureProduct):
            product_type = 'furniture'
            product_data = FurnitureProductSerializer(product, context={'request': request}).data
        elif isinstance(product, Product):
            product_type = getattr(product, 'product_type', None) or 'medicines'
            product_data = ProductSerializer(product, context={'request': request}).data
        else:
            # Fallback для неизвестных типов
            product_data = {
                'id': getattr(product, 'id', None),
                'name': getattr(product, 'name', 'Unknown'),
                'slug': getattr(product, 'slug', ''),
                'price': str(getattr(product, 'price', '')) if hasattr(product, 'price') else None,
                'currency': getattr(product, 'currency', ''),
                'main_image_url': getattr(product, 'main_image', None) or getattr(product, 'main_image_url', None)
            }
        
        # Добавляем тип товара в данные
        product_data['_product_type'] = product_type
        return product_data


class AddToFavoriteSerializer(serializers.Serializer):
    """Сериализатор для добавления товара в избранное."""
    
    product_id = serializers.IntegerField(required=True)
    product_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    def validate(self, attrs):
        """Проверка существования товара в зависимости от типа."""
        product_id = attrs.get('product_id')
        product_type = (attrs.get('product_type') or 'medicines').strip().lower()
        product_type = product_type.replace('-', '_')
        product_type = {
            'medical_accessories': 'accessories',
            'medical_accessory': 'accessories',
            'accessory': 'accessories',
        }.get(product_type, product_type)
        
        # Маппинг типов товаров на модели
        from .models import Product, ClothingProduct, ShoeProduct, ElectronicsProduct, FurnitureProduct
        
        PRODUCT_MODEL_MAP = {
            'medicines': Product,
            'supplements': Product,
            'medical_equipment': Product,
            'tableware': Product,
            'accessories': Product,
            'jewelry': Product,
            'underwear': Product,
            'headwear': Product,
            'books': Product,
            'clothing': ClothingProduct,
            'shoes': ShoeProduct,
            'electronics': ElectronicsProduct,
            'furniture': FurnitureProduct,
        }
        
        model_class = PRODUCT_MODEL_MAP.get(product_type, Product)
        
        try:
            product = model_class.objects.get(id=product_id)
            # Проверяем is_active, если поле существует
            if hasattr(product, 'is_active') and not product.is_active:
                raise serializers.ValidationError({"product_id": "Товар неактивен"})
        except model_class.DoesNotExist:
            if model_class is not Product:
                try:
                    product = Product.objects.get(id=product_id, product_type=product_type)
                    if hasattr(product, 'is_active') and not product.is_active:
                        raise serializers.ValidationError({"product_id": "Товар неактивен"})
                except Product.DoesNotExist:
                    raise serializers.ValidationError({"product_id": "Товар не найден"})
            else:
                raise serializers.ValidationError({"product_id": "Товар не найден"})
        
        attrs['_product'] = product
        attrs['_product_type'] = product_type
        return attrs


# ============================================================================
# СЕРИАЛИЗАТОРЫ ДЛЯ ОДЕЖДЫ, ОБУВИ И ЭЛЕКТРОНИКИ
# ============================================================================

class ClothingCategorySerializer(serializers.ModelSerializer):
    """Сериализатор для категорий одежды."""
    
    children_count = serializers.SerializerMethodField()
    gender_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'parent', 
            'gender', 'gender_display', 'clothing_type',
            'external_id', 'is_active', 'sort_order', 
            'children_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_children_count(self, obj):
        """Количество подкатегорий."""
        return obj.children.filter(is_active=True).count()
    
    def get_gender_display(self, obj):
        """Отображение значения gender."""
        if obj.gender:
            return obj.get_gender_display()
        return None


class ClothingProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений одежды."""
    
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ClothingProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class ClothingVariantImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений варианта одежды."""
    
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ClothingVariantImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class ClothingProductSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClothingProductSize
        fields = ['id', 'size', 'is_available', 'stock_quantity', 'sort_order']
        read_only_fields = ['id']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        stock = data.get('stock_quantity')
        if stock is not None and stock == 0:
            data['is_available'] = False
        return data


class ClothingVariantSizeSerializer(serializers.ModelSerializer):
    """Сериализатор размеров варианта одежды."""

    class Meta:
        model = ClothingVariantSize
        fields = ['id', 'size', 'is_available', 'stock_quantity', 'sort_order']
        read_only_fields = ['id']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        stock = data.get('stock_quantity')
        if stock is not None and stock == 0:
            data['is_available'] = False
        return data


class ClothingVariantSerializer(serializers.ModelSerializer):
    """Сериализатор варианта одежды."""

    images = ClothingVariantImageSerializer(many=True, read_only=True)
    sizes = ClothingVariantSizeSerializer(many=True, read_only=True)

    class Meta:
        model = ClothingVariant
        fields = [
            'id', 'slug', 'name', 'color',
            'size',  # устаревшее поле оставлено для совместимости
            'sizes',
            'price', 'old_price', 'currency',
            'is_available',
            'main_image', 'images',
            'sku', 'barcode', 'gtin', 'mpn',
            'is_active', 'sort_order',
        ]
        read_only_fields = ['id', 'slug', 'sort_order']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        preferred = None
        if request:
            preferred = request.headers.get('X-Currency') or request.query_params.get('currency')
        preferred_currency = (preferred or data.get('currency') or 'RUB').upper()

        raw_price = data.get('price')
        raw_currency = (data.get('currency') or 'RUB').upper() if data.get('currency') else 'RUB'
        if raw_price is None:
            return data

        try:
            from .utils.currency_converter import currency_converter
            _, _, price_with_margin = currency_converter.convert_price(
                Decimal(str(raw_price)),
                raw_currency,
                preferred_currency,
                apply_margin=True,
            )
            data['price'] = str(price_with_margin)
            data['currency'] = preferred_currency
        except Exception:
            data['currency'] = raw_currency
        return data


class ClothingProductSerializer(serializers.ModelSerializer):
    """Сериализатор для товаров одежды (краткая информация)."""
    
    category = ClothingCategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    sizes = ClothingProductSizeSerializer(many=True, read_only=True)
    variants = serializers.SerializerMethodField()
    default_variant_slug = serializers.SerializerMethodField()
    active_variant_slug = serializers.SerializerMethodField()
    active_variant_price = serializers.SerializerMethodField()
    active_variant_currency = serializers.SerializerMethodField()
    active_variant_stock_quantity = serializers.SerializerMethodField()
    active_variant_main_image_url = serializers.SerializerMethodField()
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    translations = ClothingProductTranslationSerializer(many=True, read_only=True)
    
    class Meta:
        model = ClothingProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'size', 'color', 'material', 'season',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url',
            'images', 'sizes',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'is_featured', 'created_at', 'updated_at', 'translations'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        """URL главного изображения.
        
        Сначала main_image, затем главное изображение из галереи,
        затем первое изображение.
        """
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "main_image_file", None), request)
        if file_url:
            return file_url
        if obj.main_image:
            return _resolve_media_url(obj.main_image, request)
        # Пробуем активный вариант
        variant = self._get_active_variant(obj)
        if variant:
            file_url = _resolve_file_url(getattr(variant, "main_image_file", None), request)
            if file_url:
                return file_url
            if variant.main_image:
                return _resolve_media_url(variant.main_image, request)
            v_main = variant.images.filter(is_main=True).first()
            if v_main:
                file_url = _resolve_file_url(getattr(v_main, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(v_main.image_url, request)
            v_first = variant.images.first()
            if v_first:
                file_url = _resolve_file_url(getattr(v_first, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(v_first.image_url, request)
        gallery = getattr(obj, "images", None)
        if gallery:
            main_img = obj.images.filter(is_main=True).first()
            if main_img:
                file_url = _resolve_file_url(getattr(main_img, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(main_img.image_url, request)
            first_img = obj.images.first()
            if first_img:
                file_url = _resolve_file_url(getattr(first_img, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(first_img.image_url, request)
        return None
    
    def get_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return self.get_active_variant_price(obj)

        preferred_currency = self._get_preferred_currency(obj)
        if obj.price is None:
            return None

        from_currency = (obj.currency or 'RUB').upper()
        if preferred_currency != from_currency:
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_with_margin = currency_converter.convert_price(
                    Decimal(obj.price),
                    from_currency,
                    preferred_currency,
                    apply_margin=True,
                )
                return f"{price_with_margin} {preferred_currency}"
            except Exception:
                pass

        return f"{obj.price} {from_currency}"
    
    def get_old_price_formatted(self, obj):
        """Форматированная старая цена."""
        if obj.old_price is not None:
            preferred_currency = self._get_preferred_currency(obj)
            from_currency = (obj.currency or 'RUB').upper()
            if preferred_currency != from_currency:
                try:
                    from .utils.currency_converter import currency_converter
                    _, _, price_with_margin = currency_converter.convert_price(
                        Decimal(obj.old_price),
                        from_currency,
                        preferred_currency,
                        apply_margin=True,
                    )
                    return f"{price_with_margin} {preferred_currency}"
                except Exception:
                    pass
            return f"{obj.old_price} {from_currency}"
        return None

    def get_images(self, obj):
        """Галерея изображений."""
        gallery = getattr(obj, "images", None)
        if not gallery:
            return []
        return ClothingProductImageSerializer(gallery.all().order_by("sort_order"), many=True).data

    # ------------------------------------------------------------------
    # Варианты
    # ------------------------------------------------------------------
    def _get_default_variant(self, obj):
        variants = getattr(obj, "variants", None)
        if not variants:
            return None
        priced = variants.filter(is_active=True, price__isnull=False).order_by("sort_order", "id").first()
        if priced:
            return priced
        return variants.filter(is_active=True).order_by("sort_order", "id").first()

    def _get_active_variant(self, obj):
        variants = getattr(obj, "variants", None)
        if not variants:
            return None
        active_slug = self.context.get("active_variant_slug")
        if active_slug:
            return variants.filter(slug=active_slug, is_active=True).first()
        return self._get_default_variant(obj)

    def get_variants(self, obj):
        variants = getattr(obj, "variants", None)
        if not variants:
            return []
        qs = variants.filter(is_active=True).order_by("sort_order", "id").prefetch_related("images")
        return ClothingVariantSerializer(qs, many=True, context={'request': self.context.get('request')}).data

    def _get_preferred_currency(self, obj) -> str:
        request = self.context.get('request')
        preferred = None
        if request:
            preferred = request.headers.get('X-Currency') or request.query_params.get('currency')
        return (preferred or obj.currency or 'RUB').upper()

    def get_default_variant_slug(self, obj):
        variant = self._get_default_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_slug(self, obj):
        variant = self._get_active_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_price(self, obj):
        variant = self._get_active_variant(obj)
        preferred_currency = self._get_preferred_currency(obj)

        if variant and variant.price is not None:
            from_currency = (variant.currency or obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_with_margin = currency_converter.convert_price(
                    Decimal(variant.price),
                    from_currency,
                    preferred_currency,
                    apply_margin=True,
                )
                return f"{price_with_margin} {preferred_currency}"
            except Exception:
                return f"{variant.price} {from_currency}"

        if obj.price is not None:
            from_currency = (obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_with_margin = currency_converter.convert_price(
                    Decimal(obj.price),
                    from_currency,
                    preferred_currency,
                    apply_margin=True,
                )
                return f"{price_with_margin} {preferred_currency}"
            except Exception:
                return f"{obj.price} {from_currency}"
        return None

    def get_active_variant_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        preferred_currency = self._get_preferred_currency(obj)
        if variant and variant.old_price is not None:
            from_currency = (variant.currency or obj.currency or 'RUB').upper()
            if preferred_currency != from_currency:
                try:
                    from .utils.currency_converter import currency_converter
                    _, _, price_with_margin = currency_converter.convert_price(
                        Decimal(variant.old_price),
                        from_currency,
                        preferred_currency,
                        apply_margin=True,
                    )
                    return f"{price_with_margin} {preferred_currency}"
                except Exception:
                    return f"{variant.old_price} {from_currency}"
            return f"{variant.old_price} {from_currency}"
        return None

    def get_active_variant_currency(self, obj):
        variant = self._get_active_variant(obj)
        if not variant:
            return None
        preferred_currency = self._get_preferred_currency(obj)
        return preferred_currency or (variant.currency if variant else None)

    def get_active_variant_stock_quantity(self, obj):
        variant = self._get_active_variant(obj)
        return variant.stock_quantity if variant else None

    def get_active_variant_main_image_url(self, obj):
        variant = self._get_active_variant(obj)
        if not variant:
            return None
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(variant, "main_image_file", None), request)
        if file_url:
            return file_url
        if variant.main_image:
            return _resolve_media_url(variant.main_image, request)
        main_img = variant.images.filter(is_main=True).first()
        if main_img:
            file_url = _resolve_file_url(getattr(main_img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(main_img.image_url, request)
        first_img = variant.images.first()
        if first_img:
            file_url = _resolve_file_url(getattr(first_img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(first_img.image_url, request)
        return None


class ShoeCategorySerializer(serializers.ModelSerializer):
    """Сериализатор для категорий обуви."""
    
    children_count = serializers.SerializerMethodField()
    gender_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'parent', 
            'gender', 'gender_display', 'shoe_type',
            'external_id', 'is_active', 'sort_order', 
            'children_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_children_count(self, obj):
        """Количество подкатегорий."""
        return obj.children.filter(is_active=True).count()
    
    def get_gender_display(self, obj):
        """Отображение значения gender."""
        if obj.gender:
            return obj.get_gender_display()
        return None


class ShoeProductSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoeProductSize
        fields = ['id', 'size', 'is_available', 'stock_quantity', 'sort_order']
        read_only_fields = ['id']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        stock = data.get('stock_quantity')
        if stock is not None and stock == 0:
            data['is_available'] = False
        return data


class ShoeProductSerializer(serializers.ModelSerializer):
    """Сериализатор для товаров обуви (краткая информация)."""
    
    category = ShoeCategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    sizes = ShoeProductSizeSerializer(many=True, read_only=True)
    variants = serializers.SerializerMethodField()
    default_variant_slug = serializers.SerializerMethodField()
    active_variant_slug = serializers.SerializerMethodField()
    active_variant_price = serializers.SerializerMethodField()
    active_variant_currency = serializers.SerializerMethodField()
    active_variant_stock_quantity = serializers.SerializerMethodField()
    active_variant_main_image_url = serializers.SerializerMethodField()
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    translations = ShoeProductTranslationSerializer(many=True, read_only=True)
    
    class Meta:
        model = ShoeProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'size', 'color', 'material',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url',
            'images', 'sizes',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'is_featured', 'created_at', 'updated_at', 'translations'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        """URL главного изображения.
        
        Сначала main_image, затем главное изображение из галереи,
        затем первое изображение.
        """
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "main_image_file", None), request)
        if file_url:
            return file_url
        if obj.main_image:
            return _resolve_media_url(obj.main_image, request)
        variant = self._get_active_variant(obj)
        if variant:
            file_url = _resolve_file_url(getattr(variant, "main_image_file", None), request)
            if file_url:
                return file_url
            if variant.main_image:
                return _resolve_media_url(variant.main_image, request)
            v_main = variant.images.filter(is_main=True).first()
            if v_main:
                file_url = _resolve_file_url(getattr(v_main, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(v_main.image_url, request)
            v_first = variant.images.first()
            if v_first:
                file_url = _resolve_file_url(getattr(v_first, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(v_first.image_url, request)
        main_img = getattr(obj, "images", None)
        if main_img:
            main_img = obj.images.filter(is_main=True).first()
            if main_img:
                file_url = _resolve_file_url(getattr(main_img, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(main_img.image_url, request)
            first_img = obj.images.first()
            if first_img:
                file_url = _resolve_file_url(getattr(first_img, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(first_img.image_url, request)
        return None
    
    def get_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return self.get_active_variant_price(obj)

        preferred_currency = self._get_preferred_currency(obj)
        if obj.price is None:
            return None

        from_currency = (obj.currency or 'RUB').upper()
        if preferred_currency != from_currency:
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_with_margin = currency_converter.convert_price(
                    Decimal(obj.price),
                    from_currency,
                    preferred_currency,
                    apply_margin=True,
                )
                return f"{price_with_margin} {preferred_currency}"
            except Exception:
                pass

        return f"{obj.price} {from_currency}"
    
    def get_old_price_formatted(self, obj):
        """Форматированная старая цена."""
        if obj.old_price is not None:
            preferred_currency = self._get_preferred_currency(obj)
            from_currency = (obj.currency or 'RUB').upper()
            if preferred_currency != from_currency:
                try:
                    from .utils.currency_converter import currency_converter
                    _, _, price_with_margin = currency_converter.convert_price(
                        Decimal(obj.old_price),
                        from_currency,
                        preferred_currency,
                        apply_margin=True,
                    )
                    return f"{price_with_margin} {preferred_currency}"
                except Exception:
                    pass
            return f"{obj.old_price} {from_currency}"
        return None

    def get_active_variant_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        preferred_currency = self._get_preferred_currency(obj)
        if variant and variant.old_price is not None:
            from_currency = (variant.currency or obj.currency or 'RUB').upper()
            if preferred_currency != from_currency:
                try:
                    from .utils.currency_converter import currency_converter
                    _, _, price_with_margin = currency_converter.convert_price(
                        Decimal(variant.old_price),
                        from_currency,
                        preferred_currency,
                        apply_margin=True,
                    )
                    return f"{price_with_margin} {preferred_currency}"
                except Exception:
                    return f"{variant.old_price} {from_currency}"
            return f"{variant.old_price} {from_currency}"
        return None

    def get_images(self, obj):
        """Галерея изображений."""
        gallery = getattr(obj, "images", None)
        if not gallery:
            return []
        return ShoeProductImageSerializer(gallery.all().order_by("sort_order"), many=True).data

    # ------------------------------------------------------------------
    # Варианты
    # ------------------------------------------------------------------
    def _get_default_variant(self, obj):
        variants = getattr(obj, "variants", None)
        if not variants:
            return None
        priced = variants.filter(is_active=True, price__isnull=False).order_by("sort_order", "id").first()
        if priced:
            return priced
        return variants.filter(is_active=True).order_by("sort_order", "id").first()

    def _get_active_variant(self, obj):
        variants = getattr(obj, "variants", None)
        if not variants:
            return None
        active_slug = self.context.get("active_variant_slug")
        if active_slug:
            return variants.filter(slug=active_slug, is_active=True).first()
        return self._get_default_variant(obj)

    def get_variants(self, obj):
        variants = getattr(obj, "variants", None)
        if not variants:
            return []
        qs = variants.filter(is_active=True).order_by("sort_order", "id").prefetch_related("images")
        return ShoeVariantSerializer(qs, many=True, context={'request': self.context.get('request')}).data

    def get_default_variant_slug(self, obj):
        variant = self._get_default_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_slug(self, obj):
        variant = self._get_active_variant(obj)
        return variant.slug if variant else None

    def _get_preferred_currency(self, obj) -> str:
        request = self.context.get('request')
        preferred = None
        if request:
            preferred = request.headers.get('X-Currency') or request.query_params.get('currency')
        return (preferred or obj.currency or 'RUB').upper()

    def get_active_variant_price(self, obj):
        variant = self._get_active_variant(obj)
        preferred_currency = self._get_preferred_currency(obj)

        if variant and variant.price is not None:
            from_currency = (variant.currency or obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_with_margin = currency_converter.convert_price(
                    Decimal(variant.price),
                    from_currency,
                    preferred_currency,
                    apply_margin=True,
                )
                return f"{price_with_margin} {preferred_currency}"
            except Exception:
                return f"{variant.price} {from_currency}"

        if obj.price is not None:
            from_currency = (obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_with_margin = currency_converter.convert_price(
                    Decimal(obj.price),
                    from_currency,
                    preferred_currency,
                    apply_margin=True,
                )
                return f"{price_with_margin} {preferred_currency}"
            except Exception:
                return f"{obj.price} {from_currency}"

        return None

    def get_active_variant_currency(self, obj):
        variant = self._get_active_variant(obj)
        if not variant:
            return None
        preferred_currency = self._get_preferred_currency(obj)
        return preferred_currency or (variant.currency if variant else None)

    def get_active_variant_stock_quantity(self, obj):
        variant = self._get_active_variant(obj)
        return variant.stock_quantity if variant else None

    def get_active_variant_main_image_url(self, obj):
        variant = self._get_active_variant(obj)
        if not variant:
            return None
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(variant, "main_image_file", None), request)
        if file_url:
            return file_url
        if variant.main_image:
            return _resolve_media_url(variant.main_image, request)
        main_img = variant.images.filter(is_main=True).first()
        if main_img:
            file_url = _resolve_file_url(getattr(main_img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(main_img.image_url, request)
        first_img = variant.images.first()
        if first_img:
            file_url = _resolve_file_url(getattr(first_img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(first_img.image_url, request)
        return None


class ShoeProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений обуви."""
    
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ShoeProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class ShoeVariantImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений варианта обуви."""
    
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ShoeVariantImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class ShoeVariantSizeSerializer(serializers.ModelSerializer):
    """Сериализатор размеров варианта обуви."""

    class Meta:
        model = ShoeVariantSize
        fields = ['id', 'size', 'is_available', 'stock_quantity', 'sort_order']
        read_only_fields = ['id']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        stock = data.get('stock_quantity')
        if stock is not None and stock == 0:
            data['is_available'] = False
        return data


class ShoeVariantSerializer(serializers.ModelSerializer):
    """Сериализатор варианта обуви."""

    images = ShoeVariantImageSerializer(many=True, read_only=True)
    sizes = ShoeVariantSizeSerializer(many=True, read_only=True)

    class Meta:
        model = ShoeVariant
        fields = [
            'id', 'slug', 'name', 'color',
            'size',  # устаревшее поле оставлено для совместимости
            'sizes',
            'price', 'old_price', 'currency',
            'is_available',
            'main_image', 'images',
            'sku', 'barcode', 'gtin', 'mpn',
            'is_active', 'sort_order',
        ]
        read_only_fields = ['id', 'slug', 'sort_order']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        preferred = None
        if request:
            preferred = request.headers.get('X-Currency') or request.query_params.get('currency')
        preferred_currency = (preferred or data.get('currency') or 'RUB').upper()

        raw_price = data.get('price')
        raw_currency = (data.get('currency') or 'RUB').upper() if data.get('currency') else 'RUB'
        if raw_price is None:
            return data

        try:
            from .utils.currency_converter import currency_converter
            _, _, price_with_margin = currency_converter.convert_price(
                Decimal(str(raw_price)),
                raw_currency,
                preferred_currency,
                apply_margin=True,
            )
            data['price'] = str(price_with_margin)
            data['currency'] = preferred_currency
        except Exception:
            data['currency'] = raw_currency
        return data


class ElectronicsCategorySerializer(serializers.ModelSerializer):
    """Сериализатор для категорий электроники."""
    
    children_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'parent', 
            'device_type', 'external_id', 'is_active', 'sort_order', 
            'children_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_children_count(self, obj):
        """Количество подкатегорий."""
        return obj.children.filter(is_active=True).count()


class ElectronicsProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений электроники."""
    
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ElectronicsProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class ElectronicsProductSerializer(serializers.ModelSerializer):
    """Сериализатор для товаров электроники (краткая информация)."""
    
    category = ElectronicsCategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    translations = ElectronicsProductTranslationSerializer(many=True, read_only=True)
    
    class Meta:
        model = ElectronicsProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'model', 'specifications', 'warranty', 'power_consumption',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url',
            'images',
            'is_featured', 'created_at', 'updated_at', 'translations'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        """URL главного изображения.
        
        Сначала main_image, затем главное изображение из галереи,
        затем первое изображение.
        """
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "main_image_file", None), request)
        if file_url:
            return file_url
        if obj.main_image:
            return _resolve_media_url(obj.main_image, request)
        gallery = getattr(obj, "images", None)
        if gallery:
            main_img = obj.images.filter(is_main=True).first()
            if main_img:
                file_url = _resolve_file_url(getattr(main_img, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(main_img.image_url, request)
            first_img = obj.images.first()
            if first_img:
                file_url = _resolve_file_url(getattr(first_img, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(first_img.image_url, request)
        return None
    
    def get_price_formatted(self, obj):
        """Форматированная цена."""
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None
    
    def get_old_price_formatted(self, obj):
        """Форматированная старая цена."""
        if obj.old_price is not None:
            request = self.context.get('request')
            preferred_currency = None
            if request:
                preferred_currency = request.headers.get('X-Currency') or request.query_params.get('currency')
            preferred_currency = (preferred_currency or obj.currency or 'RUB').upper()
            from_currency = (obj.currency or 'RUB').upper()
            if preferred_currency != from_currency:
                try:
                    from .utils.currency_converter import currency_converter
                    _, _, price_with_margin = currency_converter.convert_price(
                        Decimal(obj.old_price),
                        from_currency,
                        preferred_currency,
                        apply_margin=True,
                    )
                    return f"{price_with_margin} {preferred_currency}"
                except Exception:
                    pass
            return f"{obj.old_price} {from_currency}"
        return None

    def get_images(self, obj):
        """Галерея изображений."""
        gallery = getattr(obj, "images", None)
        if not gallery:
            return []
        return ElectronicsProductImageSerializer(gallery.all().order_by("sort_order"), many=True).data


# ============================================================================
# СЕРИАЛИЗАТОРЫ ДЛЯ МЕБЕЛИ
# ============================================================================

class FurnitureVariantImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений варианта мебели."""
    
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = FurnitureVariantImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class FurnitureVariantSerializer(serializers.ModelSerializer):
    """Сериализатор для вариантов мебели."""

    images = serializers.SerializerMethodField()

    class Meta:
        model = FurnitureVariant
        fields = [
            'id', 'name', 'slug', 'color',
            'price', 'old_price', 'currency',
            'is_available', 'stock_quantity',
            'main_image', 'images',
            'sku', 'barcode', 'gtin', 'mpn',
            'is_active', 'sort_order',
        ]
        read_only_fields = ['id', 'slug', 'sort_order']

    def get_images(self, obj):
        """Галерея изображений варианта."""
        gallery = getattr(obj, "images", None)
        if not gallery:
            return []
        return FurnitureVariantImageSerializer(gallery.all().order_by("sort_order"), many=True).data


class FurnitureProductSerializer(serializers.ModelSerializer):
    """Сериализатор для товаров мебели (краткая информация)."""
    
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()
    default_variant_slug = serializers.SerializerMethodField()
    active_variant_slug = serializers.SerializerMethodField()
    active_variant_price = serializers.SerializerMethodField()
    active_variant_currency = serializers.SerializerMethodField()
    active_variant_stock_quantity = serializers.SerializerMethodField()
    active_variant_main_image_url = serializers.SerializerMethodField()
    translations = FurnitureProductTranslationSerializer(many=True, read_only=True)
    
    class Meta:
        model = FurnitureProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'material', 'furniture_type', 'dimensions',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url',
            'images',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'is_featured', 'created_at', 'updated_at', 'translations'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        """URL главного изображения."""
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "main_image_file", None), request)
        if file_url:
            return file_url
        if obj.main_image:
            return _resolve_media_url(obj.main_image, request)
        # Пробуем активный вариант
        variant = self._get_active_variant(obj)
        if variant:
            file_url = _resolve_file_url(getattr(variant, "main_image_file", None), request)
            if file_url:
                return file_url
            if variant.main_image:
                return _resolve_media_url(variant.main_image, request)
            v_main = variant.images.filter(is_main=True).first()
            if v_main:
                file_url = _resolve_file_url(getattr(v_main, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(v_main.image_url, request)
            v_first = variant.images.first()
            if v_first:
                file_url = _resolve_file_url(getattr(v_first, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(v_first.image_url, request)
        return None
    
    def get_price_formatted(self, obj):
        """Форматированная цена."""
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return f"{variant.price} {variant.currency}"
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None
    
    def get_old_price_formatted(self, obj):
        """Форматированная старая цена."""
        variant = self._get_active_variant(obj)
        preferred_currency = self._get_preferred_currency(obj)
        if variant and variant.old_price is not None:
            from_currency = (variant.currency or obj.currency or 'RUB').upper()
            if preferred_currency != from_currency:
                try:
                    from .utils.currency_converter import currency_converter
                    _, _, price_with_margin = currency_converter.convert_price(
                        Decimal(variant.old_price),
                        from_currency,
                        preferred_currency,
                        apply_margin=True,
                    )
                    return f"{price_with_margin} {preferred_currency}"
                except Exception:
                    pass
            return f"{variant.old_price} {from_currency}"
        if obj.old_price is not None:
            from_currency = (obj.currency or 'RUB').upper()
            if preferred_currency != from_currency:
                try:
                    from .utils.currency_converter import currency_converter
                    _, _, price_with_margin = currency_converter.convert_price(
                        Decimal(obj.old_price),
                        from_currency,
                        preferred_currency,
                        apply_margin=True,
                    )
                    return f"{price_with_margin} {preferred_currency}"
                except Exception:
                    pass
            return f"{obj.old_price} {from_currency}"
        return None

    def get_active_variant_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        preferred_currency = self._get_preferred_currency(obj)
        if variant and variant.old_price is not None:
            from_currency = (variant.currency or obj.currency or 'RUB').upper()
            if preferred_currency != from_currency:
                try:
                    from .utils.currency_converter import currency_converter
                    _, _, price_with_margin = currency_converter.convert_price(
                        Decimal(variant.old_price),
                        from_currency,
                        preferred_currency,
                        apply_margin=True,
                    )
                    return f"{price_with_margin} {preferred_currency}"
                except Exception:
                    return f"{variant.old_price} {from_currency}"
            return f"{variant.old_price} {from_currency}"
        return None

    def _get_preferred_currency(self, obj) -> str:
        request = self.context.get('request')
        preferred = None
        if request:
            preferred = request.headers.get('X-Currency') or request.query_params.get('currency')
        return (preferred or obj.currency or 'RUB').upper()

    def get_images(self, obj):
        """Галерея изображений."""
        variant = self._get_active_variant(obj)
        if variant:
            return FurnitureVariantImageSerializer(variant.images.all().order_by("sort_order"), many=True).data
        return []

    def _get_default_variant(self, obj):
        variants = getattr(obj, "variants", None)
        if not variants:
            return None
        return variants.filter(is_active=True).order_by("sort_order", "id").first()

    def _get_active_variant(self, obj):
        variants = getattr(obj, "variants", None)
        if not variants:
            return None
        active_slug = self.context.get("active_variant_slug")
        if active_slug:
            return variants.filter(slug=active_slug, is_active=True).first()
        return self._get_default_variant(obj)

    def get_variants(self, obj):
        variants = getattr(obj, "variants", None)
        if not variants:
            return []
        qs = variants.filter(is_active=True).order_by("sort_order", "id").prefetch_related("images")
        return FurnitureVariantSerializer(qs, many=True).data

    def get_default_variant_slug(self, obj):
        variant = self._get_default_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_slug(self, obj):
        variant = self._get_active_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_price(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return f"{variant.price} {variant.currency}"
        return None

    def get_active_variant_currency(self, obj):
        variant = self._get_active_variant(obj)
        return variant.currency if variant else None

    def get_active_variant_stock_quantity(self, obj):
        variant = self._get_active_variant(obj)
        return variant.stock_quantity if variant else None

    def get_active_variant_main_image_url(self, obj):
        variant = self._get_active_variant(obj)
        if not variant:
            return None
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(variant, "main_image_file", None), request)
        if file_url:
            return file_url
        if variant.main_image:
            return _resolve_media_url(variant.main_image, request)
        main_img = variant.images.filter(is_main=True).first()
        if main_img:
            file_url = _resolve_file_url(getattr(main_img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(main_img.image_url, request)
        first_img = variant.images.first()
        if first_img:
            file_url = _resolve_file_url(getattr(first_img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(first_img.image_url, request)
        return None


# ============================================================================
# СЕРИАЛИЗАТОРЫ ДЛЯ УСЛУГ
# ============================================================================

class ServiceSerializer(serializers.ModelSerializer):
    """Сериализатор для услуг."""
    
    category = CategorySerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    translations = ServiceTranslationSerializer(many=True, read_only=True)
    
    class Meta:
        model = Service
        fields = [
            'id', 'name', 'slug', 'description', 'category',
            'price', 'price_formatted', 'currency',
            'duration', 'service_type',
            'main_image', 'main_image_url',
            'is_active', 'is_featured', 'created_at', 'updated_at', 'translations'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        """URL главного изображения."""
        return obj.main_image if obj.main_image else None
    
    def get_price_formatted(self, obj):
        """Форматированная цена."""
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None


class BannerMediaSerializer(serializers.ModelSerializer):
    """Сериализатор для медиа-файлов баннера."""
    
    content_url = serializers.SerializerMethodField()
    content_mime_type = serializers.SerializerMethodField()
    
    class Meta:
        model = BannerMedia
        fields = [
            'id', 'content_type', 'content_url', 'content_mime_type', 'sort_order', 
            'link_url', 'title', 'description', 'link_text'
        ]
        read_only_fields = ['id', 'content_url', 'content_mime_type']
    
    def get_content_url(self, obj):
        """Получить URL контента медиа-файла."""
        request = self.context.get('request')
        content_url = obj.get_content_url()
        
        if not content_url:
            return ''
        
        # Если это внешний URL, возвращаем как есть
        if content_url.startswith('http://') or content_url.startswith('https://'):
            return content_url
        
        # Если это локальный файл, преобразуем в абсолютный URL
        if request:
            absolute_url = request.build_absolute_uri(content_url)
            # Заменяем внутренний Docker хост на внешний, если нужно
            if 'backend:8000' in absolute_url or 'localhost:8000' not in absolute_url:
                host = request.get_host()
                scheme = 'https' if request.is_secure() else 'http'
                if 'localhost' not in host and '127.0.0.1' not in host:
                    return f"{scheme}://{host}{content_url}"
                return f"http://localhost:8000{content_url}"
            return absolute_url
        
        return content_url
    
    def get_content_mime_type(self, obj):
        """Получить MIME-тип контента."""
        return obj.get_content_type_for_html()


class BannerSerializer(serializers.ModelSerializer):
    """Сериализатор для баннеров."""
    
    media_files = serializers.SerializerMethodField()
    
    class Meta:
        model = Banner
        fields = [
            'id', 'title', 'description', 'position', 'link_url', 'link_text', 
            'is_active', 'sort_order', 'media_files'
        ]

    def get_media_files(self, obj):
        """Получить отсортированные медиа-файлы баннера."""
        media = obj.media_files.all().order_by('sort_order')
        return BannerMediaSerializer(media, many=True, context=self.context).data
