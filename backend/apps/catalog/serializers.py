"""Сериализаторы для API каталога товаров."""

from rest_framework import serializers
from .models import (
    Category, Brand, Product, ProductImage, ProductAttribute, PriceHistory, Favorite,
    ClothingCategory, ClothingProduct, ClothingProductImage, ClothingVariant, ClothingVariantImage, ClothingVariantSize,
    ShoeCategory, ShoeProduct, ShoeProductImage, ShoeVariant, ShoeVariantImage, ShoeVariantSize,
    ElectronicsCategory, ElectronicsProduct, ElectronicsProductImage,
    Banner, BannerMedia
)


class CategorySerializer(serializers.ModelSerializer):
    """Сериализатор для категорий."""
    
    children_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'parent', 
            'external_id', 'is_active', 'sort_order', 
            'children_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_children_count(self, obj):
        """Количество подкатегорий."""
        return obj.children.filter(is_active=True).count()


class BrandSerializer(serializers.ModelSerializer):
    """Сериализатор для брендов."""
    
    products_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Brand
        fields = [
            'id', 'name', 'slug', 'description', 'logo', 'website',
            'external_id', 'is_active', 'products_count', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_products_count(self, obj):
        """Количество товаров бренда."""
        return obj.products.filter(is_active=True).count()


class ProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор для изображений товара."""
    
    class Meta:
        model = ProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']


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


class ProductSerializer(serializers.ModelSerializer):
    """Сериализатор для товаров (краткая информация)."""
    
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'name_en', 'slug', 'description', 'description_en',
            'category', 'brand',
            'product_type',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'converted_price_rub', 'converted_price_usd',
            'final_price_rub', 'final_price_usd', 'margin_percent_applied',
            'availability_status', 'is_available', 'stock_quantity',
            'min_order_quantity', 'pack_quantity',
            'country_of_origin', 'gtin', 'mpn',
            'weight_value', 'weight_unit', 'length', 'width', 'height', 'dimensions_unit',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
            'main_image_url',
            'is_featured', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        """URL главного изображения."""
        # Сначала проверяем main_image
        if obj.main_image:
            return obj.main_image
        
        # Затем ищем главное изображение в связанных изображениях
        main_img = obj.images.filter(is_main=True).first()
        if main_img:
            return main_img.image_url
        
        # Если нет главного, берем первое изображение
        first_img = obj.images.first()
        if first_img:
            return first_img.image_url
        
        # Если изображений нет, возвращаем None
        return None
    
    def get_price_formatted(self, obj):
        """Форматированная цена."""
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None
    
    def get_old_price_formatted(self, obj):
        """Форматированная старая цена."""
        if obj.old_price is not None:
            return f"{obj.old_price} {obj.currency}"
        return None


class ProductDetailSerializer(ProductSerializer):
    """Сериализатор для товаров (детальная информация)."""
    
    images = ProductImageSerializer(many=True, read_only=True)
    attributes = ProductAttributeSerializer(many=True, read_only=True)
    price_history = serializers.SerializerMethodField()
    
    class Meta(ProductSerializer.Meta):
        fields = ProductSerializer.Meta.fields + [
            'images', 'attributes', 'price_history', 'external_id',
            'external_url', 'sku', 'barcode', 'last_synced_at'
        ]
    
    def get_price_history(self, obj):
        """История цен (последние 10 записей)."""
        history = obj.price_history.all()[:10]
        return PriceHistorySerializer(history, many=True).data


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
        """Форматированная цена."""
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
        
        # Определяем тип товара по модели
        product_type = 'medicines'  # По умолчанию
        if isinstance(product, ClothingProduct):
            product_type = 'clothing'
            product_data = ClothingProductSerializer(product).data
        elif isinstance(product, ShoeProduct):
            product_type = 'shoes'
            product_data = ShoeProductSerializer(product).data
        elif isinstance(product, ElectronicsProduct):
            product_type = 'electronics'
            product_data = ElectronicsProductSerializer(product).data
        elif isinstance(product, Product):
            # Для Product нужно определить подтип по категории или другим признакам
            # Пока используем 'medicines' как базовый тип
            product_type = 'medicines'
            product_data = ProductSerializer(product).data
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
        product_type = attrs.get('product_type', 'medicines')
        
        # Маппинг типов товаров на модели
        from .models import Product, ClothingProduct, ShoeProduct, ElectronicsProduct
        
        PRODUCT_MODEL_MAP = {
            'medicines': Product,
            'supplements': Product,
            'medical_equipment': Product,
            'furniture': Product,
            'tableware': Product,
            'accessories': Product,
            'jewelry': Product,
            'underwear': Product,
            'headwear': Product,
            'clothing': ClothingProduct,
            'shoes': ShoeProduct,
            'electronics': ElectronicsProduct,
        }
        
        model_class = PRODUCT_MODEL_MAP.get(product_type, Product)
        
        try:
            product = model_class.objects.get(id=product_id)
            # Проверяем is_active, если поле существует
            if hasattr(product, 'is_active') and not product.is_active:
                raise serializers.ValidationError({"product_id": "Товар неактивен"})
        except model_class.DoesNotExist:
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
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)
    
    class Meta:
        model = ClothingCategory
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


class ClothingProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений одежды."""

    class Meta:
        model = ClothingProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']


class ClothingVariantImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений варианта одежды."""

    class Meta:
        model = ClothingVariantImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']


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


class ClothingProductSerializer(serializers.ModelSerializer):
    """Сериализатор для товаров одежды (краткая информация)."""
    
    category = ClothingCategorySerializer(read_only=True)
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
    
    class Meta:
        model = ClothingProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'size', 'color', 'material', 'season',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url',
            'images',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url',
            'is_featured', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        """URL главного изображения.
        
        Сначала main_image, затем главное изображение из галереи,
        затем первое изображение.
        """
        if obj.main_image:
            return obj.main_image
        # Пробуем активный вариант
        variant = self._get_active_variant(obj)
        if variant:
            if variant.main_image:
                return variant.main_image
            v_main = variant.images.filter(is_main=True).first()
            if v_main:
                return v_main.image_url
            v_first = variant.images.first()
            if v_first:
                return v_first.image_url
        gallery = getattr(obj, "images", None)
        if gallery:
            main_img = obj.images.filter(is_main=True).first()
            if main_img:
                return main_img.image_url
            first_img = obj.images.first()
            if first_img:
                return first_img.image_url
        return None
    
    def get_price_formatted(self, obj):
        """Форматированная цена."""
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None
    
    def get_old_price_formatted(self, obj):
        """Форматированная старая цена."""
        if obj.old_price is not None:
            return f"{obj.old_price} {obj.currency}"
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
        return ClothingVariantSerializer(qs, many=True).data

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
        if variant.main_image:
            return variant.main_image
        main_img = variant.images.filter(is_main=True).first()
        if main_img:
            return main_img.image_url
        first_img = variant.images.first()
        if first_img:
            return first_img.image_url
        return None


class ShoeCategorySerializer(serializers.ModelSerializer):
    """Сериализатор для категорий обуви."""
    
    children_count = serializers.SerializerMethodField()
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)
    
    class Meta:
        model = ShoeCategory
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


class ShoeProductSerializer(serializers.ModelSerializer):
    """Сериализатор для товаров обуви (краткая информация)."""
    
    category = ShoeCategorySerializer(read_only=True)
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
    
    class Meta:
        model = ShoeProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'size', 'color', 'material',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url',
            'images',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url',
            'is_featured', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        """URL главного изображения.
        
        Сначала main_image, затем главное изображение из галереи,
        затем первое изображение.
        """
        if obj.main_image:
            return obj.main_image
        variant = self._get_active_variant(obj)
        if variant:
            if variant.main_image:
                return variant.main_image
            v_main = variant.images.filter(is_main=True).first()
            if v_main:
                return v_main.image_url
            v_first = variant.images.first()
            if v_first:
                return v_first.image_url
        main_img = getattr(obj, "images", None)
        if main_img:
            main_img = obj.images.filter(is_main=True).first()
            if main_img:
                return main_img.image_url
            first_img = obj.images.first()
            if first_img:
                return first_img.image_url
        return None
    
    def get_price_formatted(self, obj):
        """Форматированная цена."""
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None
    
    def get_old_price_formatted(self, obj):
        """Форматированная старая цена."""
        if obj.old_price is not None:
            return f"{obj.old_price} {obj.currency}"
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
        return ShoeVariantSerializer(qs, many=True).data

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
        if variant.main_image:
            return variant.main_image
        main_img = variant.images.filter(is_main=True).first()
        if main_img:
            return main_img.image_url
        first_img = variant.images.first()
        if first_img:
            return first_img.image_url
        return None


class ShoeProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений обуви."""

    class Meta:
        model = ShoeProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']


class ShoeVariantImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений варианта обуви."""

    class Meta:
        model = ShoeVariantImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']


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



class ElectronicsCategorySerializer(serializers.ModelSerializer):
    """Сериализатор для категорий электроники."""
    
    children_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ElectronicsCategory
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

    class Meta:
        model = ElectronicsProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']


class ElectronicsProductSerializer(serializers.ModelSerializer):
    """Сериализатор для товаров электроники (краткая информация)."""
    
    category = ElectronicsCategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    
    class Meta:
        model = ElectronicsProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'model', 'specifications', 'warranty', 'power_consumption',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url',
            'images',
            'is_featured', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        """URL главного изображения.
        
        Сначала main_image, затем главное изображение из галереи,
        затем первое изображение.
        """
        if obj.main_image:
            return obj.main_image
        gallery = getattr(obj, "images", None)
        if gallery:
            main_img = obj.images.filter(is_main=True).first()
            if main_img:
                return main_img.image_url
            first_img = obj.images.first()
            if first_img:
                return first_img.image_url
        return None
    
    def get_price_formatted(self, obj):
        """Форматированная цена."""
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None
    
    def get_old_price_formatted(self, obj):
        """Форматированная старая цена."""
        if obj.old_price is not None:
            return f"{obj.old_price} {obj.currency}"
        return None

    def get_images(self, obj):
        """Галерея изображений."""
        gallery = getattr(obj, "images", None)
        if not gallery:
            return []
        return ElectronicsProductImageSerializer(gallery.all().order_by("sort_order"), many=True).data


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
