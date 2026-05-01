"""Сериализаторы для API каталога товаров."""

from urllib.parse import quote, urlparse
import re
import logging
from decimal import Decimal
from django.conf import settings
from django.db.models import Count
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)
from .models import (
    Category, CategoryTranslation, Brand, BrandTranslation, Product, ProductTranslation, ProductImage, PriceHistory, Favorite,
    ClothingProduct, ClothingProductTranslation, ClothingProductImage, ClothingVariant, ClothingVariantImage, ClothingVariantSize, ClothingProductSize,
    ShoeProduct, ShoeProductTranslation, ShoeProductImage, ShoeVariant, ShoeVariantImage, ShoeVariantSize, ShoeProductSize,
    JewelryProduct, JewelryProductTranslation, JewelryProductImage, JewelryVariant, JewelryVariantImage, JewelryVariantSize,
    ElectronicsProduct, ElectronicsProductTranslation, ElectronicsProductImage,
    FurnitureProduct, FurnitureProductTranslation, FurnitureProductImage, FurnitureVariant, FurnitureVariantImage,
    BookProduct, BookProductTranslation, BookProductImage,
    PerfumeryProduct, PerfumeryProductTranslation, PerfumeryProductImage, PerfumeryVariant, PerfumeryVariantImage,
    MedicineProduct, MedicineProductTranslation, MedicineProductImage,
    SupplementProduct, SupplementProductTranslation, SupplementProductImage,
    MedicalEquipmentProduct, MedicalEquipmentProductTranslation, MedicalEquipmentProductImage,
    TablewareProduct, TablewareProductTranslation, TablewareProductImage,
    AccessoryProduct, AccessoryProductTranslation, AccessoryProductImage,
    IncenseProduct, IncenseProductTranslation, IncenseProductImage,
    Service, ServiceTranslation, ServiceImage, ServicePrice, ServiceAttribute,
    GlobalAttributeKey, ProductAttributeValue,
    Banner, BannerMedia, Author, ProductAuthor, ProductGenre, BookVariant, BookVariantSize, BookVariantImage,
    SportsProduct, SportsProductTranslation, SportsProductImage, SportsVariant, SportsVariantImage,
    AutoPartProduct, AutoPartProductTranslation, AutoPartProductImage, AutoPartVariant, AutoPartVariantImage,
)
from .seo_defaults import resolve_book_seo_value
from .utils.media_path import normalize_duplicated_media_path
from .utils.storage_paths import detect_media_type
from .utils.variant_titles import build_variant_display_title

TRANSLATION_SEO_FIELDS = [
    'meta_title',
    'meta_description',
    'meta_keywords',
    'og_title',
    'og_description',
]


def _request_lang(request) -> str:
    return getattr(request, 'LANGUAGE_CODE', 'ru') if request else 'ru'


class _LocalizedSeoMethodsMixin:
    def _resolve_localized_seo(self, obj, field_name: str):
        return resolve_book_seo_value(obj, field_name, lang=_request_lang(self.context.get('request')))

    def get_meta_title(self, obj):
        return self._resolve_localized_seo(obj, "meta_title")

    def get_meta_description(self, obj):
        return self._resolve_localized_seo(obj, "meta_description")

    def get_meta_keywords(self, obj):
        return self._resolve_localized_seo(obj, "meta_keywords")

    def get_og_title(self, obj):
        return self._resolve_localized_seo(obj, "og_title")

    def get_og_description(self, obj):
        return self._resolve_localized_seo(obj, "og_description")

    def get_og_image_url(self, obj):
        return self._resolve_localized_seo(obj, "og_image_url")


def _r2_proxy_url(absolute_url, request):
    """Если URL ведёт на R2 или CDN проекта, вернуть URL прокси через /api/catalog/proxy-media/."""
    if not absolute_url or not absolute_url.startswith('http'):
        return None
    
    r2_config = getattr(settings, 'R2_CONFIG', {})
    r2_public = (r2_config.get('public_url', None) or getattr(settings, 'R2_PUBLIC_URL', '') or '').rstrip('/')
    project_cdn = 'https://cdn.mudaroba.com'  # CNAME для R2
    
    is_r2 = r2_public and absolute_url.startswith(r2_public)
    is_project_cdn = absolute_url.startswith(project_cdn)
    
    if not (is_r2 or is_project_cdn):
        return None

    try:
        # Извлекаем путь относительно публичного URL
        prefix = r2_public if is_r2 else project_cdn
        path = absolute_url[len(prefix):].lstrip('/')
        if not path:
            return None
            
        path = normalize_duplicated_media_path(path)
        return f"/api/catalog/proxy-media/?path={quote(path, safe='')}"
    except Exception:
        return None


def _resolve_media_url(value, request):
    if not value:
        return None
    # Уже прокси-URL — не добавлять /media/
    if value.startswith('/api/'):
        return value

    # Проверка на видео — для них ОБЯЗАТЕЛЬНО используем proxy-media (поддерживает Range).
    # Пути карточек категорий/брендов и галерей: .../videos/... — на CDN имя без суффикса .mp4.
    path_lower = value.lower().split('?')[0]
    video_exts = ('.mp4', '.webm', '.mov', '.m4v', '.avi', '.mkv')
    is_video = any(path_lower.endswith(ext) for ext in video_exts)
    if not is_video and '/videos/' in path_lower:
        if 'marketing/cards/' in path_lower or '/products/' in path_lower:
            is_video = True

    if is_video:
        proxy = _r2_proxy_url(value, request)
        if proxy:
            return proxy
        # Если это внешнее видео не из R2, но требует проксирования (маловероятно для видео, но на всякий случай)
        if value.startswith('http'):
             return value

    if 'instagram.f' in value or 'cdninstagram.com' in value:
        return f"/api/catalog/proxy-image/?url={quote(value)}"
    
    # Прокси для внешних CDN (устраняет CORS/EncodingError на Flutter Web)
    # ВАЖНО: Если это видео с cdn.mudaroba.com, оно уже должно было уйти выше в proxy-media
    if value.startswith('http') and ('cdn.mudaroba.com' in value or 'r2.dev' in value):
        proxy = _r2_proxy_url(value, request)
        if proxy:
            return proxy
        return f"/api/catalog/proxy-image/?url={quote(value)}"

    # Относительный ключ в бакете (без https): /media/ на проде часто без Range — <video> не стримится.
    if not value.startswith('http'):
        p = value.lstrip('/')
        if '..' in p:
            return None
        if is_video:
            path_norm = normalize_duplicated_media_path(p)
            return f"/api/catalog/proxy-media/?path={quote(path_norm, safe='')}"
        return f"/media/{p}"
    
    proxy = _r2_proxy_url(value, request)
    if proxy:
        return proxy
    return value


def _get_variant_applied_ai_draft(variant):
    external_data = getattr(variant, "external_data", None)
    if not isinstance(external_data, dict):
        return {}
    payload = external_data.get("ai_variant_applied")
    if not isinstance(payload, dict):
        return {}
    draft = payload.get("draft")
    return draft if isinstance(draft, dict) else {}


def _get_variant_draft_title(variant, locale: str) -> str:
    draft = _get_variant_applied_ai_draft(variant)
    if draft:
        bucket = draft.get(locale) or {}
        generated = str(bucket.get("generated_title") or "").strip()
        if generated:
            return generated
    return build_variant_display_title(variant, locale)


def _get_variant_draft_description(variant, locale: str) -> str:
    draft = _get_variant_applied_ai_draft(variant)
    if not draft:
        return ""
    bucket = draft.get(locale) or {}
    return str(bucket.get("generated_description") or "").strip()


def _get_variant_localized_description(variant, locale: str) -> str:
    localized = _get_variant_draft_description(variant, locale)
    if localized:
        return localized
    product = getattr(variant, "product", None)
    if not product:
        return ""
    if locale == "en":
        translations = getattr(product, "translations", None)
        if hasattr(translations, "filter"):
            trans = translations.filter(locale="en").first()
            if trans and trans.description:
                return trans.description
    return getattr(product, "description", "") or ""


def _resolve_file_url(file_field, request):
    if not file_field:
        return None
    if hasattr(file_field, "url"):
        raw_url = file_field.url
        if request:
            raw_url = request.build_absolute_uri(raw_url)
        proxy = _r2_proxy_url(raw_url, request)
        if proxy:
            return proxy
        return raw_url
    return None


def _resolve_file_url_if_stored(file_field, request):
    """Как _resolve_file_url, но только если объект реально есть в storage (иначе 404 на proxy-media).

    Ключ в БД может быть без R2_PREFIX (products/...), а объект в бакете — с префиксом (dev/products/...);
    proxy-media перебирает кандидатов, здесь делаем то же самое.
    """
    if not file_field or not getattr(file_field, "name", None):
        return None
    from django.core.files.storage import default_storage

    from apps.catalog.utils.media_path import resolve_existing_media_storage_key

    try:
        resolved_key = resolve_existing_media_storage_key(file_field.name)
        if not resolved_key:
            return None
        raw_url = default_storage.url(resolved_key)
    except Exception:
        return None
    if request:
        raw_url = request.build_absolute_uri(raw_url)
    proxy = _r2_proxy_url(raw_url, request)
    if proxy:
        return proxy
    return raw_url


def _resolve_video_file_url(file_field, request):
    """URL главного видеофайла: сначала только если объект есть в storage (как proxy-media), иначе как в корзине.

    На проде ключ в БД и префикс в бакете иногда расходятся — if_stored даёт None, тогда всё равно отдаём
    URL по полю (иначе витрина без видео, а корзина с тем же товаром показывает ролик).
    """
    if not file_field or not getattr(file_field, "name", None):
        return None
    u = _resolve_file_url_if_stored(file_field, request)
    if u:
        return u
    return _resolve_file_url(file_field, request)


def serialize_product_for_card(product, request):
    """
    Сериализует товар для карточки с учётом типа (shoes, clothing и т.д.).
    Используется в recommendations API, чтобы возвращать active_variant_price,
    main_image_url и другие поля, которые ProductSerializer не предоставляет
    для товаров с вариантами.
    """
    ctx = {'request': request}
    if isinstance(product, ClothingProduct):
        return ClothingProductSerializer(product, context=ctx).data
    if isinstance(product, ShoeProduct):
        return ShoeProductSerializer(product, context=ctx).data
    if isinstance(product, ElectronicsProduct):
        return ElectronicsProductSerializer(product, context=ctx).data
    if isinstance(product, FurnitureProduct):
        return FurnitureProductSerializer(product, context=ctx).data
    if isinstance(product, JewelryProduct):
        return JewelryProductSerializer(product, context=ctx).data
    # Shadow Product с книгами: тот же payload, что в списке /catalog/books/ (video_url, варианты, …)
    pt = (getattr(product, 'product_type', None) or '').strip().lower().replace('-', '_')
    if pt == 'books':
        book = getattr(product, 'book_item', None)
        if book:
            return BookProductSerializer(book, context=ctx).data
    return ProductSerializer(product, context=ctx).data


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
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class FurnitureProductTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов товаров мебели."""
    
    class Meta:
        model = FurnitureProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class ServiceTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов услуг."""
    
    class Meta:
        model = ServiceTranslation
        fields = ['locale', 'name', 'description']


class ClothingProductTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов товаров одежды."""
    
    class Meta:
        model = ClothingProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class ShoeProductTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов товаров обуви."""
    
    class Meta:
        model = ShoeProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class ElectronicsProductTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов товаров электроники."""
    
    class Meta:
        model = ElectronicsProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


def _get_category_ids_with_descendants(slugs: list) -> set:
    """Возвращает set ID категорий по slug, включая все дочерние (подкатегории)."""
    if not slugs:
        return set()
    slugs = [s.strip() for s in slugs if s.strip()]
    if not slugs:
        return set()
    cats = Category.objects.filter(slug__in=slugs, is_active=True).values_list('id', flat=True)
    current_ids = list(cats)
    all_ids = set(current_ids)
    while current_ids:
        children = list(Category.objects.filter(
            parent_id__in=current_ids, is_active=True
        ).values_list('id', flat=True))
        current_ids = [c for c in children if c not in all_ids]
        all_ids.update(current_ids)
    return all_ids


class CategorySerializer(serializers.ModelSerializer):
    """Сериализатор для категорий."""
    
    name = serializers.SerializerMethodField()
    children_count = serializers.SerializerMethodField()
    products_count = serializers.SerializerMethodField()
    card_media_url = serializers.SerializerMethodField()
    category_type = serializers.SerializerMethodField()
    category_type_slug = serializers.SerializerMethodField()
    gender_display = serializers.SerializerMethodField()
    translations = CategoryTranslationSerializer(many=True, read_only=True)
    ancestors = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'card_media_url', 'parent', 'ancestors',
            'external_id', 'is_active', 'sort_order',
            'children_count', 'products_count', 'created_at', 'updated_at',
            'category_type', 'category_type_slug', 'translations',
            'gender', 'gender_display', 'clothing_type', 'device_type',
            'meta_title', 'meta_description', 'meta_keywords', 'og_title', 'og_description', 'og_image_url',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def to_representation(self, instance):
        """Скрытие описания для главной страницы."""
        ret = super().to_representation(instance)
        if self.context.get('hide_description'):
            ret['description'] = None
        return ret

    def get_name(self, obj):
        """Возвращает название категории на языке запроса (X-Language / Accept-Language)."""
        from django.utils import translation
        request = self.context.get('request')
        lang = getattr(request, 'LANGUAGE_CODE', None) if request else None
        if not lang:
            lang = translation.get_language() or 'ru'
        # Ищем перевод для текущего языка
        if hasattr(obj, '_prefetched_objects_cache') and 'translations' in obj._prefetched_objects_cache:
            trans_list = obj._prefetched_objects_cache['translations']
        else:
            trans_list = list(obj.translations.all())
        for t in trans_list:
            if t.locale == lang:
                return t.name or obj.name
        return obj.name
    
    def get_children_count(self, obj):
        """Количество подкатегорий."""
        if self.context.get('hide_counts'):
            return 0
        return obj.children.filter(is_active=True).count()

    def get_products_count(self, obj):
        """Количество товаров в категории и всех её подкатегориях."""
        if self.context.get('hide_counts'):
            return 0
        cat_ids = _get_category_ids_with_descendants([obj.slug])
        if not cat_ids:
            return 0
        return Product.objects.filter(category_id__in=cat_ids, is_active=True).count()

    def get_card_media_url(self, obj):
        """URL медиа-файла карточки категории. Прокси для R2 — устраняет CORS/SSL на мобильном."""
        url = obj.get_card_media_url()
        if not url:
            return None
        resolved = _resolve_media_url(url, self.context.get('request'))
        if resolved:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(resolved)
            return resolved
        if url.startswith('/'):
            return url
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

    def get_ancestors(self, obj):
        """Возвращает список родительских категорий (снизу вверх) с именами и слагами."""
        from django.utils import translation
        request = self.context.get('request')
        lang = getattr(request, 'LANGUAGE_CODE', None) if request else None
        if not lang:
            lang = translation.get_language() or 'ru'
            
        ancestors_list = []
        curr = obj.parent
        while curr:
            name = curr.name
            # Попытка локализации родителя
            if hasattr(curr, 'translations'):
                try:
                    # Поиск в префетченной коллекции если возможно, иначе запрос
                    t = curr.translations.filter(locale=lang).first()
                    if t and t.name:
                        name = t.name
                except Exception:
                    pass
            
            ancestors_list.append({
                'id': curr.id,
                'name': name,
                'slug': curr.slug
            })
            curr = curr.parent
        
        # Инвертируем, чтобы было от корня к текущей
        ancestors_list.reverse()
        return ancestors_list


class BrandSerializer(serializers.ModelSerializer):
    """Сериализатор для брендов."""
    
    products_count = serializers.SerializerMethodField()
    logo = serializers.SerializerMethodField()
    card_media_url = serializers.SerializerMethodField()
    primary_category_slug = serializers.SerializerMethodField()
    translations = BrandTranslationSerializer(many=True, read_only=True)
    
    class Meta:
        model = Brand
        fields = [
            'id', 'name', 'slug', 'description', 'logo', 'website', 'card_media_url',
            'primary_category_slug', 'category_slugs',
            'external_id', 'is_active', 'products_count', 
            'translations',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def to_representation(self, instance):
        """Скрытие счетчика товаров для главной страницы."""
        ret = super().to_representation(instance)
        if self.context.get('hide_counts'):
            ret['products_count'] = 0
        return ret
    
    def get_products_count(self, obj):
        """Количество товаров бренда в наличии (точное с учетом доменов)."""
        # Если в контексте указано скрыть счетчики (например, для главной страницы),
        # выходим немедленно, чтобы не нагружать БД тяжелыми запросами count().
        if self.context.get('hide_counts'):
            return None

        model_map = {
            'jewelry': JewelryProduct,
            'clothing': ClothingProduct,
            'shoes': ShoeProduct,
            'electronics': ElectronicsProduct,
            'furniture': FurnitureProduct,
            'underwear': ClothingProduct,
            'headwear': ClothingProduct,
        }
        # Фильтр по наличию
        available_filter = {'is_active': True, 'is_available': True}

        primary_slug = obj.primary_category_slug
        if primary_slug:
            # 1. Если задана специализация бренда, считаем только её
            normalized_type = primary_slug.replace('-', '_')
            if primary_slug in model_map:
                return model_map[primary_slug].objects.filter(brand=obj, **available_filter).count()
            if normalized_type in model_map:
                return model_map[normalized_type].objects.filter(brand=obj, **available_filter).count()

            # Если для типа нет доменной модели (например, medicines), считаем в базе
            return obj.products.filter(is_active=True, is_available=True, product_type=normalized_type).count()

        # 2. Если специализация не задана, суммируем все легитимные товары в наличии
        count = JewelryProduct.objects.filter(brand=obj, **available_filter).count()
        count += ClothingProduct.objects.filter(brand=obj, **available_filter).count()
        count += ShoeProduct.objects.filter(brand=obj, **available_filter).count()
        count += ElectronicsProduct.objects.filter(brand=obj, **available_filter).count()
        count += FurnitureProduct.objects.filter(brand=obj, **available_filter).count()

        # Добавляем легаси-типы, исключая те, что уже должны быть в доменах
        refactored_types = ['jewelry', 'clothing', 'shoes', 'electronics', 'furniture', 'underwear', 'headwear']
        count += obj.products.filter(is_active=True, is_available=True).exclude(
            product_type__in=refactored_types
        ).count()

        return count

    def get_logo(self, obj):
        """URL логотипа. Прокси для R2/cdn — устраняет CORS/SSL на мобильном."""
        if not obj.logo:
            return None
        resolved = _resolve_media_url(obj.logo, self.context.get('request'))
        if resolved:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(resolved)
            return resolved
        return obj.logo

    def get_card_media_url(self, obj):
        """URL медиа-файла карточки бренда. Прокси для R2 — устраняет CORS/SSL на мобильном."""
        url = obj.get_card_media_url()
        if not url:
            return None
        resolved = _resolve_media_url(url, self.context.get('request'))
        if resolved:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(resolved)
            return resolved
        if url.startswith('/'):
            return url
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(url)
        return url

    def get_primary_category_slug(self, obj):
        """Slug основной категории бренда. Используем категорию, где у бренда есть товары."""
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
            "perfumery": "perfumery",
        }

        # Маппинг доменных моделей на slug категории
        domain_model_map = [
            ('furniture', FurnitureProduct),
            ('shoes', ShoeProduct),
            ('clothing', ClothingProduct),
            ('jewelry', JewelryProduct),
            ('electronics', ElectronicsProduct),
        ]

        def normalize(slug: str | None) -> str | None:
            if not slug:
                return None
            slug = slug.replace("_", "-").lower()
            return allowed_map.get(slug, slug)

        # Если primary_category_slug задан — доверяем ему
        if obj.primary_category_slug:
            norm = normalize(obj.primary_category_slug)
            if norm and norm in allowed_map.values():
                return norm

        products_qs = obj.products.filter(is_active=True).select_related("category__parent")

        # 1) Считаем самые частые категории (берём корневой/родительский slug если есть)
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

        # 3) Проверяем доменные модели (FurnitureProduct, ShoeProduct и т.д.)
        #    Это нужно для брендов, у которых товары только в доменных таблицах,
        #    но нет записей в базовой таблице Product
        best_slug = None
        best_count = 0
        for slug, model in domain_model_map:
            count = model.objects.filter(brand=obj, is_active=True).count()
            if count > best_count:
                best_count = count
                best_slug = slug
        if best_slug:
            return best_slug

        return None


class ProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор для изображений товара."""
    
    image_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductImage
        fields = ['id', 'image_url', 'video_url', 'alt_text', 'sort_order', 'is_main']
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        if getattr(obj, "video_url", None) or getattr(obj, "video_file", None):
            return None
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)

    def get_video_url(self, obj):
        request = self.context.get('request')
        raw_url = getattr(obj, "video_url", None)
        if not raw_url:
            raw_url = ""
        if raw_url:
            path_lower = raw_url.split("?")[0].lower()
            if not path_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg")):
                return _resolve_media_url(raw_url, request)
        file_url = _resolve_file_url(getattr(obj, "video_file", None), request)
        if file_url:
            return file_url
        return None
class ProductDynamicAttributeSerializer(serializers.ModelSerializer):
    """Сериализатор для динамических атрибутов товара."""
    
    key = serializers.ReadOnlyField(source='attribute_key.slug')
    key_display = serializers.ReadOnlyField(source='attribute_key.name')
    value = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductAttributeValue
        fields = ['id', 'key', 'key_display', 'value', 'sort_order']

    def get_value(self, obj):
        # Получаем язык из контекста (через i18n middleware обычно)
        from django.utils import translation
        lang = translation.get_language()
        
        if lang == 'ru' and obj.value_ru:
            return obj.value_ru
        if lang == 'en' and obj.value_en:
            return obj.value_en
        
        # Fallback на основное значение
        return obj.value


class PriceHistorySerializer(serializers.ModelSerializer):
    """Сериализатор для истории цен."""
    
    class Meta:
        model = PriceHistory
        fields = ['price', 'currency', 'recorded_at', 'source']


class AuthorSerializer(serializers.ModelSerializer):
    """Сериализатор для авторов."""
    full_name = serializers.ReadOnlyField()
    full_name_en = serializers.ReadOnlyField()
    
    class Meta:
        model = Author
        fields = ['id', 'first_name', 'last_name', 'first_name_en', 'last_name_en', 'full_name', 'full_name_en', 'bio', 'photo', 'birth_date', 'created_at']


class ProductAuthorSerializer(serializers.ModelSerializer):
    """Сериализатор для связи товаров с авторами."""
    author = AuthorSerializer(read_only=True)
    
    class Meta:
        model = ProductAuthor
        fields = ['id', 'author', 'created_at']


class BookGenreSerializer(serializers.ModelSerializer):
    translations = CategoryTranslationSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'translations']


class ProductGenreSerializer(serializers.ModelSerializer):
    genre = BookGenreSerializer(read_only=True)

    class Meta:
        model = ProductGenre
        fields = ['id', 'genre', 'sort_order']


class BookVariantSizeSerializer(serializers.ModelSerializer):
    """Сериализатор форматов варианта книги."""

    class Meta:
        model = BookVariantSize
        fields = ['id', 'size', 'is_available', 'stock_quantity', 'sort_order']
        read_only_fields = ['id']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        stock = data.get('stock_quantity')
        if stock is not None and stock == 0:
            data['is_available'] = False
        return data


class BookVariantImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений варианта книги."""

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = BookVariantImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class BookVariantSerializer(serializers.ModelSerializer):
    """Сериализатор вариантов книги."""

    name = serializers.SerializerMethodField()
    name_en = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    description_en = serializers.SerializerMethodField()
    images = BookVariantImageSerializer(many=True, read_only=True)
    sizes = BookVariantSizeSerializer(many=True, read_only=True)

    class Meta:
        model = BookVariant
        fields = [
            'id', 'slug', 'name', 'name_en', 'description', 'description_en',
            'cover_type', 'format_type', 'isbn',
            'price', 'old_price', 'currency',
            'is_available', 'stock_quantity',
            'main_image', 'images',
            'sku', 'barcode',
            'external_id', 'external_url', 'external_data',
            'is_active', 'sort_order',
            'created_at', 'updated_at',
            'sizes',
        ]
        read_only_fields = ['id', 'slug', 'sort_order', 'created_at', 'updated_at']

    def get_name(self, obj):
        return _get_variant_draft_title(obj, "ru") or obj.name

    def get_name_en(self, obj):
        return _get_variant_draft_title(obj, "en") or obj.name_en

    def get_description(self, obj):
        return _get_variant_localized_description(obj, "ru")

    def get_description_en(self, obj):
        return _get_variant_localized_description(obj, "en")


class ProductSerializer(_LocalizedSeoMethodsMixin, serializers.ModelSerializer):
    """Сериализатор для товаров (краткая информация)."""
    
    name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
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
    translations = serializers.SerializerMethodField()
    book_authors = ProductAuthorSerializer(many=True, read_only=True)
    book_genres = ProductGenreSerializer(many=True, read_only=True)
    book_attributes = serializers.SerializerMethodField()
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    isbn = serializers.SerializerMethodField()
    pages = serializers.SerializerMethodField()
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()
    publisher = serializers.SerializerMethodField()
    publication_date = serializers.SerializerMethodField()
    language = serializers.SerializerMethodField()
    cover_type = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()
    is_bestseller = serializers.SerializerMethodField()
    has_manual_main_image = serializers.BooleanField(read_only=True)
    main_video_url = serializers.SerializerMethodField()
    main_gif_url = serializers.SerializerMethodField()
    # Для shadow Product с доменом slug на доменной модели может отличаться от Product.slug (коллизии) —
    # фронт строит /product/{type}/{slug} по доменному API.
    slug = serializers.SerializerMethodField()
    
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
            'book_authors', 'book_genres', 'book_attributes', 'dynamic_attributes', 'product_type',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
            'main_image_url', 'video_url', 'main_video_url', 'main_gif_url', 'has_manual_main_image',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_slug(self, obj):
        """Слаг для ссылок на доменный detail API (если есть связанная доменная запись)."""
        from .models import HeadwearProduct, UnderwearProduct, IslamicClothingProduct

        pt = (getattr(obj, 'product_type', None) or '').strip().lower().replace('-', '_')
        try:
            if pt == 'headwear':
                dom = HeadwearProduct.objects.filter(base_product_id=obj.pk).only('slug').first()
                if dom and dom.slug:
                    return dom.slug
            elif pt == 'underwear':
                dom = UnderwearProduct.objects.filter(base_product_id=obj.pk).only('slug').first()
                if dom and dom.slug:
                    return dom.slug
            elif pt == 'islamic_clothing':
                dom = IslamicClothingProduct.objects.filter(base_product_id=obj.pk).only('slug').first()
                if dom and dom.slug:
                    return dom.slug
        except Exception:
            pass
        return obj.slug

    def get_name(self, obj):
        """Локализованное название."""
        request = self.context.get('request')
        lang = getattr(request, 'LANGUAGE_CODE', 'en') if request else 'en'
        if lang == 'ru':
            return obj.name
        
        # Сначала ищем в собственных переводах Product
        if hasattr(obj, 'translations'):
            # Если это QuerySet, проверяем его через filter
            if hasattr(obj.translations, 'filter'):
                trans = obj.translations.filter(locale=lang).first()
                if trans and trans.name:
                    return trans.name
            # Если это уже список (prefetch)
            elif isinstance(obj.translations, list):
                trans = next((t for t in obj.translations if t.locale == lang), None)
                if trans and trans.name:
                    return trans.name

        # Fallback к доменным моделям
        try:
            if hasattr(obj, 'domain_item') and obj.domain_item != obj:
                dt = obj.domain_item.translations.filter(locale=lang).first()
                if dt and dt.name:
                    return dt.name
        except Exception:
            pass
            
        return obj.name

    def get_description(self, obj):
        """Локализованное описание."""
        request = self.context.get('request')
        lang = getattr(request, 'LANGUAGE_CODE', 'en') if request else 'en'
        if lang == 'ru':
            return obj.description
            
        if hasattr(obj, 'translations'):
            if hasattr(obj.translations, 'filter'):
                trans = obj.translations.filter(locale=lang).first()
                if trans and trans.description:
                    return trans.description
            elif isinstance(obj.translations, list):
                trans = next((t for t in obj.translations if t.locale == lang), None)
                if trans and trans.description:
                    return trans.description

        try:
            if hasattr(obj, 'domain_item') and obj.domain_item != obj:
                dt = obj.domain_item.translations.filter(locale=lang).first()
                if dt and dt.description:
                    return dt.description
        except Exception:
            pass

        return obj.description

    def get_translations(self, obj):
        # Retrieve pre-fetched translations if any
        base_trans = []
        if hasattr(obj, 'translations') and hasattr(obj.translations, 'all'):
            # Pre-fetched relationships do not cause N+1 query
            base_trans = list(obj.translations.all())
        
        if base_trans:
            return ProductTranslationSerializer(base_trans, many=True).data

        # Fallback to domain models
        try:
            if hasattr(obj, 'domain_item'):
                domain_obj = obj.domain_item
                if domain_obj and hasattr(domain_obj, 'translations') and domain_obj != obj:
                    domain_trans = domain_obj.translations.all()
                    if domain_trans:
                        return [
                            {
                                "locale": t.locale,
                                "name": t.name,
                                "description": t.description,
                                "meta_title": getattr(t, "meta_title", ""),
                                "meta_description": getattr(t, "meta_description", ""),
                                "meta_keywords": getattr(t, "meta_keywords", ""),
                                "og_title": getattr(t, "og_title", ""),
                                "og_description": getattr(t, "og_description", ""),
                            }
                            for t in domain_trans
                        ]
        except Exception:
            pass

        return []
    
    def get_main_image_url(self, obj):
        """URL главного изображения."""
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "main_image_file", None), request)
        if file_url:
            return _resolve_media_url(file_url, request) or file_url
        
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
            return _resolve_media_url(obj.main_image, request)
        
        # Затем ищем главное изображение в связанных изображениях
        main_img = obj.images.filter(is_main=True).first()
        if main_img:
            file_url = _resolve_file_url(getattr(main_img, "image_file", None), request)
            if file_url:
                return _resolve_media_url(file_url, request) or file_url
            return _resolve_media_url(main_img.image_url, request) or main_img.image_url
        
        # Если нет главного, берем первое изображение
        first_img = obj.images.first()
        if first_img:
            file_url = _resolve_file_url(getattr(first_img, "image_file", None), request)
            if file_url:
                return _resolve_media_url(file_url, request) or file_url
            return _resolve_media_url(first_img.image_url, request) or first_img.image_url
        
        # Фолбэк: medicine, supplement и др. — domain_item с main_image/gallery_images
        try:
            domain = getattr(obj, "domain_item", None)
            if domain and callable(domain):
                domain = domain()
            if domain and domain != obj:
                file_url = _resolve_file_url(getattr(domain, "main_image_file", None), request)
                if file_url:
                    return file_url
                if getattr(domain, "main_image", None):
                    return _resolve_media_url(domain.main_image, request)
                gallery = getattr(domain, "gallery_images", None)
                if gallery:
                    first = gallery.first()
                    if first:
                        file_url = _resolve_file_url(getattr(first, "image_file", None), request)
                        if file_url:
                            return file_url
                        if getattr(first, "image_url", None):
                            return _resolve_media_url(first.image_url, request)
        except Exception:
            pass

        return None

    def get_video_url(self, obj):
        """URL видео товара (Generic). Приоритет загруженному файлу; затем доменная модель (shadow)."""
        request = self.context.get('request')

        def _from_entity(entity):
            if not entity:
                return None
            ff = getattr(entity, "main_video_file", None)
            if ff and getattr(ff, "name", None):
                resolved = _resolve_video_file_url(ff, request)
                if resolved:
                    return resolved
            raw = getattr(entity, "video_url", None) or ""
            if raw and raw.strip():
                path_lower = raw.split("?")[0].lower()
                if not path_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg")):
                    return _resolve_media_url(raw, request)
            return None

        # 1–2: shadow Product
        out = _from_entity(obj)
        if out:
            return out
        # Книги: явно book_item (как BookProductSerializer), без зависимости от порядка domain_item.
        pt = (getattr(obj, "product_type", None) or "").strip().lower().replace("-", "_")
        if pt == "books":
            try:
                bk = obj.book_item
            except Exception:
                bk = None
            if bk is not None:
                out = _from_entity(bk)
                if out:
                    return out
        # 3: остальные домены, если синк в Product ещё не заполнил видео
        try:
            domain = getattr(obj, "domain_item", None)
            if domain and domain != obj:
                out = _from_entity(domain)
                if out:
                    return out
        except Exception:
            pass
        return None

    def get_main_video_url(self, obj):
        """Дублирует video_url для фронта (карточки ожидают main_video_url || video_url)."""
        return self.get_video_url(obj)

    def get_main_gif_url(self, obj):
        """GIF с Product или доменной модели (например услуги с gif_file)."""
        request = self.context.get('request')

        def _from_entity(entity):
            if not entity:
                return None
            gf = getattr(entity, 'gif_file', None)
            if gf and getattr(gf, 'name', None):
                u = _resolve_file_url_if_stored(gf, request)
                if u:
                    return u
                return _resolve_file_url(gf, request)
            return None

        out = _from_entity(obj)
        if out:
            return out
        try:
            domain = getattr(obj, 'domain_item', None)
            if domain and domain != obj:
                out = _from_entity(domain)
                if out:
                    return out
        except Exception:
            pass
        return None

    def _get_external_attributes(self, obj):
        data = obj.external_data or {}
        attrs = data.get('attributes') or {}
        return attrs if isinstance(attrs, dict) else {}

    def get_book_attributes(self, obj):
        """Возвращает атрибуты книг из external_data (format, thickness_mm) для фронта."""
        attrs = self._get_external_attributes(obj)
        out = {}
        if attrs.get('format'):
            out['format'] = str(attrs['format']).strip()
        if attrs.get('thickness_mm') is not None and str(attrs.get('thickness_mm')).strip():
            out['thickness_mm'] = str(attrs['thickness_mm']).strip()
        return out

    def _is_valid_isbn(self, value):
        if not value:
            return False
        val = str(value).strip()
        if not val or "..." in val or "00000" in val:
            return False
        digits = re.sub(r'\D', '', val)
        return len(digits) in (10, 13)

    def get_isbn(self, obj):
        isbn_val = getattr(obj, 'isbn', None)
        if self._is_valid_isbn(isbn_val):
            return isbn_val
        attrs = self._get_external_attributes(obj)
        ext_isbn = attrs.get('isbn')
        if self._is_valid_isbn(ext_isbn):
            return str(ext_isbn).strip()
        return None

    def get_pages(self, obj):
        pages_val = getattr(obj, 'pages', None)
        if pages_val and pages_val > 0:
            return pages_val
        attrs = self._get_external_attributes(obj)
        pages = attrs.get('pages')
        if pages is None:
            return None
        try:
            pages_val = int(pages)
        except (TypeError, ValueError):
            return None
        return pages_val if pages_val > 0 else None
    
    def get_publisher(self, obj):
        return getattr(obj, 'publisher', None)

    def get_publication_date(self, obj):
        return getattr(obj, 'publication_date', None)

    def get_language(self, obj):
        return getattr(obj, 'language', None)

    def get_cover_type(self, obj):
        return getattr(obj, 'cover_type', None)

    def get_rating(self, obj):
        return getattr(obj, 'rating', None)

    def get_reviews_count(self, obj):
        return getattr(obj, 'reviews_count', None)

    def get_is_bestseller(self, obj):
        return getattr(obj, 'is_bestseller', False)
    
    def get_price_formatted(self, obj):
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
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
                pass
            return f"{obj.price} {from_currency}"
        return None
    
    def get_old_price_formatted(self, obj):
        """Форматированная старая цена."""
        if obj.old_price is not None:
            request = self.context.get('request')
            preferred_currency = self._get_preferred_currency(request)
            from_currency = (obj.currency or 'RUB').upper()
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
            formatted_price = f"{obj.old_price}"
            if '.' in formatted_price:
                formatted_price = formatted_price.rstrip('0').rstrip('.')
            return f"{formatted_price} {from_currency}"
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
        
        # 1. Пробуем получить из кэшированных цен
        try:
            prices = obj.get_all_prices()
            if prices and preferred_currency in prices:
                return prices[preferred_currency].get('price_with_margin')
        except Exception:
            pass
            
        # 2. Fallback: конвертация на лету
        if obj.price is not None:
            from_currency = (obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_with_margin = currency_converter.convert_price(
                    Decimal(str(obj.price)),
                    from_currency,
                    preferred_currency,
                    apply_margin=True,
                )
                return price_with_margin
            except Exception:
                pass
        
        return obj.price
    
    def get_currency(self, obj):
        """Получает валюту товара."""
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        
        # 1. Пробуем получить из кэшированных цен
        try:
            prices = obj.get_all_prices()
            if prices and preferred_currency in prices:
                return preferred_currency
        except Exception:
            pass
            
        # 2. Fallback: если конвертация возможна, возвращаем preferred_currency
        if obj.price is not None:
            from_currency = (obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                currency_converter.convert_price(
                    Decimal(str(obj.price)),
                    from_currency,
                    preferred_currency,
                    apply_margin=True,
                )
                return preferred_currency
            except Exception:
                pass
        
        return obj.currency or 'RUB'
    
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
    
    images = serializers.SerializerMethodField()
    price_history = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()
    book_variants = serializers.SerializerMethodField()
    
    class Meta(ProductSerializer.Meta):
        fields = ProductSerializer.Meta.fields + [
            'images', 'price_history', 'external_id',
            'external_url', 'sku', 'barcode', 'last_synced_at',
            'book_variants',
        ]
    
    def get_price_history(self, obj):
        """История цен (последние 10 записей)."""
        history = obj.price_history.all()[:10]
        return PriceHistorySerializer(history, many=True).data

    def get_images(self, obj):
        gallery = getattr(obj, "images", None)
        request = self.context.get("request")
        context = {"request": request}

        def _serialize_gallery(qs):
            if not qs:
                return []
            qs = qs.all().order_by("sort_order", "id")
            has_video = bool(getattr(obj, "video_url", None))
            has_video_in_gallery = qs.filter(
                **{"video_url__isnull": False}
            ).exclude(video_url="").exists() if hasattr(qs.model, "video_url") else False
            filtered = []
            for img in qs:
                raw_image_url = getattr(img, "image_url", "") or ""
                raw_video_url = getattr(img, "video_url", "") or ""
                image_is_video = raw_image_url and detect_media_type(raw_image_url) == "video"
                if image_is_video and (has_video or has_video_in_gallery):
                    continue
                try:
                    data = ProductImageSerializer(img, context=context).data
                except Exception:
                    data = {
                        "id": getattr(img, "id", 0),
                        "image_url": _resolve_file_url(getattr(img, "image_file", None), request)
                        or _resolve_media_url(raw_image_url, request),
                        "video_url": None,
                        "alt_text": getattr(img, "alt_text", "") or "",
                        "sort_order": getattr(img, "sort_order", 0) or 0,
                        "is_main": getattr(img, "is_main", False) or False,
                    }
                if image_is_video and not raw_video_url:
                    data["video_url"] = _resolve_media_url(raw_image_url, request)
                    data["image_url"] = None
                if data.get("image_url") or data.get("video_url"):
                    filtered.append(data)
            return filtered

        result = _serialize_gallery(gallery)
        if result:
            return result

        domain = getattr(obj, "domain_item", None)
        if domain and domain != obj:
            gallery_domain = getattr(domain, "gallery_images", None) or getattr(domain, "images", None)
            if gallery_domain:
                main_first = []
                rest = []
                for img in gallery_domain.all().order_by("sort_order", "id"):
                    url = _resolve_file_url(getattr(img, "image_file", None), request)
                    if not url:
                        url = _resolve_media_url(getattr(img, "image_url", "") or "", request)
                    else:
                        url = _resolve_media_url(url, request) or url
                    raw_video = getattr(img, "video_url", "") or ""
                    vid_url = _resolve_media_url(raw_video, request) if raw_video else None
                    if not vid_url and getattr(img, "video_file", None):
                        vid_url = _resolve_file_url(img.video_file, request)
                    if url or vid_url:
                        item = {
                            "id": getattr(img, "id", 0),
                            "image_url": url,
                            "video_url": vid_url,
                            "alt_text": getattr(img, "alt_text", "") or "",
                            "sort_order": getattr(img, "sort_order", 0) or 0,
                            "is_main": getattr(img, "is_main", False) or False,
                        }
                        if item.get("is_main"):
                            main_first.insert(0, item)
                        else:
                            rest.append(item)
                return main_first + rest

        return []

    def get_book_variants(self, obj):
        if (obj.product_type or "").lower() != "books":
            return []
        book_product = getattr(obj, "book_item", None)
        if book_product is None:
            return []
        variants = book_product.book_variants.filter(is_active=True).order_by("sort_order", "id")
        return BookVariantSerializer(variants, many=True, context={"request": self.context.get("request")}).data
    
    def get_og_image_url(self, obj):
        """OG изображение с прокси для Instagram."""
        request = self.context.get('request')
        
        og_value = resolve_book_seo_value(obj, "og_image_url")
        if og_value:
            if 'instagram.f' in og_value or 'cdninstagram.com' in og_value:
                if request:
                    scheme = request.scheme
                    host = request.get_host()
                    if 'backend' in host or 'localhost:3001' in host or 'localhost:3000' in host:
                        base_url = f"{scheme}://localhost:8000"
                    else:
                        base_url = f"{scheme}://{host}"
                    return f"{base_url}/api/catalog/proxy-image/?url={quote(og_value)}"
                return f"http://localhost:8000/api/catalog/proxy-image/?url={quote(og_value)}"
            return og_value
        
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
        fields = ['id', 'product', 'chosen_size', 'created_at']
        read_only_fields = ['id', 'chosen_size', 'created_at']
    
    def get_product(self, obj):
        """Сериализация товара в зависимости от его типа."""
        from .models import BookProduct, HeadwearProduct, UnderwearProduct, IslamicClothingProduct

        product = obj.product
        request = self.context.get('request')

        def _pin_base_product_fields(data: dict, base_pk: int) -> dict:
            """ID в избранном всегда совпадает с object_id (shadow Product)."""
            data['id'] = base_pk
            data['base_product_id'] = base_pk
            return data

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
        elif isinstance(product, JewelryProduct):
            product_type = 'jewelry'
            product_data = JewelryProductSerializer(product, context={'request': request}).data
        elif isinstance(product, BookProduct):
            product_type = 'books'
            product_data = BookProductSerializer(product, context={'request': request}).data
            if product.base_product_id:
                _pin_base_product_fields(product_data, product.base_product_id)
        elif isinstance(product, HeadwearProduct):
            product_type = 'headwear'
            product_data = HeadwearProductSerializer(product, context={'request': request}).data
            if product.base_product_id:
                _pin_base_product_fields(product_data, product.base_product_id)
        elif isinstance(product, UnderwearProduct):
            product_type = 'underwear'
            product_data = UnderwearProductSerializer(product, context={'request': request}).data
            if product.base_product_id:
                _pin_base_product_fields(product_data, product.base_product_id)
        elif isinstance(product, IslamicClothingProduct):
            product_type = 'islamic_clothing'
            product_data = IslamicClothingProductSerializer(product, context={'request': request}).data
            if product.base_product_id:
                _pin_base_product_fields(product_data, product.base_product_id)
        elif isinstance(product, Product):
            raw_pt = getattr(product, 'product_type', None) or 'medicines'
            product_type = str(raw_pt).strip().lower().replace('-', '_')
            hw_item = uw_item = ic_item = None
            if product_type == 'headwear':
                try:
                    hw_item = product.headwear_item
                except HeadwearProduct.DoesNotExist:
                    hw_item = None
            if product_type == 'underwear':
                try:
                    uw_item = product.underwear_item
                except UnderwearProduct.DoesNotExist:
                    uw_item = None
            if product_type in ('islamic_clothing', 'islamic-clothing'):
                try:
                    ic_item = product.islamic_clothing_item
                except IslamicClothingProduct.DoesNotExist:
                    ic_item = None
            book_item = None
            if product_type == 'books':
                try:
                    book_item = product.book_item
                except BookProduct.DoesNotExist:
                    book_item = None
            if book_item is not None:
                product_data = BookProductSerializer(book_item, context={'request': request}).data
                _pin_base_product_fields(product_data, product.id)
            elif hw_item is not None:
                product_data = HeadwearProductSerializer(hw_item, context={'request': request}).data
                _pin_base_product_fields(product_data, product.id)
            elif uw_item is not None:
                product_data = UnderwearProductSerializer(uw_item, context={'request': request}).data
                _pin_base_product_fields(product_data, product.id)
            elif ic_item is not None:
                product_data = IslamicClothingProductSerializer(ic_item, context={'request': request}).data
                _pin_base_product_fields(product_data, product.id)
            else:
                product_data = ProductSerializer(product, context={'request': request}).data
        elif isinstance(product, Service):
            product_type = 'uslugi'
            product_data = ServiceSerializer(product, context={'request': request}).data
        else:
            # Fallback для неизвестных типов
            product_data = {
                'id': getattr(product, 'id', None),
                'name': getattr(product, 'name', 'Unknown'),
                'slug': getattr(product, 'slug', ''),
                'price': str(getattr(product, 'price', '')) if hasattr(product, 'price') else None,
                'currency': getattr(product, 'currency', ''),
                'main_image_url': getattr(product, 'main_image', None) or getattr(product, 'main_image_url', None),
                'video_url': getattr(product, 'video_url', None) or getattr(product, 'main_video_url', None) or getattr(product, 'main_video', None)
            }

        # Тип для фронта: дефисы (как в URL и TYPES_NEEDING_PATH)
        api_pt = str(product_type).replace('_', '-')
        product_data['_product_type'] = api_pt
        product_data['favorite_chosen_size'] = getattr(obj, 'chosen_size', '') or ''
        ed = getattr(product, 'external_data', None) if isinstance(product, Product) else None
        if isinstance(ed, dict):
            sv = ed.get('source_variant_slug')
            if sv:
                product_data['favorite_variant_slug'] = sv
        return product_data


def resolve_product_for_favorites_api(product_id, product_type_raw):
    """
    Единая резолвация товара для add/remove/check избранного.

    Для headwear / underwear / islamic_clothing / books допускается id доменной строки или id shadow Product
    (как в листингах и карточках). Избранное хранится на доменной модели; ответ списка по-прежнему
    отдаёт id shadow Product в поле id (см. FavoriteSerializer), если у домена задан base_product_id.
    """
    from django.core.exceptions import ObjectDoesNotExist

    from .models import (
        ClothingProduct,
        ShoeProduct,
        ElectronicsProduct,
        FurnitureProduct,
        JewelryProduct,
        Service,
        MedicineProduct,
        SupplementProduct,
        HeadwearProduct,
        UnderwearProduct,
        IslamicClothingProduct,
    )

    try:
        pid = int(product_id)
    except (TypeError, ValueError):
        raise serializers.ValidationError({"product_id": "Некорректный product_id"})

    product_type = (product_type_raw or 'medicines').strip().lower().replace('-', '_')
    product_type = {
        'medical_accessories': 'accessories',
        'medical_accessory': 'accessories',
        'accessory': 'accessories',
    }.get(product_type, product_type)

    def _ensure_active(obj):
        if hasattr(obj, 'is_active') and not obj.is_active:
            raise serializers.ValidationError({"product_id": "Товар неактивен"})
        return obj

    def _resolve_domain_triplet(model_cls, reverse_attr):
        try:
            return _ensure_active(model_cls.objects.get(id=pid))
        except model_cls.DoesNotExist:
            pass
        row = model_cls.objects.filter(base_product_id=pid).first()
        if row:
            return _ensure_active(row)
        try:
            p = Product.objects.get(id=pid)
        except Product.DoesNotExist:
            raise serializers.ValidationError({"product_id": "Товар не найден"})
        try:
            dom = getattr(p, reverse_attr)
        except ObjectDoesNotExist:
            raise serializers.ValidationError({"product_id": "Товар не найден"})
        return _ensure_active(dom)

    if product_type == 'headwear':
        return _resolve_domain_triplet(HeadwearProduct, 'headwear_item'), product_type
    if product_type == 'underwear':
        return _resolve_domain_triplet(UnderwearProduct, 'underwear_item'), product_type
    if product_type == 'islamic_clothing':
        return _resolve_domain_triplet(IslamicClothingProduct, 'islamic_clothing_item'), product_type

    # Книги: число pid может быть id shadow Product (витрина /catalog/products) или pk BookProduct (домен).
    # Если в Product есть строка books с этим pk — сначала трактуем как shadow (избранное по base_product_id),
    # иначе — как доменный pk; иначе коллизия «pk книги = id чужого shadow» ломала добавление.
    if product_type == 'books':
        from .models import BookProduct

        shadow_book = BookProduct.objects.filter(base_product_id=pid).first()
        dom_book = BookProduct.objects.filter(pk=pid).first()
        prod_is_book_shadow = Product.objects.filter(pk=pid, product_type='books', is_active=True).exists()
        if prod_is_book_shadow and shadow_book:
            return _ensure_active(shadow_book), product_type
        if dom_book:
            return _ensure_active(dom_book), product_type
        if shadow_book:
            return _ensure_active(shadow_book), product_type
        try:
            p = Product.objects.get(id=pid)
        except Product.DoesNotExist:
            raise serializers.ValidationError({"product_id": "Товар не найден"})
        pt = (getattr(p, "product_type", None) or "").strip().lower().replace("-", "_")
        if pt != "books":
            raise serializers.ValidationError({"product_id": "Товар не найден"})
        try:
            dom = p.book_item
        except BookProduct.DoesNotExist:
            raise serializers.ValidationError({"product_id": "Товар не найден"})
        return _ensure_active(dom), product_type

    try:
        from .models import MedicalEquipmentProduct
    except ImportError:
        MedicalEquipmentProduct = None

    domain_maps = {}
    if MedicalEquipmentProduct:
        domain_maps['medical_equipment'] = MedicalEquipmentProduct

    PRODUCT_MODEL_MAP = {
        'medicines': MedicineProduct,
        'supplements': SupplementProduct if SupplementProduct else Product,
        'medical_equipment': domain_maps.get('medical_equipment', Product),
        'tableware': Product,
        'accessories': Product,
        'jewelry': JewelryProduct,
        'perfumery': Product,
        'clothing': ClothingProduct,
        'shoes': ShoeProduct,
        'electronics': ElectronicsProduct,
        'furniture': FurnitureProduct,
        'uslugi': Service,
    }

    model_class = PRODUCT_MODEL_MAP.get(product_type) or Product

    try:
        product = model_class.objects.get(id=pid)
        return _ensure_active(product), product_type
    except model_class.DoesNotExist:
        if model_class is not Product:
            try:
                product = Product.objects.get(id=pid)
                return _ensure_active(product), product_type
            except Product.DoesNotExist:
                raise serializers.ValidationError({"product_id": "Товар не найден"})
        raise serializers.ValidationError({"product_id": "Товар не найден"})


class AddToFavoriteSerializer(serializers.Serializer):
    """
    Добавление/удаление из избранного.
    Либо product_id (как раньше), либо product_slug + product_type — как при добавлении в корзину
    (вариант мебели, обуви, одежды → shadow Product + chosen_size).
    """

    product_id = serializers.IntegerField(required=False, allow_null=True)
    product_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    product_slug = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    size = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        from apps.orders.serializers import resolve_product_like_add_to_cart

        slug = (attrs.get('product_slug') or '').strip()
        ptype = attrs.get('product_type')
        size_raw = attrs.get('size')
        size_str = (size_raw or '').strip() if size_raw is not None else ''

        # Сначала slug (вариант мебели/обуви и т.д.): не смешиваем с product_id.
        # Иначе клиенты с product_id: 0 / мусором + product_slug получали 400.
        if slug:
            product, chosen = resolve_product_like_add_to_cart(
                product_id=None,
                product_type=ptype,
                product_slug=slug,
                size=size_str,
            )
            attrs['_product'] = product
            attrs['_chosen_size'] = chosen or ''
            pt = getattr(product, 'product_type', None) or ptype or 'medicines'
            attrs['_product_type'] = str(pt).strip().lower().replace('-', '_')
            return attrs

        pid_raw = attrs.get('product_id')
        pid_int = None
        if pid_raw is not None and pid_raw != '':
            try:
                pid_int = int(pid_raw)
            except (TypeError, ValueError):
                pid_int = None
        if not pid_int or pid_int <= 0:
            raise serializers.ValidationError({"detail": _("Нужен product_id или product_slug")})

        product, norm_type = resolve_product_for_favorites_api(pid_int, ptype)
        attrs['_product'] = product
        attrs['_chosen_size'] = ''
        attrs['_product_type'] = norm_type
        return attrs



# ============================================================================
# СЕРИАЛИЗАТОРЫ ДЛЯ ОДЕЖДЫ, ОБУВИ И ЭЛЕКТРОНИКИ
# ============================================================================

class ClothingCategorySerializer(serializers.ModelSerializer):
    """Сериализатор для категорий одежды."""
    
    children_count = serializers.SerializerMethodField()
    gender_display = serializers.SerializerMethodField()
    ancestors = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'parent', 'ancestors',
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

    def get_ancestors(self, obj):
        """Возвращает список родительских категорий (снизу вверх) с именами и слагами."""
        from django.utils import translation
        request = self.context.get('request')
        lang = getattr(request, 'LANGUAGE_CODE', None) if request else None
        if not lang:
            lang = translation.get_language() or 'ru'
            
        ancestors_list = []
        curr = obj.parent
        while curr:
            name = curr.name
            # Попытка локализации родителя
            if hasattr(curr, 'translations'):
                try:
                    t = curr.translations.filter(locale=lang).first()
                    if t and t.name:
                        name = t.name
                except Exception:
                    pass
            
            ancestors_list.append({
                'id': curr.id,
                'name': name,
                'slug': curr.slug
            })
            curr = curr.parent
        
        ancestors_list.reverse()
        return ancestors_list


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

    name = serializers.SerializerMethodField()
    name_en = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    description_en = serializers.SerializerMethodField()
    images = ClothingVariantImageSerializer(many=True, read_only=True)
    sizes = ClothingVariantSizeSerializer(many=True, read_only=True)

    class Meta:
        model = ClothingVariant
        fields = [
            'id', 'slug', 'name', 'name_en', 'description', 'description_en', 'color',
            'size',  # устаревшее поле оставлено для совместимости
            'sizes',
            'price', 'old_price', 'currency',
            'is_available',
            'main_image', 'images',
            'sku', 'barcode', 'gtin', 'mpn',
            'is_active', 'sort_order',
        ]
        read_only_fields = ['id', 'slug', 'sort_order']

    def get_name(self, obj):
        return _get_variant_draft_title(obj, "ru") or obj.name

    def get_name_en(self, obj):
        return _get_variant_draft_title(obj, "en") or obj.name_en

    def get_description(self, obj):
        return _get_variant_localized_description(obj, "ru")

    def get_description_en(self, obj):
        return _get_variant_localized_description(obj, "en")

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


class ClothingProductSerializer(_LocalizedSeoMethodsMixin, serializers.ModelSerializer):
    """Сериализатор для товаров одежды (краткая информация)."""
    
    category = ClothingCategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
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
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()
    product_type = serializers.SerializerMethodField(read_only=True)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    
    def get_product_type(self, obj):
        raw = getattr(type(obj), '_domain_product_type', None)
        return str(raw).replace('_', '-') if raw else None

    class Meta:
        model = ClothingProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'size', 'color',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url', 'video_url',
            'images', 'sizes', 'dynamic_attributes', 'product_type',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
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
    
    def get_video_url(self, obj):
        """URL видео для воспроизведения (Clothing). Приоритет загруженному файлу."""
        request = self.context.get('request')
        
        # 1. Приоритет файлу в ClothingProduct
        file_field = getattr(obj, "main_video_file", None)
        if file_field and getattr(file_field, "name", None):
            resolved = _resolve_video_file_url(file_field, request)
            if resolved:
                return resolved

        # 2. Проверка shadow-копии (Product)
        base_product = getattr(obj, "base_product", None)
        if base_product:
            file_field = getattr(base_product, "main_video_file", None)
            if file_field and getattr(file_field, "name", None):
                resolved = _resolve_video_file_url(file_field, request)
                if resolved:
                    return resolved

        # 3. Фолбэк на внешний URL
        raw_url = getattr(obj, "video_url", None) or ""
        if raw_url and raw_url.strip():
            path_lower = raw_url.split("?")[0].lower()
            if not path_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg")):
                return _resolve_media_url(raw_url, request)
                
        return None
    
    def get_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return self.get_active_variant_price(obj)

        preferred_currency = self._get_preferred_currency(obj)
        if obj.price is None:
            return None

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
            pass

        return f"{obj.price} {from_currency}"
    
    def get_old_price_formatted(self, obj):
        """Форматированная старая цена."""
        if obj.old_price is not None:
            preferred_currency = self._get_preferred_currency(obj)
            from_currency = (obj.currency or 'RUB').upper()
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
            # Форматируем число, убирая лишние нули после запятой
            formatted_price = f"{obj.old_price}"
            if '.' in formatted_price:
                formatted_price = formatted_price.rstrip('0').rstrip('.')
            return f"{formatted_price} {from_currency}"
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
                # Форматируем число, убирая лишние нули после запятой
                formatted_price = f"{variant.old_price}"
                if '.' in formatted_price:
                    formatted_price = formatted_price.rstrip('0').rstrip('.')
                return f"{formatted_price} {from_currency}"
            # Форматируем число, убирая лишние нули после запятой
            formatted_price = f"{variant.old_price}"
            if '.' in formatted_price:
                formatted_price = formatted_price.rstrip('0').rstrip('.')
            return f"{formatted_price} {from_currency}"
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
    ancestors = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'parent', 'ancestors',
            'gender', 'gender_display',
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

    def get_ancestors(self, obj):
        """Возвращает список родительских категорий (снизу вверх) с именами и слагами."""
        from django.utils import translation
        request = self.context.get('request')
        lang = getattr(request, 'LANGUAGE_CODE', None) if request else None
        if not lang:
            lang = translation.get_language() or 'ru'
            
        ancestors_list = []
        curr = obj.parent
        while curr:
            name = curr.name
            # Попытка локализации родителя
            if hasattr(curr, 'translations'):
                try:
                    t = curr.translations.filter(locale=lang).first()
                    if t and t.name:
                        name = t.name
                except Exception:
                    pass
            
            ancestors_list.append({
                'id': curr.id,
                'name': name,
                'slug': curr.slug
            })
            curr = curr.parent
        
        ancestors_list.reverse()
        return ancestors_list


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


class ShoeProductSerializer(_LocalizedSeoMethodsMixin, serializers.ModelSerializer):
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
    video_url = serializers.SerializerMethodField()
    translations = ShoeProductTranslationSerializer(many=True, read_only=True)
    product_type = serializers.SerializerMethodField(read_only=True)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ShoeProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'size', 'color',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url', 'video_url',
            'images', 'sizes', 'dynamic_attributes', 'product_type',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_product_type(self, obj):
        raw = getattr(type(obj), '_domain_product_type', None)
        return str(raw).replace('_', '-') if raw else None
    
    def get_video_url(self, obj):
        """URL видео товара (Shoes). Приоритет загруженному файлу."""
        request = self.context.get('request')
        
        # 1. Приоритет файлу в ShoeProduct
        file_field = getattr(obj, "main_video_file", None)
        if file_field and getattr(file_field, "name", None):
            resolved = _resolve_video_file_url(file_field, request)
            if resolved:
                return resolved

        # 2. Проверка shadow-копии (Product)
        base_product = getattr(obj, "base_product", None)
        if base_product:
            file_field = getattr(base_product, "main_video_file", None)
            if file_field and getattr(file_field, "name", None):
                resolved = _resolve_video_file_url(file_field, request)
                if resolved:
                    return resolved

        # 3. Фолбэк на внешний URL
        raw_url = getattr(obj, "video_url", None) or ""
        if raw_url and raw_url.strip():
            path_lower = raw_url.split("?")[0].lower()
            if not path_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg")):
                return _resolve_media_url(raw_url, request)
                
        return None

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
            # Форматируем число, убирая лишние нули после запятой
            formatted_price = f"{obj.old_price}"
            if '.' in formatted_price:
                formatted_price = formatted_price.rstrip('0').rstrip('.')
            return f"{formatted_price} {from_currency}"
        return None

    def get_active_variant_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        preferred_currency = self._get_preferred_currency(obj)
        if variant and variant.old_price is not None:
            from_currency = (variant.currency or obj.currency or 'RUB').upper()
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
                # Форматируем число, убирая лишние нули после запятой
                formatted_price = f"{variant.old_price}"
                if '.' in formatted_price:
                    formatted_price = formatted_price.rstrip('0').rstrip('.')
                return f"{formatted_price} {from_currency}"
            # Форматируем число, убирая лишние нули после запятой
            formatted_price = f"{variant.old_price}"
            if '.' in formatted_price:
                formatted_price = formatted_price.rstrip('0').rstrip('.')
            return f"{formatted_price} {from_currency}"
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

    name = serializers.SerializerMethodField()
    name_en = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    description_en = serializers.SerializerMethodField()
    images = ShoeVariantImageSerializer(many=True, read_only=True)
    sizes = ShoeVariantSizeSerializer(many=True, read_only=True)

    class Meta:
        model = ShoeVariant
        fields = [
            'id', 'slug', 'name', 'name_en', 'description', 'description_en', 'color',
            'size',  # устаревшее поле оставлено для совместимости
            'sizes',
            'price', 'old_price', 'currency',
            'is_available',
            'main_image', 'images',
            'sku', 'barcode', 'gtin', 'mpn',
            'is_active', 'sort_order',
        ]
        read_only_fields = ['id', 'slug', 'sort_order']

    def get_name(self, obj):
        return _get_variant_draft_title(obj, "ru") or obj.name

    def get_name_en(self, obj):
        return _get_variant_draft_title(obj, "en") or obj.name_en

    def get_description(self, obj):
        return _get_variant_localized_description(obj, "ru")

    def get_description_en(self, obj):
        return _get_variant_localized_description(obj, "en")

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


class ElectronicsProductSerializer(_LocalizedSeoMethodsMixin, serializers.ModelSerializer):
    """Сериализатор для товаров электроники (краткая информация)."""
    
    category = ElectronicsCategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    translations = ElectronicsProductTranslationSerializer(many=True, read_only=True)
    product_type = serializers.SerializerMethodField(read_only=True)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ElectronicsProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'model', 'specifications', 'warranty', 'power_consumption',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url',
            'images', 'dynamic_attributes', 'product_type',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_product_type(self, obj):
        raw = getattr(type(obj), '_domain_product_type', None)
        return str(raw).replace('_', '-') if raw else None
    
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

class FurnitureProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений товаров мебели (галерея)."""
    
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = FurnitureProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


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

    name = serializers.SerializerMethodField()
    name_en = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    description_en = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    old_price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    size_display = serializers.SerializerMethodField()
    color_display = serializers.SerializerMethodField()

    class Meta:
        model = FurnitureVariant
        fields = [
            'id', 'name', 'name_en', 'description', 'description_en', 'slug', 'color',
            'price', 'old_price', 'currency',
            'is_available', 'stock_quantity',
            'main_image', 'images',
            'sku', 'barcode', 'gtin', 'mpn',
            'is_active', 'sort_order', 'size_display', 'color_display',
        ]
        read_only_fields = ['id', 'slug', 'sort_order']

    def get_name(self, obj):
        return _get_variant_draft_title(obj, "ru") or obj.name

    def get_name_en(self, obj):
        return _get_variant_draft_title(obj, "en") or obj.name_en

    def get_description(self, obj):
        return _get_variant_localized_description(obj, "ru")

    def get_description_en(self, obj):
        return _get_variant_localized_description(obj, "en")

    def _get_preferred_currency(self, request):
        default = 'RUB'
        if not request:
            return default
        preferred = request.headers.get('X-Currency') or request.query_params.get('currency')
        if preferred:
            return preferred.upper()
        if getattr(request, 'user', None) and request.user.is_authenticated:
            uc = getattr(request.user, 'currency', None)
            if uc:
                return uc.upper()
        lang = getattr(request, 'LANGUAGE_CODE', None)
        return {'en': 'USD', 'ru': 'RUB'}.get(lang, default)

    def get_price(self, obj):
        if obj.price is None:
            return None
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        from_currency = (obj.currency or 'RUB').upper()
        try:
            from .utils.currency_converter import currency_converter
            _, _, price_with_margin = currency_converter.convert_price(
                Decimal(str(obj.price)),
                from_currency,
                preferred_currency,
                apply_margin=True,
            )
            return price_with_margin
        except Exception:
            pass
        return obj.price

    def get_old_price(self, obj):
        if obj.old_price is None:
            return None
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        from_currency = (obj.currency or 'RUB').upper()
        try:
            from .utils.currency_converter import currency_converter
            _, _, price_with_margin = currency_converter.convert_price(
                Decimal(str(obj.old_price)),
                from_currency,
                preferred_currency,
                apply_margin=True,
            )
            return price_with_margin
        except Exception:
            pass
        return obj.old_price

    def get_currency(self, obj):
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        if obj.price is not None:
            from_currency = (obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                currency_converter.convert_price(
                    Decimal(str(obj.price)),
                    from_currency,
                    preferred_currency,
                    apply_margin=True,
                )
                return preferred_currency
            except Exception:
                pass
        return obj.currency or 'RUB'

    def get_images(self, obj):
        """Галерея изображений варианта."""
        gallery = getattr(obj, "images", None)
        if not gallery:
            return []
        return FurnitureVariantImageSerializer(gallery.all().order_by("sort_order"), many=True).data

    def get_size_display(self, obj):
        """Краткий размер из IKEA variant1 (например 120x70 cm) для карточки у цены."""
        ed = obj.external_data if isinstance(obj.external_data, dict) else {}
        info = ed.get("ikea_variant_info")
        if isinstance(info, dict):
            v1 = info.get("variant1")
            if isinstance(v1, dict):
                val = (v1.get("value") or "").strip()
                if val:
                    return val
        return ""

    def get_color_display(self, obj):
        """Подпись цвета для витрины: поле color или value из ikea_variant_info."""
        raw = (getattr(obj, "color", None) or "").strip()
        if raw:
            return raw
        ed = obj.external_data if isinstance(obj.external_data, dict) else {}
        info = ed.get("ikea_variant_info")
        if isinstance(info, dict):
            c = info.get("color")
            if isinstance(c, dict):
                val = (c.get("value") or "").strip()
                if val:
                    return val
        return ""


class FurnitureProductSerializer(_LocalizedSeoMethodsMixin, serializers.ModelSerializer):
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
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    translations = FurnitureProductTranslationSerializer(many=True, read_only=True)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    base_product_id = serializers.IntegerField(read_only=True)
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
    product_type = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = FurnitureProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'external_id',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'material', 'furniture_type', 'dimensions',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url', 'video_url',
            'images', 'dynamic_attributes', 'product_type',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations',
            'base_product_id',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_product_type(self, obj):
        """Тип товара для API: из _domain_product_type (как у других доменных сериализаторов)."""
        raw = getattr(type(obj), '_domain_product_type', None)
        return str(raw).replace('_', '-') if raw else None

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

    def get_video_url(self, obj):
        """URL видео товара (Furniture). Приоритет загруженному файлу."""
        request = self.context.get('request')
        
        # 1. Приоритет файлу в FurnitureProduct
        file_field = getattr(obj, "main_video_file", None)
        if file_field and getattr(file_field, "name", None):
            resolved = _resolve_video_file_url(file_field, request)
            if resolved:
                return resolved

        # 2. Проверка shadow-копии (Product), т.к. enrichment часто обновляет только её
        base_product = getattr(obj, "base_product", None)
        if base_product:
            file_field = getattr(base_product, "main_video_file", None)
            if file_field and getattr(file_field, "name", None):
                resolved = _resolve_video_file_url(file_field, request)
                if resolved:
                    return resolved

        # 3. Фолбэк на внешний URL
        raw_url = getattr(obj, "video_url", None) or ""
        if raw_url and raw_url.strip():
            path_lower = raw_url.split("?")[0].lower()
            if not path_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg")):
                return _resolve_media_url(raw_url, request)
                
        return None
    
    def get_price_formatted(self, obj):
        """Форматированная цена."""
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            preferred_currency = self._get_preferred_currency(obj)
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
                pass
            return f"{variant.price} {from_currency}"
        if obj.price is not None:
            preferred_currency = self._get_preferred_currency(obj)
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
                pass
            return f"{obj.price} {from_currency}"
        return None
    
    def get_old_price_formatted(self, obj):
        """Форматированная старая цена."""
        variant = self._get_active_variant(obj)
        preferred_currency = self._get_preferred_currency(obj)
        if variant and variant.old_price is not None:
            from_currency = (variant.currency or obj.currency or 'RUB').upper()
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
                # Форматируем число, убирая лишние нули после запятой
                formatted_price = f"{variant.old_price}"
                if '.' in formatted_price:
                    formatted_price = formatted_price.rstrip('0').rstrip('.')
                return f"{formatted_price} {from_currency}"
            # Форматируем число, убирая лишние нули после запятой
            formatted_price = f"{variant.old_price}"
            if '.' in formatted_price:
                formatted_price = formatted_price.rstrip('0').rstrip('.')
            return f"{formatted_price} {from_currency}"
        if obj.old_price is not None:
            from_currency = (obj.currency or 'RUB').upper()
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
                # Форматируем число, убирая лишние нули после запятой
                formatted_price = f"{obj.old_price}"
                if '.' in formatted_price:
                    formatted_price = formatted_price.rstrip('0').rstrip('.')
                return f"{formatted_price} {from_currency}"
            # Форматируем число, убирая лишние нули после запятой
            formatted_price = f"{obj.old_price}"
            if '.' in formatted_price:
                formatted_price = formatted_price.rstrip('0').rstrip('.')
            return f"{formatted_price} {from_currency}"
        return None

    def get_active_variant_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        preferred_currency = self._get_preferred_currency(obj)
        if variant and variant.old_price is not None:
            from_currency = (variant.currency or obj.currency or 'RUB').upper()
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
                # Форматируем число, убирая лишние нули после запятой
                formatted_price = f"{variant.old_price}"
                if '.' in formatted_price:
                    formatted_price = formatted_price.rstrip('0').rstrip('.')
                return f"{formatted_price} {from_currency}"
            # Форматируем число, убирая лишние нули после запятой
            formatted_price = f"{variant.old_price}"
            if '.' in formatted_price:
                formatted_price = formatted_price.rstrip('0').rstrip('.')
            return f"{formatted_price} {from_currency}"
        return None

    def _get_preferred_currency(self, obj) -> str:
        request = self.context.get('request')
        preferred = None
        if request:
            preferred = request.headers.get('X-Currency') or request.query_params.get('currency')
        return (preferred or obj.currency or 'RUB').upper()

    def get_images(self, obj):
        """Галерея изображений. Объединяет изображения товара и текущего варианта.

        У вариативной мебели одна и та же картинка может храниться и в FurnitureProductImage,
        и в FurnitureVariantImage (наследие парсинга или ручные правки). Без дедупликации
        в API уходили два одинаковых слайда подряд.
        """
        request = self.context.get('request')
        ctx = {"request": request}

        variant = self._get_active_variant(obj)
        variant_rows: list = []
        if variant:
            variant_images = variant.images.all().order_by("sort_order")
            if variant_images.exists():
                variant_rows = FurnitureVariantImageSerializer(
                    variant_images, many=True, context=ctx
                ).data

        product_images = obj.images.all().order_by("sort_order")
        product_rows: list = []
        if product_images.exists():
            product_rows = FurnitureProductImageSerializer(
                product_images, many=True, context=ctx
            ).data

        # Сначала кадры варианта (источник истины по цвету), затем уникальные общие кадры товара
        ordered: list = []
        seen: set[str] = set()
        for row in variant_rows + product_rows:
            url = (row.get("image_url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            ordered.append(row)
        return ordered

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
        return FurnitureVariantSerializer(qs, many=True, context=self.context).data

    def get_default_variant_slug(self, obj):
        variant = self._get_default_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_slug(self, obj):
        variant = self._get_active_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_price(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            preferred_currency = self._get_preferred_currency(obj)
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
                pass
            return f"{variant.price} {from_currency}"
        if obj.price is None:
            return None
        preferred_currency = self._get_preferred_currency(obj)
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
            pass
        return f"{obj.price} {from_currency}"

    def get_active_variant_currency(self, obj):
        variant = self._get_active_variant(obj)
        preferred_currency = self._get_preferred_currency(obj)
        if variant and variant.price is not None:
            from_currency = (variant.currency or obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                currency_converter.convert_price(
                    Decimal(variant.price),
                    from_currency,
                    preferred_currency,
                    apply_margin=True,
                )
                return preferred_currency
            except Exception:
                return from_currency
        if obj.price is None:
            return None
        from_currency = (obj.currency or 'RUB').upper()
        if preferred_currency == from_currency:
            return from_currency
        try:
            from .utils.currency_converter import currency_converter
            currency_converter.convert_price(
                Decimal(obj.price),
                from_currency,
                preferred_currency,
                apply_margin=True,
            )
            return preferred_currency
        except Exception:
            return from_currency

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
# СЕРИАЛИЗАТОРЫ ДЛЯ УКРАШЕНИЙ
# ============================================================================

class JewelryProductTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = JewelryProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class JewelryProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = JewelryProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class JewelryVariantSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = JewelryVariantSize
        fields = ['id', 'size_value', 'size_unit', 'size_type', 'size_display', 'is_available', 'stock_quantity', 'sort_order']


class JewelryVariantImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = JewelryVariantImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class JewelryVariantSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    name_en = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    description_en = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    sizes = JewelryVariantSizeSerializer(many=True, read_only=True)
    price = serializers.SerializerMethodField()
    old_price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()

    class Meta:
        model = JewelryVariant
        fields = [
            'id', 'name', 'name_en', 'description', 'description_en', 'slug', 'color', 'material', 'gender',
            'price', 'old_price', 'currency',
            'is_available', 'stock_quantity',
            'main_image', 'images', 'sizes',
            'sku', 'barcode', 'gtin', 'mpn',
            'is_active', 'sort_order',
        ]
        read_only_fields = ['id', 'slug', 'sort_order']

    def get_name(self, obj):
        return _get_variant_draft_title(obj, "ru") or obj.name

    def get_name_en(self, obj):
        return _get_variant_draft_title(obj, "en") or obj.name_en

    def get_description(self, obj):
        return _get_variant_localized_description(obj, "ru")

    def get_description_en(self, obj):
        return _get_variant_localized_description(obj, "en")

    def _get_preferred_currency(self, request):
        default = 'RUB'
        if not request:
            return default
        preferred = request.headers.get('X-Currency') or request.query_params.get('currency')
        if preferred:
            return preferred.upper()
        if getattr(request, 'user', None) and request.user.is_authenticated:
             uc = getattr(request.user, 'currency', None)
             if uc: return uc.upper()
        lang = getattr(request, 'LANGUAGE_CODE', None)
        return {'en': 'USD', 'ru': 'RUB'}.get(lang, default)

    def get_price(self, obj):
        if obj.price is None:
            return None
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        from_currency = (obj.currency or 'RUB').upper()
        
        try:
            from .utils.currency_converter import currency_converter
            _, _, price_with_margin = currency_converter.convert_price(
                Decimal(str(obj.price)),
                from_currency,
                preferred_currency,
                apply_margin=True,
            )
            return price_with_margin
        except Exception:
            pass
        return obj.price

    def get_old_price(self, obj):
        if obj.old_price is None:
            return None
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        from_currency = (obj.currency or 'RUB').upper()
        
        try:
            from .utils.currency_converter import currency_converter
            _, _, price_with_margin = currency_converter.convert_price(
                Decimal(str(obj.old_price)),
                from_currency,
                preferred_currency,
                apply_margin=True,
            )
            return price_with_margin
        except Exception:
            pass
        return obj.old_price

    def get_currency(self, obj):
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        if obj.price is not None:
             from_currency = (obj.currency or 'RUB').upper()
             try:
                from .utils.currency_converter import currency_converter
                currency_converter.convert_price(
                    Decimal(str(obj.price)),
                    from_currency,
                    preferred_currency,
                    apply_margin=True,
                )
                return preferred_currency
             except Exception:
                 pass
        return obj.currency or 'RUB'

    def get_images(self, obj):
        gallery = getattr(obj, "images", None)
        if not gallery:
            return []
        return JewelryVariantImageSerializer(gallery.all().order_by("sort_order"), many=True).data


class JewelryProductSerializer(_LocalizedSeoMethodsMixin, serializers.ModelSerializer):
    """Сериализатор для товаров украшений (с вариантами и размерами)."""
    product_type = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
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
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    translations = JewelryProductTranslationSerializer(many=True, read_only=True)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()

    class Meta:
        model = JewelryProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency', 'jewelry_type', 'material', 'metal_purity', 'stone_type', 'carat_weight', 'gender',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url', 'video_url',
            'images', 'dynamic_attributes', 'product_type',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_product_type(self, obj):
        return 'jewelry'

    def get_main_image_url(self, obj):
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
        gallery = getattr(obj, "images", None)
        if gallery:
            main_img = gallery.filter(is_main=True).first()
            if main_img:
                file_url = _resolve_file_url(getattr(main_img, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(main_img.image_url, request)
            first_img = gallery.first()
            if first_img:
                file_url = _resolve_file_url(getattr(first_img, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(first_img.image_url, request)
        return None

    def get_video_url(self, obj):
        """URL видео товара (Jewelry). Приоритет загруженному файлу."""
        request = self.context.get('request')
        
        # 1. Приоритет файлу в JewelryProduct
        file_field = getattr(obj, "main_video_file", None)
        if file_field and getattr(file_field, "name", None):
            resolved = _resolve_video_file_url(file_field, request)
            if resolved:
                return resolved

        # 2. Проверка shadow-копии (Product)
        base_product = getattr(obj, "base_product", None)
        if base_product:
            file_field = getattr(base_product, "main_video_file", None)
            if file_field and getattr(file_field, "name", None):
                resolved = _resolve_video_file_url(file_field, request)
                if resolved:
                    return resolved

        # 3. Фолбэк на внешний URL
        raw_url = getattr(obj, "video_url", None) or ""
        if raw_url and raw_url.strip():
            path_lower = raw_url.split("?")[0].lower()
            if not path_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg")):
                return _resolve_media_url(raw_url, request)
                
        return None

    def _get_preferred_currency(self, obj) -> str:
        """Определяет валюту: X-Currency -> query param -> user.currency -> язык -> default."""
        request = self.context.get('request')
        default = (obj.currency or 'RUB').upper()
        if not request:
            return default
        preferred = request.headers.get('X-Currency') or request.query_params.get('currency')
        if preferred:
            return preferred.upper()
        if getattr(request, 'user', None) and request.user.is_authenticated:
            uc = getattr(request.user, 'currency', None)
            if uc:
                return uc.upper()
        lang = getattr(request, 'LANGUAGE_CODE', None)
        return {'en': 'USD', 'ru': 'RUB'}.get(lang, default)

    def _convert_price(self, amount, from_currency: str, to_currency: str):
        """Конвертация цены с маржой. Возвращает (price_with_margin, to_currency) или (amount, from_currency) при ошибке."""
        if amount is None:
            return None, from_currency
        from_currency = (from_currency or 'RUB').upper()
        to_currency = (to_currency or 'RUB').upper()
        if from_currency == to_currency:
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_with_margin = currency_converter.convert_price(
                    Decimal(str(amount)), from_currency, to_currency, apply_margin=True,
                )
                return price_with_margin, to_currency
            except Exception:
                return amount, from_currency
        try:
            from .utils.currency_converter import currency_converter
            _, _, price_with_margin = currency_converter.convert_price(
                Decimal(str(amount)), from_currency, to_currency, apply_margin=True,
            )
            return price_with_margin, to_currency
        except Exception:
            return amount, from_currency

    def get_price(self, obj):
        """Цена с конвертацией и маржой (для отображения на фронте)."""
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            preferred = self._get_preferred_currency(obj)
            price_val, curr = self._convert_price(
                variant.price, variant.currency or obj.currency, preferred
            )
            return float(price_val) if price_val is not None else None
        if obj.price is not None:
            preferred = self._get_preferred_currency(obj)
            price_val, _ = self._convert_price(obj.price, obj.currency, preferred)
            return float(price_val) if price_val is not None else None
        return None

    def get_currency(self, obj):
        """Валюта с учётом конвертации (предпочтительная валюта пользователя)."""
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            preferred = self._get_preferred_currency(obj)
            _, curr = self._convert_price(
                variant.price, variant.currency or obj.currency, preferred
            )
            return curr
        return self._get_preferred_currency(obj)

    def get_price_formatted(self, obj):
        """Цена с конвертацией и маржой (строка для отображения)."""
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            preferred = self._get_preferred_currency(obj)
            price_val, curr = self._convert_price(
                variant.price, variant.currency or obj.currency, preferred
            )
            return f"{price_val} {curr}" if price_val is not None else None
        if obj.price is not None:
            preferred = self._get_preferred_currency(obj)
            price_val, curr = self._convert_price(obj.price, obj.currency, preferred)
            return f"{price_val} {curr}" if price_val is not None else None
        return None

    def get_old_price_formatted(self, obj):
        """Старая цена с конвертацией и маржой."""
        variant = self._get_active_variant(obj)
        preferred = self._get_preferred_currency(obj)
        if variant and variant.old_price is not None:
            price_val, curr = self._convert_price(
                variant.old_price, variant.currency or obj.currency, preferred
            )
            return f"{price_val} {curr}" if price_val is not None else None
        if obj.old_price is not None:
            price_val, curr = self._convert_price(obj.old_price, obj.currency, preferred)
            return f"{price_val} {curr}" if price_val is not None else None
        return None

    def get_images(self, obj):
        variant = self._get_active_variant(obj)
        gallery = getattr(obj, "images", None)
        product_images = []
        if gallery:
            product_images = JewelryProductImageSerializer(
                gallery.all().order_by("sort_order"),
                many=True,
                context=self.context
            ).data
        variant_images = []
        if variant:
            variant_images = JewelryVariantImageSerializer(
                variant.images.all().order_by("sort_order"),
                many=True,
                context=self.context
            ).data
        if not product_images:
            return variant_images
        if not variant_images:
            return product_images
        seen = set()
        merged = []
        for item in product_images:
            url = item.get("image_url")
            if url:
                seen.add(url)
            merged.append(item)
        for item in variant_images:
            url = item.get("image_url")
            if url and url in seen:
                continue
            merged.append(item)
        return merged

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
        qs = variants.filter(is_active=True).order_by("sort_order", "id").prefetch_related("images", "sizes")
        return JewelryVariantSerializer(qs, many=True, context=self.context).data

    def get_default_variant_slug(self, obj):
        variant = self._get_default_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_slug(self, obj):
        variant = self._get_active_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_price(self, obj):
        """Цена активного варианта с конвертацией и маржой."""
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            preferred = self._get_preferred_currency(obj)
            price_val, curr = self._convert_price(
                variant.price, variant.currency or obj.currency, preferred
            )
            return f"{price_val} {curr}" if price_val is not None else None
        if obj.price is not None:
            preferred = self._get_preferred_currency(obj)
            price_val, curr = self._convert_price(obj.price, obj.currency, preferred)
            return f"{price_val} {curr}" if price_val is not None else None
        return None

    def get_active_variant_currency(self, obj):
        """Валюта активного варианта (после конвертации)."""
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            preferred = self._get_preferred_currency(obj)
            _, curr = self._convert_price(
                variant.price, variant.currency or obj.currency, preferred
            )
            return curr
        if obj.price is not None:
            preferred = self._get_preferred_currency(obj)
            _, curr = self._convert_price(obj.price, obj.currency, preferred)
            return curr
        return None

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

    def get_active_variant_old_price_formatted(self, obj):
        """Старая цена активного варианта с конвертацией и маржой."""
        variant = self._get_active_variant(obj)
        if variant and variant.old_price is not None:
            preferred = self._get_preferred_currency(obj)
            price_val, curr = self._convert_price(
                variant.old_price, variant.currency or obj.currency, preferred
            )
            return f"{price_val} {curr}" if price_val is not None else None
        return None

# ============================================================================
# СЕРИАЛИЗАТОРЫ ДЛЯ УСЛУГ
# ============================================================================

class ServiceImageSerializer(serializers.ModelSerializer):
    """Сериализатор для галереи изображений услуги."""
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ServiceImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        if obj.image_file:
            return obj.image_file.url
        return obj.image_url


class ServicePriceSerializer(serializers.ModelSerializer):
    """Сериализатор мультивалютных цен услуги."""
    class Meta:
        model = ServicePrice
        fields = [
            'base_currency', 'base_price',
            'rub_price', 'rub_price_with_margin',
            'usd_price', 'usd_price_with_margin',
            'kzt_price', 'kzt_price_with_margin',
            'eur_price', 'eur_price_with_margin',
            'try_price', 'try_price_with_margin',
            'usdt_price', 'usdt_price_with_margin',
        ]

class ServiceAttributeSerializer(serializers.ModelSerializer):
    """Сериализатор динамических атрибутов услуги."""

    key = serializers.ReadOnlyField(source='attribute_key.slug')
    key_display = serializers.ReadOnlyField(source='attribute_key.name')
    value = serializers.SerializerMethodField()

    class Meta:
        model = ServiceAttribute
        fields = ['id', 'key', 'key_display', 'value', 'sort_order']

    def get_value(self, obj):
        from django.utils import translation
        lang = translation.get_language()
        
        if lang == 'ru' and obj.value_ru:
            return obj.value_ru
        if lang == 'en' and obj.value_en:
            return obj.value_en
            
        return obj.value


class ServiceSerializer(serializers.ModelSerializer):
    """Сериализатор для услуг."""
    
    name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True)
    product_type = serializers.ReadOnlyField(default='uslugi')
    main_image_url = serializers.SerializerMethodField()
    main_video_url = serializers.SerializerMethodField()
    main_gif_url = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    translations = ServiceTranslationSerializer(many=True, read_only=True)
    images = ServiceImageSerializer(many=True, read_only=True)
    gallery = ServiceImageSerializer(source='images', many=True, read_only=True)
    prices_info = ServicePriceSerializer(source='price_info', read_only=True)
    service_attributes = ServiceAttributeSerializer(many=True, read_only=True)
    
    class Meta:
        model = Service
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'product_type',
            'price', 'price_formatted', 'currency', 'prices_info',
            'main_image', 'main_image_url', 'video_url', 'main_video_url', 'main_gif_url',
            'gallery', 'images',
            'service_attributes',
            'is_active', 'is_featured', 'created_at', 'updated_at', 'translations',
            'meta_title', 'meta_description', 'meta_keywords', 'og_title', 'og_description', 'og_image_url'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'product_type']
    
    def get_name(self, obj):
        """Локализованное название."""
        request = self.context.get('request')
        lang = getattr(request, 'LANGUAGE_CODE', 'en') if request else 'en'
        if lang == 'ru':
            return obj.name
        translation = obj.translations.filter(locale=lang).first()
        if translation and translation.name:
            return translation.name
        return obj.name

    def get_description(self, obj):
        """Локализованное описание."""
        request = self.context.get('request')
        lang = getattr(request, 'LANGUAGE_CODE', 'en') if request else 'en'
        if lang == 'ru':
            return obj.description
        translation = obj.translations.filter(locale=lang).first()
        if translation and translation.description:
            return translation.description
        return obj.description

    def get_main_image_url(self, obj):
        """URL главного изображения."""
        if obj.main_image_file:
            return obj.main_image_file.url
        return obj.main_image if obj.main_image else None

    def get_main_video_url(self, obj):
        """URL главного видео."""
        if obj.main_video_file:
            return obj.main_video_file.url
        return obj.video_url if obj.video_url else None

    def get_main_gif_url(self, obj):
        """URL GIF."""
        if obj.gif_file:
            return obj.gif_file.url
        return None

    def _get_preferred_currency(self, request):
        """Определяет предпочитаемую валюту."""
        default_currency = 'RUB'
        if not request:
            return default_currency
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
        language_currency_map = {'en': 'USD', 'ru': 'RUB'}
        return language_currency_map.get(language_code, default_currency)

    def get_price(self, obj):
        """Получает цену в предпочитаемой валюте."""
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        return obj.get_price(preferred_currency)

    def get_currency(self, obj):
        """Получает активную валюту."""
        request = self.context.get('request')
        return self._get_preferred_currency(request)

    def get_price_formatted(self, obj):
        """Форматированная цена в предпочитаемой валюте."""
        request = self.context.get('request')
        preferred_currency = self._get_preferred_currency(request)
        price = obj.get_price(preferred_currency)
        if price is not None:
            return f"{price} {preferred_currency}"
        return None


def _banner_api_language(context):
    """Язык ответа API: X-Language / Accept-Language (как у категорий)."""
    from django.utils import translation

    request = context.get("request")
    lang = getattr(request, "LANGUAGE_CODE", None) if request else None
    if not lang:
        lang = translation.get_language() or "ru"
    if isinstance(lang, str) and "-" in lang:
        lang = lang.split("-")[0]
    return lang if lang in ("ru", "en") else "ru"


def _translation_row_for_locale(translations_iter, lang):
    for t in translations_iter:
        if t.locale == lang:
            return t
    return None


def _resolve_banner_texts_for_lang(banner, lang):
    """Тексты баннера: перевод для locale, иначе поля модели."""
    if hasattr(banner, "_prefetched_objects_cache") and "translations" in banner._prefetched_objects_cache:
        trans_list = banner._prefetched_objects_cache["translations"]
    else:
        trans_list = list(banner.translations.all())
    tr = _translation_row_for_locale(trans_list, lang)

    def pick(attr):
        v = getattr(tr, attr, "") if tr else ""
        if v:
            return v
        return getattr(banner, attr, "") or ""

    return {
        "title": pick("title"),
        "description": pick("description"),
        "link_text": pick("link_text"),
    }


def _resolve_banner_media_texts_for_lang(media, lang, banner_resolved):
    """Тексты слайда: перевод → поля медиа → fallback с баннера."""
    if hasattr(media, "_prefetched_objects_cache") and "translations" in media._prefetched_objects_cache:
        trans_list = media._prefetched_objects_cache["translations"]
    else:
        trans_list = list(media.translations.all())
    tr = _translation_row_for_locale(trans_list, lang)

    def pick(m_attr, banner_key):
        v = getattr(tr, m_attr, "") if tr else ""
        if v:
            return v
        mv = getattr(media, m_attr, "") or ""
        if mv:
            return mv
        return (banner_resolved or {}).get(banner_key) or ""

    return {
        "title": pick("title", "title"),
        "description": pick("description", "description"),
        "link_text": pick("link_text", "link_text"),
    }


class BannerMediaSerializer(serializers.ModelSerializer):
    """Сериализатор для медиа-файлов баннера."""

    content_url = serializers.SerializerMethodField()
    content_mime_type = serializers.SerializerMethodField()
    file = serializers.SerializerMethodField()  # Алиас для content_url (мобильное приложение)
    title = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    link_text = serializers.SerializerMethodField()

    class Meta:
        model = BannerMedia
        fields = [
            'id', 'content_type', 'content_url', 'content_mime_type', 'file', 'sort_order',
            'link_url', 'title', 'description', 'link_text', 'created_at'
        ]
        read_only_fields = ['id', 'content_url', 'content_mime_type', 'file', 'title', 'description', 'link_text']
    
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
    
    def get_file(self, obj):
        """URL контента (алиас для мобильного приложения)."""
        return self.get_content_url(obj)
    
    def get_content_mime_type(self, obj):
        """Получить MIME-тип контента."""
        return obj.get_content_type_for_html()

    def get_title(self, obj):
        lang = _banner_api_language(self.context)
        br = self.context.get("banner_resolved") or _resolve_banner_texts_for_lang(obj.banner, lang)
        return _resolve_banner_media_texts_for_lang(obj, lang, br)["title"]

    def get_description(self, obj):
        lang = _banner_api_language(self.context)
        br = self.context.get("banner_resolved") or _resolve_banner_texts_for_lang(obj.banner, lang)
        return _resolve_banner_media_texts_for_lang(obj, lang, br)["description"]

    def get_link_text(self, obj):
        lang = _banner_api_language(self.context)
        br = self.context.get("banner_resolved") or _resolve_banner_texts_for_lang(obj.banner, lang)
        return _resolve_banner_media_texts_for_lang(obj, lang, br)["link_text"]


class BannerSerializer(serializers.ModelSerializer):
    """Сериализатор для баннеров."""

    title = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    link_text = serializers.SerializerMethodField()
    media_files = serializers.SerializerMethodField()

    class Meta:
        model = Banner
        fields = [
            'id', 'title', 'description', 'position', 'link_url', 'link_text',
            'is_active', 'sort_order', 'media_files'
        ]
        read_only_fields = ['title', 'description', 'link_text']

    def get_title(self, obj):
        return _resolve_banner_texts_for_lang(obj, _banner_api_language(self.context))["title"]

    def get_description(self, obj):
        return _resolve_banner_texts_for_lang(obj, _banner_api_language(self.context))["description"]

    def get_link_text(self, obj):
        return _resolve_banner_texts_for_lang(obj, _banner_api_language(self.context))["link_text"]

    def get_media_files(self, obj):
        """
        Получить отсортированные медиа-файлы баннера.
        ВАЖНО: порядок должен совпадать с тем, как их показывает админка.
        У модели BannerMedia в Meta уже задан ordering = ['banner', 'sort_order', 'id'],
        поэтому здесь не переопределяем сортировку и используем этот же порядок.
        """
        lang = _banner_api_language(self.context)
        banner_resolved = _resolve_banner_texts_for_lang(obj, lang)
        media = obj.media_files.all()
        ctx = {**self.context, "banner_resolved": banner_resolved}
        return BannerMediaSerializer(media, many=True, context=ctx).data


# ─────────────────────────────────────────────────────────────
#                       BOOK PRODUCT
# ─────────────────────────────────────────────────────────────

class BookProductTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов товаров-книг."""

    class Meta:
        model = BookProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class BookProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор для изображений товаров-книг."""

    image_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = BookProductImage
        fields = ['id', 'image_url', 'video_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if getattr(obj, "video_url", None) or getattr(obj, "video_file", None):
            return None
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)

    def get_video_url(self, obj):
        request = self.context.get('request')
        raw_url = getattr(obj, "video_url", None) or ""
        if raw_url:
            path_lower = raw_url.split("?")[0].lower()
            if not path_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg")):
                return _resolve_media_url(raw_url, request)
        file_url = _resolve_file_url(getattr(obj, "video_file", None), request)
        if file_url:
            return file_url
        return None


class BookProductSerializer(_LocalizedSeoMethodsMixin, serializers.ModelSerializer):
    """Сериализатор для товаров-книг (краткая информация)."""

    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
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
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    translations = BookProductTranslationSerializer(many=True, read_only=True)
    book_authors = ProductAuthorSerializer(many=True, read_only=True)
    book_genres = ProductGenreSerializer(many=True, read_only=True)
    base_product_id = serializers.IntegerField(read_only=True, source='base_product.id', default=None)
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
    main_video_url = serializers.SerializerMethodField()
    book_attributes = serializers.SerializerMethodField()
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    has_manual_main_image = serializers.BooleanField(read_only=True)
    # _domain_product_type на модели — атрибут класса, не поле БД.
    product_type = serializers.SerializerMethodField(read_only=True)

    def get_book_attributes(self, obj):
        data = getattr(obj.base_product, 'external_data', None) or {}
        attrs = data.get('attributes') if isinstance(data, dict) else {}
        attrs = attrs if isinstance(attrs, dict) else {}
        out = {}
        if attrs.get('format'):
            out['format'] = str(attrs['format']).strip()
        if attrs.get('thickness_mm') is not None and str(attrs.get('thickness_mm')).strip():
            out['thickness_mm'] = str(attrs['thickness_mm']).strip()
        return out

    def get_product_type(self, obj):
        raw = getattr(type(obj), '_domain_product_type', None)
        if raw:
            return str(raw).replace('_', '-')
        pt = getattr(obj, 'product_type', None)
        if pt is not None and str(pt).strip() != '':
            return str(pt).replace('_', '-')
        return None

    class Meta:
        model = BookProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency',
            'isbn', 'publisher', 'publication_date', 'pages', 'language',
            'cover_type', 'rating', 'reviews_count', 'is_bestseller',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url',
            'video_url', 'main_video_url', 'has_manual_main_image',
            'images',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'book_authors', 'book_genres', 'book_attributes', 'dynamic_attributes', 'product_type',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations',
            'base_product_id',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def _get_active_variant(self, obj):
        """Получает активный вариант."""
        active_slug = self.context.get('active_variant_slug')
        if active_slug:
            variant = obj.book_variants.filter(slug=active_slug, is_active=True).first()
            if variant:
                return variant
        return obj.book_variants.filter(is_active=True).order_by('sort_order').first()

    def _get_preferred_currency(self, obj):
        request = self.context.get('request')
        if not request:
            return 'RUB'
        preferred = request.headers.get('X-Currency') or request.query_params.get('currency')
        if preferred:
            return preferred.upper()
        language_code = getattr(request, 'LANGUAGE_CODE', None)
        return {'en': 'USD', 'ru': 'RUB'}.get(language_code, 'RUB')

    def get_main_image_url(self, obj):
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
        return None

    def get_video_url(self, obj):
        """URL видео: как у ProductSerializer — сначала загруженный файл, потом внешний URL.

        Иначе при наличии main_video_file на base_product отдавался бы сырой umma-land .mov,
        который в <video> часто не играет (CORS/хостинг), хотя копия в хранилище уже есть.
        """
        request = self.context.get('request')

        def _url_for_book_entity(entity):
            if not entity:
                return None
            ff = getattr(entity, "main_video_file", None)
            if ff and getattr(ff, "name", None):
                resolved = _resolve_video_file_url(ff, request)
                if resolved:
                    return resolved
            raw = getattr(entity, "video_url", None) or ""
            if raw and raw.strip():
                path_lower = raw.split("?")[0].lower()
                if not path_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg")):
                    return _resolve_media_url(raw, request)
            return None

        # Сначала base_product: скачанное видео сидит на shadow Product, у BookProduct часто только внешний URL.
        base = getattr(obj, "base_product", None)
        for entity in (base, obj):
            u = _url_for_book_entity(entity)
            if u:
                return u
        return None

    def get_main_video_url(self, obj):
        """Тот же URL, что video_url (для фронта: main_video_url || video_url)."""
        return self.get_video_url(obj)

    def get_price(self, obj):
        """Конвертированная цена с маржой (вариант или базовый товар)."""
        variant = self._get_active_variant(obj)
        price_val = variant.price if (variant and variant.price is not None) else obj.price
        if price_val is None:
            return None
        preferred = self._get_preferred_currency(obj)
        src_currency = (variant.currency if variant and variant.currency else obj.currency) or 'RUB'
        from_currency = src_currency.upper()
        try:
            from .utils.currency_converter import currency_converter
            _, _, price_m = currency_converter.convert_price(Decimal(price_val), from_currency, preferred, apply_margin=True)
            return price_m
        except Exception:
            pass
        return price_val

    def get_currency(self, obj):
        """Валюта цены (preferred если конвертация прошла)."""
        variant = self._get_active_variant(obj)
        price_val = variant.price if (variant and variant.price is not None) else obj.price
        preferred = self._get_preferred_currency(obj)
        src_currency = (variant.currency if variant and variant.currency else obj.currency) or 'RUB'
        from_currency = src_currency.upper()
        if price_val is not None:
            try:
                from .utils.currency_converter import currency_converter
                currency_converter.convert_price(Decimal(price_val), from_currency, preferred, apply_margin=True)
                return preferred
            except Exception:
                pass
        return from_currency

    def get_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            preferred = self._get_preferred_currency(obj)
            from_currency = (variant.currency or obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_m = currency_converter.convert_price(Decimal(variant.price), from_currency, preferred, apply_margin=True)
                return f"{price_m} {preferred}"
            except Exception:
                pass
            return f"{variant.price} {from_currency}"
        if obj.price is not None:
            preferred = self._get_preferred_currency(obj)
            from_currency = (obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_m = currency_converter.convert_price(Decimal(obj.price), from_currency, preferred, apply_margin=True)
                return f"{price_m} {preferred}"
            except Exception:
                pass
            return f"{obj.price} {from_currency}"
        return None

    def get_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        price_val = (variant.old_price if variant and variant.old_price is not None else obj.old_price)
        cur = (variant.currency if variant else None) or obj.currency or 'RUB'
        if price_val is not None:
            preferred = self._get_preferred_currency(obj)
            from_currency = cur.upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_m = currency_converter.convert_price(Decimal(price_val), from_currency, preferred, apply_margin=True)
                return f"{price_m} {preferred}"
            except Exception:
                pass
            formatted = f"{price_val}"
            if '.' in formatted:
                formatted = formatted.rstrip('0').rstrip('.')
            return f"{formatted} {from_currency}"
        return None

    def get_images(self, obj):
        images_qs = obj.images.all()
        base = getattr(obj, "base_product", None)

        # Фильтруем превью-видео, которые парсер складывает в external_data.attributes.video_posters
        if base and isinstance(getattr(base, "external_data", None), dict):
            attrs = base.external_data.get("attributes") or {}
            if isinstance(attrs, dict):
                video_posters = attrs.get("video_posters") or []
                if isinstance(video_posters, (list, tuple)):
                    poster_urls = [u for u in video_posters if isinstance(u, str) and u]
                    if poster_urls:
                        images_qs = images_qs.exclude(image_url__in=poster_urls)

                # Дополнительный хак: UmmaLand-книги с видео.
                # Лишнее превью обычно последним кадром галереи, но учитываем только товары с видео.
                source = attrs.get("source") or base.external_data.get("source")
                raw_video = attrs.get("video_url") or base.external_data.get("video_url")
                has_video = bool(raw_video or getattr(base, "video_url", None))
                if (
                    has_video
                    and isinstance(source, str)
                    and "umma-land.com" in source
                ):
                    ordered = list(images_qs.order_by("sort_order", "id"))
                    if len(ordered) >= 2:
                        last = ordered[-1]
                        images_qs = images_qs.exclude(pk=last.pk)

        product_images = BookProductImageSerializer(images_qs, many=True, context=self.context).data
        variant = self._get_active_variant(obj)
        if variant:
            variant_images = BookVariantImageSerializer(variant.images.all(), many=True, context=self.context).data
            return product_images + variant_images
        return product_images

    def get_variants(self, obj):
        return BookVariantSerializer(obj.book_variants.filter(is_active=True).order_by('sort_order'), many=True, context=self.context).data

    def get_default_variant_slug(self, obj):
        v = obj.book_variants.filter(is_active=True).order_by('sort_order').first()
        return v.slug if v else None

    def get_active_variant_slug(self, obj):
        v = self._get_active_variant(obj)
        return v.slug if v else None

    def get_active_variant_price(self, obj):
        v = self._get_active_variant(obj)
        if v and v.price is not None:
            preferred = self._get_preferred_currency(obj)
            from_currency = (v.currency or obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_m = currency_converter.convert_price(Decimal(v.price), from_currency, preferred, apply_margin=True)
                return str(price_m)
            except Exception:
                pass
            return str(v.price)
        return None

    def get_active_variant_currency(self, obj):
        v = self._get_active_variant(obj)
        if v:
            preferred = self._get_preferred_currency(obj)
            return preferred
        return None

    def get_active_variant_stock_quantity(self, obj):
        v = self._get_active_variant(obj)
        return v.stock_quantity if v else None

    def get_active_variant_main_image_url(self, obj):
        v = self._get_active_variant(obj)
        if not v:
            return None
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(v, "main_image_file", None), request)
        if file_url:
            return file_url
        if v.main_image:
            return _resolve_media_url(v.main_image, request)
        v_main = v.images.filter(is_main=True).first()
        if v_main:
            file_url = _resolve_file_url(getattr(v_main, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(v_main.image_url, request)
        return None

    def get_active_variant_old_price_formatted(self, obj):
        v = self._get_active_variant(obj)
        if v and v.old_price is not None:
            preferred = self._get_preferred_currency(obj)
            from_currency = (v.currency or obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_m = currency_converter.convert_price(Decimal(v.old_price), from_currency, preferred, apply_margin=True)
                return f"{price_m} {preferred}"
            except Exception:
                pass
            formatted = f"{v.old_price}"
            if '.' in formatted:
                formatted = formatted.rstrip('0').rstrip('.')
            return f"{formatted} {from_currency}"
        return None

# ─────────────────────────────────────────────────────────────
#                     PERFUMERY PRODUCT
# ─────────────────────────────────────────────────────────────

class PerfumeryProductTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов парфюмерии."""

    class Meta:
        model = PerfumeryProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class PerfumeryProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор для изображений парфюмерии."""

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = PerfumeryProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class PerfumeryVariantImageSerializer(serializers.ModelSerializer):
    """Сериализатор для изображений варианта парфюмерии."""

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = PerfumeryVariantImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class PerfumeryVariantSerializer(serializers.ModelSerializer):
    """Сериализатор для вариантов парфюмерии."""

    name = serializers.SerializerMethodField()
    name_en = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    description_en = serializers.SerializerMethodField()
    images = PerfumeryVariantImageSerializer(many=True, read_only=True)

    class Meta:
        model = PerfumeryVariant
        fields = [
            'id', 'slug', 'name', 'name_en', 'description', 'description_en', 'volume',
            'price', 'old_price', 'currency',
            'is_available', 'stock_quantity',
            'main_image', 'images',
            'sku', 'barcode',
            'external_id', 'external_url', 'external_data',
            'is_active', 'sort_order',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'sort_order', 'created_at', 'updated_at']

    def get_name(self, obj):
        return _get_variant_draft_title(obj, "ru") or obj.name

    def get_name_en(self, obj):
        return _get_variant_draft_title(obj, "en") or obj.name_en

    def get_description(self, obj):
        return _get_variant_localized_description(obj, "ru")

    def get_description_en(self, obj):
        return _get_variant_localized_description(obj, "en")


class PerfumeryProductSerializer(_LocalizedSeoMethodsMixin, serializers.ModelSerializer):
    """Сериализатор для товаров парфюмерии (краткая информация)."""

    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
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
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    translations = PerfumeryProductTranslationSerializer(many=True, read_only=True)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    base_product_id = serializers.IntegerField(read_only=True, source='base_product.id', default=None)
    product_type = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PerfumeryProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted',
            'currency',
            'volume', 'fragrance_type', 'fragrance_family', 'gender',
            'top_notes', 'heart_notes', 'base_notes',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url',
            'images', 'dynamic_attributes', 'product_type',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations',
            'base_product_id',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_product_type(self, obj):
        raw = getattr(type(obj), '_domain_product_type', None)
        return str(raw).replace('_', '-') if raw else None

    def _get_active_variant(self, obj):
        active_slug = self.context.get('active_variant_slug')
        if active_slug:
            variant = obj.variants.filter(slug=active_slug, is_active=True).first()
            if variant:
                return variant
        return obj.variants.filter(is_active=True).order_by('sort_order').first()

    def _get_preferred_currency(self, obj):
        request = self.context.get('request')
        if not request:
            return 'RUB'
        preferred = request.headers.get('X-Currency') or request.query_params.get('currency')
        if preferred:
            return preferred.upper()
        language_code = getattr(request, 'LANGUAGE_CODE', None)
        return {'en': 'USD', 'ru': 'RUB'}.get(language_code, 'RUB')

    def get_price(self, obj):
        """Конвертированная цена с маржой: берём из активного варианта или из самого товара."""
        variant = self._get_active_variant(obj)
        price_val = variant.price if (variant and variant.price is not None) else obj.price
        if price_val is None:
            return None
        preferred = self._get_preferred_currency(obj)
        src_currency = (variant.currency if variant and variant.currency else obj.currency) or 'RUB'
        from_currency = src_currency.upper()
        try:
            from .utils.currency_converter import currency_converter
            _, _, price_m = currency_converter.convert_price(Decimal(price_val), from_currency, preferred, apply_margin=True)
            return price_m
        except Exception:
            pass
        return price_val

    def get_currency(self, obj):
        """Валюта цены (preferred если конвертация прошла успешно)."""
        variant = self._get_active_variant(obj)
        price_val = variant.price if (variant and variant.price is not None) else obj.price
        preferred = self._get_preferred_currency(obj)
        src_currency = (variant.currency if variant and variant.currency else obj.currency) or 'RUB'
        from_currency = src_currency.upper()
        if price_val is not None:
            try:
                from .utils.currency_converter import currency_converter
                currency_converter.convert_price(Decimal(price_val), from_currency, preferred, apply_margin=True)
                return preferred
            except Exception:
                pass
        return from_currency

    def get_main_image_url(self, obj):
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
        return None

    def get_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            preferred = self._get_preferred_currency(obj)
            from_currency = (variant.currency or obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_m = currency_converter.convert_price(Decimal(variant.price), from_currency, preferred, apply_margin=True)
                return f"{price_m} {preferred}"
            except Exception:
                pass
            return f"{variant.price} {from_currency}"
        if obj.price is not None:
            preferred = self._get_preferred_currency(obj)
            from_currency = (obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_m = currency_converter.convert_price(Decimal(obj.price), from_currency, preferred, apply_margin=True)
                return f"{price_m} {preferred}"
            except Exception:
                pass
            return f"{obj.price} {from_currency}"
        return None

    def get_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        price_val = (variant.old_price if variant and variant.old_price is not None else obj.old_price)
        cur = (variant.currency if variant else None) or obj.currency or 'RUB'
        if price_val is not None:
            preferred = self._get_preferred_currency(obj)
            from_currency = cur.upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_m = currency_converter.convert_price(Decimal(price_val), from_currency, preferred, apply_margin=True)
                return f"{price_m} {preferred}"
            except Exception:
                pass
            formatted = f"{price_val}"
            if '.' in formatted:
                formatted = formatted.rstrip('0').rstrip('.')
            return f"{formatted} {from_currency}"
        return None

    def get_images(self, obj):
        product_images = PerfumeryProductImageSerializer(obj.images.all(), many=True, context=self.context).data
        variant = self._get_active_variant(obj)
        if variant:
            variant_images = PerfumeryVariantImageSerializer(variant.images.all(), many=True, context=self.context).data
            return product_images + variant_images
        return product_images

    def get_variants(self, obj):
        return PerfumeryVariantSerializer(obj.variants.filter(is_active=True).order_by('sort_order'), many=True, context=self.context).data

    def get_default_variant_slug(self, obj):
        v = obj.variants.filter(is_active=True).order_by('sort_order').first()
        return v.slug if v else None

    def get_active_variant_slug(self, obj):
        v = self._get_active_variant(obj)
        return v.slug if v else None

    def get_active_variant_price(self, obj):
        v = self._get_active_variant(obj)
        if v and v.price is not None:
            preferred = self._get_preferred_currency(obj)
            from_currency = (v.currency or obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_m = currency_converter.convert_price(Decimal(v.price), from_currency, preferred, apply_margin=True)
                return str(price_m)
            except Exception:
                pass
            return str(v.price)
        return None

    def get_active_variant_currency(self, obj):
        v = self._get_active_variant(obj)
        if v:
            preferred = self._get_preferred_currency(obj)
            return preferred
        return None

    def get_active_variant_stock_quantity(self, obj):
        v = self._get_active_variant(obj)
        return v.stock_quantity if v else None

    def get_active_variant_main_image_url(self, obj):
        v = self._get_active_variant(obj)
        if not v:
            return None
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(v, "main_image_file", None), request)
        if file_url:
            return file_url
        if v.main_image:
            return _resolve_media_url(v.main_image, request)
        v_main = v.images.filter(is_main=True).first()
        if v_main:
            file_url = _resolve_file_url(getattr(v_main, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(v_main.image_url, request)
        return None

    def get_active_variant_old_price_formatted(self, obj):
        v = self._get_active_variant(obj)
        if v and v.old_price is not None:
            preferred = self._get_preferred_currency(obj)
            from_currency = (v.currency or obj.currency or 'RUB').upper()
            try:
                from .utils.currency_converter import currency_converter
                _, _, price_m = currency_converter.convert_price(Decimal(v.old_price), from_currency, preferred, apply_margin=True)
                return f"{price_m} {preferred}"
            except Exception:
                pass
            formatted = f"{v.old_price}"
            if '.' in formatted:
                formatted = formatted.rstrip('0').rstrip('.')
            return f"{formatted} {from_currency}"
        return None

# ─────────────────────────────────────────────────────────────
#                 ПРОСТЫЕ ДОМЕНЫ (Волна 2)
# ─────────────────────────────────────────────────────────────

# ─── Базовый миксин для простых доменов (без вариантов) ───

class _SimpleDomainMixin(_LocalizedSeoMethodsMixin, serializers.Serializer):
    """Общие поля и методы для доменных ModelSerializer.

    Важно: наследуемся от serializers.Serializer, чтобы SerializerMetaclass
    заполнил _declared_fields — иначе поля миксина (в т.ч. product_type) не
    попадают в дочерний ModelSerializer и DRF пытается взять их с модели.
    """

    main_image_url = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()

    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()
    # _domain_product_type на модели — атрибут класса, не поле БД; CharField(source=...) ломает ModelSerializer.
    product_type = serializers.SerializerMethodField(read_only=True)

    def get_product_type(self, obj):
        raw = getattr(type(obj), '_domain_product_type', None)
        if raw:
            return str(raw).replace('_', '-')
        pt = getattr(obj, 'product_type', None)
        if pt is not None and str(pt).strip() != '':
            return str(pt).replace('_', '-')
        return None

    def _get_preferred_currency(self, obj):
        request = self.context.get('request')
        default_currency = 'RUB'
        if not request:
            return default_currency
            
        preferred_currency = request.headers.get('X-Currency') or request.query_params.get('currency')
        if preferred_currency:
            return preferred_currency.upper()
            
        if getattr(request, 'user', None) and request.user.is_authenticated:
            user_currency = getattr(request.user, 'currency', None)
            if user_currency:
                return user_currency.upper()

        language_code = getattr(request, 'LANGUAGE_CODE', None)
        return {'en': 'USD', 'ru': 'RUB'}.get(language_code, default_currency)

    def get_main_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "main_image_file", None), request)
        if file_url:
            return file_url
        if obj.main_image:
            return _resolve_media_url(obj.main_image, request)
        img = obj.gallery_images.filter(is_main=True).first() or obj.gallery_images.first()
        if img:
            file_url = _resolve_file_url(getattr(img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(img.image_url, request)

        # Fallback to base product
        base = getattr(obj, "base_product", None)
        if base:
            file_url = _resolve_file_url(getattr(base, "main_image_file", None), request)
            if file_url:
                return file_url
            if base.main_image:
                return _resolve_media_url(base.main_image, request)
            b_img = base.images.filter(is_main=True).first() or base.images.first()
            if b_img:
                file_url = _resolve_file_url(getattr(b_img, "image_file", None), request)
                if file_url:
                    return file_url
                return _resolve_media_url(b_img.image_url, request)
        return None

    def get_price(self, obj):
        if obj.price is None:
            return None
        preferred = self._get_preferred_currency(obj)
        from_currency = (obj.currency or 'RUB').upper()
        try:
            from .utils.currency_converter import currency_converter
            _, _, price_m = currency_converter.convert_price(Decimal(obj.price), from_currency, preferred, apply_margin=True)
            return price_m
        except Exception:
            pass
        return obj.price

    def get_currency(self, obj):
        preferred = self._get_preferred_currency(obj)
        from_currency = (obj.currency or 'RUB').upper()
        if obj.price is not None:
            try:
                from .utils.currency_converter import currency_converter
                currency_converter.convert_price(Decimal(obj.price), from_currency, preferred, apply_margin=True)
                return preferred
            except Exception:
                pass
        return from_currency

    def get_price_formatted(self, obj):
        if obj.price is None:
            return None
        preferred = self._get_preferred_currency(obj)
        from_currency = (obj.currency or 'RUB').upper()
        try:
            from .utils.currency_converter import currency_converter
            _, _, price_m = currency_converter.convert_price(Decimal(obj.price), from_currency, preferred, apply_margin=True)
            return f"{price_m} {preferred}"
        except Exception:
            pass
        return f"{obj.price} {from_currency}"

    def get_old_price_formatted(self, obj):
        if obj.old_price is None:
            return None
        preferred = self._get_preferred_currency(obj)
        from_currency = (obj.currency or 'RUB').upper()
        try:
            from .utils.currency_converter import currency_converter
            _, _, price_m = currency_converter.convert_price(Decimal(obj.old_price), from_currency, preferred, apply_margin=True)
            return f"{price_m} {preferred}"
        except Exception:
            pass
        formatted = f"{obj.old_price}"
        if '.' in formatted:
            formatted = formatted.rstrip('0').rstrip('.')
        return f"{formatted} {from_currency}"

    def get_images(self, obj):
        from_context = self.context
        imgs = list(obj.gallery_images.all())
        image_serializer = self._image_serializer_class
        
        # Fallback to base product images if domain gallery is empty
        if not imgs:
            base = getattr(obj, "base_product", None)
            if base:
                # Используем базовый сериализатор изображений для общих изображений Product
                return ProductImageSerializer(base.images.all(), many=True, context=from_context).data
                
        return image_serializer(imgs, many=True, context=from_context).data

# ─── МЕДИКАМЕНТЫ ───

class MedicineProductTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicineProductTranslation
        fields = [
            'locale', 'name', 'description', 'usage_instructions',
            'side_effects', 'contraindications', 'storage_conditions', 'indications',
            'dosage_form', 'active_ingredient', 'volume', 'origin_country',
            *TRANSLATION_SEO_FIELDS,
        ]


class MedicineProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = MedicineProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class MedicineProductSerializer(_SimpleDomainMixin, serializers.ModelSerializer):
    _image_serializer_class = MedicineProductImageSerializer

    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    translations = MedicineProductTranslationSerializer(many=True, read_only=True)
    base_product_id = serializers.IntegerField(read_only=True, source='base_product.id', default=None)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()
    
    usage_instructions = serializers.SerializerMethodField()
    side_effects = serializers.SerializerMethodField()
    contraindications = serializers.SerializerMethodField()
    storage_conditions = serializers.SerializerMethodField()
    indications = serializers.SerializerMethodField()
    special_notes = serializers.SerializerMethodField()

    dosage_form = serializers.SerializerMethodField()
    active_ingredient = serializers.SerializerMethodField()
    volume = serializers.SerializerMethodField()
    origin_country = serializers.SerializerMethodField()
    administration_route = serializers.SerializerMethodField()
    shelf_life = serializers.SerializerMethodField()
    sgk_status = serializers.SerializerMethodField()
    prescription_type = serializers.SerializerMethodField()

    def _get_translation_field(self, obj, field_name, fallback_value=None):
        request = self.context.get('request')
        lang = 'ru'
        if request:
            lang = request.query_params.get('lang') or getattr(request, 'LANGUAGE_CODE', 'ru')
        
        # 1. Сначала ищем в текущей локали
        for t in obj.translations.all():
            if t.locale == lang:
                val = getattr(t, field_name, None)
                if val: return val
                
        # 2. Потом в RU (как дефолт)
        if lang != 'ru':
            for t in obj.translations.all():
                if t.locale == 'ru':
                    val = getattr(t, field_name, None)
                    if val: return val
                    
        # 3. Возвращаем fallback (поле из основной модели)
        return fallback_value

    def get_dosage_form(self, obj):
        return self._get_translation_field(obj, 'dosage_form', obj.dosage_form)

    def get_active_ingredient(self, obj):
        return self._get_translation_field(obj, 'active_ingredient', obj.active_ingredient)

    def get_volume(self, obj):
        return self._get_translation_field(obj, 'volume', obj.volume)

    def get_origin_country(self, obj):
        return self._get_translation_field(obj, 'origin_country', obj.origin_country)

    def get_usage_instructions(self, obj):
        return self._get_translation_field(obj, 'usage_instructions')

    def get_side_effects(self, obj):
        return self._get_translation_field(obj, 'side_effects')

    def get_contraindications(self, obj):
        return self._get_translation_field(obj, 'contraindications')

    def get_storage_conditions(self, obj):
        return self._get_translation_field(obj, 'storage_conditions', obj.storage_conditions)

    def get_indications(self, obj):
        return self._get_translation_field(obj, 'indications')

    def get_special_notes(self, obj):
        return self._get_translation_field(obj, 'special_notes', obj.special_notes)

    def get_administration_route(self, obj):
        return self._get_translation_field(obj, 'administration_route', obj.administration_route)

    def get_shelf_life(self, obj):
        return self._get_translation_field(obj, 'shelf_life', obj.shelf_life)

    def get_sgk_status(self, obj):
        return self._get_translation_field(obj, 'sgk_status', obj.sgk_status)

    def get_prescription_type(self, obj):
        return self._get_translation_field(obj, 'prescription_type', obj.prescription_type)

    class Meta:
        model = MedicineProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand', 'product_type',
            'price', 'price_formatted', 'old_price', 'old_price_formatted', 'currency',
            'dosage_form', 'active_ingredient', 'prescription_required', 'prescription_type',
            'volume', 'origin_country', 'administration_route', 'shelf_life',
            'barcode', 'atc_code', 'nfc_code', 'sgk_status', 'sgk_equivalent_code', 'sgk_active_ingredient_code', 'sgk_public_no', 'special_notes',
            'usage_instructions', 'side_effects', 'contraindications',
            'storage_conditions', 'indications',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url', 'images',
            'dynamic_attributes',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations',
            'base_product_id', 'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ─── БАДы ───

class SupplementProductTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplementProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class SupplementProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = SupplementProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class SupplementProductSerializer(_SimpleDomainMixin, serializers.ModelSerializer):
    _image_serializer_class = SupplementProductImageSerializer

    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    translations = SupplementProductTranslationSerializer(many=True, read_only=True)
    base_product_id = serializers.IntegerField(read_only=True, source='base_product.id', default=None)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()

    dosage_form = serializers.SerializerMethodField()
    active_ingredient = serializers.SerializerMethodField()
    serving_size = serializers.SerializerMethodField()

    def _get_translation_field(self, obj, field_name, fallback_value=None):
        request = self.context.get('request')
        lang = 'ru'
        if request:
            lang = request.query_params.get('lang') or getattr(request, 'LANGUAGE_CODE', 'ru')
        
        for t in obj.translations.all():
            if t.locale == lang:
                val = getattr(t, field_name, None)
                if val: return val
                
        if lang != 'ru':
            for t in obj.translations.all():
                if t.locale == 'ru':
                    val = getattr(t, field_name, None)
                    if val: return val
                    
        return fallback_value

    def get_dosage_form(self, obj):
        return self._get_translation_field(obj, 'dosage_form', obj.dosage_form)

    def get_active_ingredient(self, obj):
        return self._get_translation_field(obj, 'active_ingredient', obj.active_ingredient)

    def get_serving_size(self, obj):
        return self._get_translation_field(obj, 'serving_size', obj.serving_size)

    class Meta:
        model = SupplementProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted', 'currency',
            'dosage_form', 'active_ingredient', 'serving_size',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url', 'images', 'product_type',
            'dynamic_attributes',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations',
            'base_product_id',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ─── МЕДТЕХНИКА ───

class MedicalEquipmentProductTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalEquipmentProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class MedicalEquipmentProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = MedicalEquipmentProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class MedicalEquipmentProductSerializer(_SimpleDomainMixin, serializers.ModelSerializer):
    _image_serializer_class = MedicalEquipmentProductImageSerializer

    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    translations = MedicalEquipmentProductTranslationSerializer(many=True, read_only=True)
    base_product_id = serializers.IntegerField(read_only=True, source='base_product.id', default=None)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()

    class Meta:
        model = MedicalEquipmentProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted', 'currency',
            'equipment_type', 'warranty_months',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url', 'images',
            'dynamic_attributes',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations',
            'base_product_id', 'product_type',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ─── ПОСУДА ───

class TablewareProductTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TablewareProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class TablewareProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = TablewareProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class TablewareProductSerializer(_SimpleDomainMixin, serializers.ModelSerializer):
    _image_serializer_class = TablewareProductImageSerializer

    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    translations = TablewareProductTranslationSerializer(many=True, read_only=True)
    base_product_id = serializers.IntegerField(read_only=True, source='base_product.id', default=None)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()

    class Meta:
        model = TablewareProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted', 'currency',
            'material', 'set_pieces_count',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url', 'images',
            'dynamic_attributes',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations',
            'base_product_id', 'product_type',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ─── АКСЕССУАРЫ ───

class AccessoryProductTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessoryProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class AccessoryProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = AccessoryProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class AccessoryProductSerializer(_SimpleDomainMixin, serializers.ModelSerializer):
    _image_serializer_class = AccessoryProductImageSerializer

    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    translations = AccessoryProductTranslationSerializer(many=True, read_only=True)
    base_product_id = serializers.IntegerField(read_only=True, source='base_product.id', default=None)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()

    class Meta:
        model = AccessoryProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted', 'currency',
            'accessory_type', 'material',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url', 'images',
            'dynamic_attributes',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations',
            'base_product_id', 'product_type',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ─── БЛАГОВОНИЯ ───

class IncenseProductTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncenseProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class IncenseProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = IncenseProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "image_file", None), request)
        if file_url:
            return file_url
        return _resolve_media_url(obj.image_url, request)


class IncenseProductSerializer(_SimpleDomainMixin, serializers.ModelSerializer):
    _image_serializer_class = IncenseProductImageSerializer

    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    translations = IncenseProductTranslationSerializer(many=True, read_only=True)
    base_product_id = serializers.IntegerField(read_only=True, source='base_product.id', default=None)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()

    class Meta:
        model = IncenseProduct
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'price_formatted', 'old_price', 'old_price_formatted', 'currency',
            'scent_type', 'burn_time', 'weight_grams',
            'is_available', 'stock_quantity', 'main_image', 'main_image_url', 'images',
            'dynamic_attributes',
            'is_new', 'is_featured', 'created_at', 'updated_at', 'translations',
            'base_product_id', 'product_type',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

# ============================================================================
# SPORTS
# ============================================================================

class SportsProductTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SportsProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class SportsProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = SportsProductImage
        fields = ['id', 'image', 'is_main', 'created_at']

    def get_image(self, obj):
        request = self.context.get('request')
        return _resolve_file_url(obj.image_file, request)


class SportsVariantImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = SportsVariantImage
        fields = ['id', 'image', 'is_main', 'created_at']

    def get_image(self, obj):
        request = self.context.get('request')
        return _resolve_file_url(obj.image_file, request)


class SportsVariantSerializer(serializers.ModelSerializer):
    slug = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    images = SportsVariantImageSerializer(many=True, read_only=True)
    sizes = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()

    class Meta:
        model = SportsVariant
        fields = [
            'id', 'slug', 'color', 'size', 'sku', 'price', 'old_price',
            'currency', 'stock_quantity', 'is_available', 'images', 'sizes',
            'price_formatted', 'old_price_formatted'
        ]

    def get_slug(self, obj):
        return f"sports-variant-{obj.pk}"

    def get_currency(self, obj):
        return obj.product.currency

    def get_sizes(self, obj):
        if not obj.size:
            return []
        return [{
            "id": obj.pk,
            "size": obj.size,
            "is_available": obj.is_available,
            "stock_quantity": obj.stock_quantity,
            "sort_order": 0,
        }]

    def get_price_formatted(self, obj):
        if obj.price is None: return None
        return f"{obj.price} {obj.product.currency}"

    def get_old_price_formatted(self, obj):
        if obj.old_price is None: return None
        return f"{obj.old_price} {obj.product.currency}"


class SportsProductSerializer(_SimpleDomainMixin, serializers.ModelSerializer):
    """Списковый сериализатор для спорттоваров."""
    variants = SportsVariantSerializer(many=True, read_only=True)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    main_image_url = serializers.SerializerMethodField()
    default_variant_slug = serializers.SerializerMethodField()
    active_variant_slug = serializers.SerializerMethodField()
    active_variant_price = serializers.SerializerMethodField()
    active_variant_currency = serializers.SerializerMethodField()
    active_variant_stock_quantity = serializers.SerializerMethodField()
    active_variant_main_image_url = serializers.SerializerMethodField()
    active_variant_old_price_formatted = serializers.SerializerMethodField()

    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()

    class Meta:
        model = SportsProduct
        fields = [
            'id', 'slug', 'name', 'price', 'old_price', 'currency', 
            'is_available', 'is_new', 'is_featured', 'main_image', 'main_image_url',
            'sport_type', 'equipment_type', 'product_type',
            'dynamic_attributes',
            'price_formatted', 'old_price_formatted',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
        ]

    def _get_default_variant(self, obj):
        return obj.variants.filter(is_available=True).order_by('id').first() or obj.variants.order_by('id').first()

    def _get_active_variant(self, obj):
        active_slug = self.context.get('active_variant_slug')
        if active_slug:
            match = obj.variants.filter(pk=str(active_slug).replace('sports-variant-', '')).first()
            if match:
                return match
        return self._get_default_variant(obj)

    def get_default_variant_slug(self, obj):
        variant = self._get_default_variant(obj)
        return SportsVariantSerializer().get_slug(variant) if variant else None

    def get_active_variant_slug(self, obj):
        variant = self._get_active_variant(obj)
        return SportsVariantSerializer().get_slug(variant) if variant else None

    def get_active_variant_price(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return f"{variant.price} {obj.currency}"
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None

    def get_active_variant_currency(self, obj):
        return obj.currency

    def get_active_variant_stock_quantity(self, obj):
        variant = self._get_active_variant(obj)
        return variant.stock_quantity if variant else None

    def get_active_variant_main_image_url(self, obj):
        variant = self._get_active_variant(obj)
        if not variant:
            return None
        request = self.context.get('request')
        main_image = variant.images.filter(is_main=True).first() or variant.images.first()
        if not main_image:
            return None
        return _resolve_file_url(main_image.image_file, request)

    def get_active_variant_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.old_price is not None:
            return f"{variant.old_price} {obj.currency}"
        if obj.old_price is not None:
            return f"{obj.old_price} {obj.currency}"
        return None


class SportsProductDetailSerializer(_SimpleDomainMixin, serializers.ModelSerializer):
    """Детальный сериализатор для спорттоваров."""
    translations = SportsProductTranslationSerializer(many=True, read_only=True)
    images = SportsProductImageSerializer(many=True, read_only=True)
    variants = SportsVariantSerializer(many=True, read_only=True)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    
    main_image_url = serializers.SerializerMethodField()
    default_variant_slug = serializers.SerializerMethodField()
    active_variant_slug = serializers.SerializerMethodField()
    active_variant_price = serializers.SerializerMethodField()
    active_variant_currency = serializers.SerializerMethodField()
    active_variant_stock_quantity = serializers.SerializerMethodField()
    active_variant_main_image_url = serializers.SerializerMethodField()
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()

    
    similar_products = serializers.SerializerMethodField()

    class Meta:
        model = SportsProduct
        fields = [
            'id', 'slug', 'name', 'description', 
            'price', 'old_price', 'currency',
            'is_available', 'stock_quantity', 
            'is_new', 'is_featured', 
            'created_at', 'updated_at',
            'category', 'brand', 'main_image', 'main_image_url',
            'translations', 'images', 'variants', 'dynamic_attributes',
            'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'sport_type', 'equipment_type', 'material', 'product_type',
            'price_formatted', 'old_price_formatted', 
            'similar_products',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
        ]

    def get_similar_products(self, obj):
        return []

    def _get_default_variant(self, obj):
        return obj.variants.filter(is_available=True).order_by('id').first() or obj.variants.order_by('id').first()

    def _get_active_variant(self, obj):
        active_slug = self.context.get('active_variant_slug')
        if active_slug:
            match = obj.variants.filter(pk=str(active_slug).replace('sports-variant-', '')).first()
            if match:
                return match
        return self._get_default_variant(obj)

    def get_default_variant_slug(self, obj):
        variant = self._get_default_variant(obj)
        return SportsVariantSerializer().get_slug(variant) if variant else None

    def get_active_variant_slug(self, obj):
        variant = self._get_active_variant(obj)
        return SportsVariantSerializer().get_slug(variant) if variant else None

    def get_active_variant_price(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return f"{variant.price} {obj.currency}"
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None

    def get_active_variant_currency(self, obj):
        return obj.currency

    def get_active_variant_stock_quantity(self, obj):
        variant = self._get_active_variant(obj)
        return variant.stock_quantity if variant else None

    def get_active_variant_main_image_url(self, obj):
        variant = self._get_active_variant(obj)
        if not variant:
            return None
        request = self.context.get('request')
        main_image = variant.images.filter(is_main=True).first() or variant.images.first()
        if not main_image:
            return None
        return _resolve_file_url(main_image.image_file, request)

    def get_active_variant_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.old_price is not None:
            return f"{variant.old_price} {obj.currency}"
        if obj.old_price is not None:
            return f"{obj.old_price} {obj.currency}"
        return None


# ============================================================================
# AUTO PARTS
# ============================================================================

class AutoPartProductTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutoPartProductTranslation
        fields = ['locale', 'name', 'description', *TRANSLATION_SEO_FIELDS]


class AutoPartProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = AutoPartProductImage
        fields = ['id', 'image', 'is_main', 'created_at']

    def get_image(self, obj):
        request = self.context.get('request')
        return _resolve_file_url(obj.image_file, request)


class AutoPartVariantImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = AutoPartVariantImage
        fields = ['id', 'image', 'is_main', 'created_at']

    def get_image(self, obj):
        request = self.context.get('request')
        return _resolve_file_url(obj.image_file, request)


class AutoPartVariantSerializer(serializers.ModelSerializer):
    slug = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    images = AutoPartVariantImageSerializer(many=True, read_only=True)

    class Meta:
        model = AutoPartVariant
        fields = [
            'id', 'slug', 'condition', 'sku', 'manufacturer', 'price', 'old_price',
            'currency', 'stock_quantity', 'is_available', 'images'
        ]

    def get_slug(self, obj):
        return f"auto-part-variant-{obj.pk}"

    def get_currency(self, obj):
        return obj.product.currency


class AutoPartProductSerializer(_SimpleDomainMixin, serializers.ModelSerializer):
    """Списковый сериализатор для автозапчастей."""
    variants = AutoPartVariantSerializer(many=True, read_only=True)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    main_image_url = serializers.SerializerMethodField()
    default_variant_slug = serializers.SerializerMethodField()
    active_variant_slug = serializers.SerializerMethodField()
    active_variant_price = serializers.SerializerMethodField()
    active_variant_currency = serializers.SerializerMethodField()
    active_variant_stock_quantity = serializers.SerializerMethodField()
    active_variant_main_image_url = serializers.SerializerMethodField()
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()

    class Meta:
        model = AutoPartProduct
        fields = [
            'id', 'slug', 'name', 'price', 'old_price', 'currency', 
            'is_available', 'is_new', 'is_featured', 'main_image', 'main_image_url',
            'part_number', 'car_brand', 'car_model', 'product_type',
            'dynamic_attributes',
            'price_formatted', 'old_price_formatted',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
        ]

    def _get_default_variant(self, obj):
        return obj.variants.filter(is_available=True).order_by('id').first() or obj.variants.order_by('id').first()

    def _get_active_variant(self, obj):
        active_slug = self.context.get('active_variant_slug')
        if active_slug:
            match = obj.variants.filter(pk=str(active_slug).replace('auto-part-variant-', '')).first()
            if match:
                return match
        return self._get_default_variant(obj)

    def get_default_variant_slug(self, obj):
        variant = self._get_default_variant(obj)
        return AutoPartVariantSerializer().get_slug(variant) if variant else None

    def get_active_variant_slug(self, obj):
        variant = self._get_active_variant(obj)
        return AutoPartVariantSerializer().get_slug(variant) if variant else None

    def get_active_variant_price(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return f"{variant.price} {obj.currency}"
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None

    def get_active_variant_currency(self, obj):
        return obj.currency

    def get_active_variant_stock_quantity(self, obj):
        variant = self._get_active_variant(obj)
        return variant.stock_quantity if variant else None

    def get_active_variant_main_image_url(self, obj):
        variant = self._get_active_variant(obj)
        if not variant:
            return None
        request = self.context.get('request')
        main_image = variant.images.filter(is_main=True).first() or variant.images.first()
        if not main_image:
            return None
        return _resolve_file_url(main_image.image_file, request)

    def get_active_variant_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.old_price is not None:
            return f"{variant.old_price} {obj.currency}"
        if obj.old_price is not None:
            return f"{obj.old_price} {obj.currency}"
        return None


class AutoPartProductDetailSerializer(_SimpleDomainMixin, serializers.ModelSerializer):
    """Детальный сериализатор для автозапчастей."""
    translations = AutoPartProductTranslationSerializer(many=True, read_only=True)
    images = AutoPartProductImageSerializer(many=True, read_only=True)
    variants = AutoPartVariantSerializer(many=True, read_only=True)
    dynamic_attributes = ProductDynamicAttributeSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    
    main_image_url = serializers.SerializerMethodField()
    default_variant_slug = serializers.SerializerMethodField()
    active_variant_slug = serializers.SerializerMethodField()
    active_variant_price = serializers.SerializerMethodField()
    active_variant_currency = serializers.SerializerMethodField()
    active_variant_stock_quantity = serializers.SerializerMethodField()
    active_variant_main_image_url = serializers.SerializerMethodField()
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    price_formatted = serializers.SerializerMethodField()
    old_price_formatted = serializers.SerializerMethodField()
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()
    meta_keywords = serializers.SerializerMethodField()
    og_title = serializers.SerializerMethodField()
    og_description = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()

    
    similar_products = serializers.SerializerMethodField()

    class Meta:
        model = AutoPartProduct
        fields = [
            'id', 'slug', 'name', 'description', 
            'price', 'old_price', 'currency',
            'is_available', 'stock_quantity', 
            'is_new', 'is_featured', 
            'created_at', 'updated_at',
            'category', 'brand', 'main_image', 'main_image_url',
            'translations', 'images', 'variants', 'dynamic_attributes',
            'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'part_number', 'car_brand', 'car_model', 'compatibility_years', 'product_type',
            'price_formatted', 'old_price_formatted', 
            'similar_products',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url',
        ]

    def get_similar_products(self, obj):
        return []

    def _get_default_variant(self, obj):
        return obj.variants.filter(is_available=True).order_by('id').first() or obj.variants.order_by('id').first()

    def _get_active_variant(self, obj):
        active_slug = self.context.get('active_variant_slug')
        if active_slug:
            match = obj.variants.filter(pk=str(active_slug).replace('auto-part-variant-', '')).first()
            if match:
                return match
        return self._get_default_variant(obj)

    def get_default_variant_slug(self, obj):
        variant = self._get_default_variant(obj)
        return AutoPartVariantSerializer().get_slug(variant) if variant else None

    def get_active_variant_slug(self, obj):
        variant = self._get_active_variant(obj)
        return AutoPartVariantSerializer().get_slug(variant) if variant else None

    def get_active_variant_price(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return f"{variant.price} {obj.currency}"
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None

    def get_active_variant_currency(self, obj):
        return obj.currency

    def get_active_variant_stock_quantity(self, obj):
        variant = self._get_active_variant(obj)
        return variant.stock_quantity if variant else None

    def get_active_variant_main_image_url(self, obj):
        variant = self._get_active_variant(obj)
        if not variant:
            return None
        request = self.context.get('request')
        main_image = variant.images.filter(is_main=True).first() or variant.images.first()
        if not main_image:
            return None
        return _resolve_file_url(main_image.image_file, request)

    def get_active_variant_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.old_price is not None:
            return f"{variant.old_price} {obj.currency}"
        if obj.old_price is not None:
            return f"{obj.old_price} {obj.currency}"
        return None

# ============================================================================
# ДОМЕН Headwear
# ============================================================================

from .models import (
    HeadwearProduct, HeadwearProductImage, HeadwearProductSize, HeadwearVariant,
    HeadwearVariantImage, HeadwearVariantSize,
    UnderwearProduct, UnderwearProductImage, UnderwearProductSize, UnderwearVariant,
    UnderwearVariantImage, UnderwearVariantSize,
    IslamicClothingProduct, IslamicClothingProductImage, IslamicClothingProductSize, IslamicClothingVariant,
    IslamicClothingVariantImage, IslamicClothingVariantSize
)

class HeadwearProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    class Meta:
        model = HeadwearProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image_file:
            return _resolve_file_url(obj.image_file, request)
        return _resolve_media_url(obj.image_url, request)

class HeadwearProductSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeadwearProductSize
        fields = ['id', 'size', 'is_available', 'stock_quantity', 'sort_order']

class HeadwearVariantImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = HeadwearVariantImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image_file:
            return _resolve_file_url(obj.image_file, request)
        return _resolve_media_url(obj.image_url, request)

class HeadwearVariantSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeadwearVariantSize
        fields = ['id', 'size', 'is_available', 'stock_quantity', 'sort_order']

class HeadwearVariantSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    name_en = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    description_en = serializers.SerializerMethodField()
    images = HeadwearVariantImageSerializer(many=True, read_only=True)
    sizes = HeadwearVariantSizeSerializer(many=True, read_only=True)
    main_image_url = serializers.SerializerMethodField()

    class Meta:
        model = HeadwearVariant
        fields = [
            'id', 'name', 'name_en', 'description', 'description_en', 'slug', 'color', 'size',
            'sku', 'barcode', 'gtin', 'mpn',
            'price', 'currency', 'old_price',
            'is_available', 'stock_quantity',
            'main_image', 'main_image_url',
            'external_id', 'external_url', 'external_data',
            'is_active', 'sort_order',
            'images', 'sizes',
        ]

    def get_name(self, obj):
        return _get_variant_draft_title(obj, "ru") or obj.name

    def get_name_en(self, obj):
        return _get_variant_draft_title(obj, "en") or obj.name_en

    def get_description(self, obj):
        return _get_variant_localized_description(obj, "ru")

    def get_description_en(self, obj):
        return _get_variant_localized_description(obj, "en")

    def get_main_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "main_image_file", None), request)
        if file_url:
            return file_url
        if obj.main_image:
            return _resolve_media_url(obj.main_image, request)
        img = obj.images.filter(is_main=True).first() or obj.images.first()
        if img:
            file_url = _resolve_file_url(getattr(img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(img.image_url, request)
        return None

class HeadwearProductSerializer(_SimpleDomainMixin, serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    brand_slug = serializers.CharField(source='brand.slug', read_only=True)
    
    main_image_url = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
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
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    
    dynamic_attributes = serializers.SerializerMethodField()
    sizes = HeadwearProductSizeSerializer(many=True, read_only=True)
    # Явно: при множественных переопределениях полей миксина надёжнее не полагаться только на merge.
    product_type = serializers.SerializerMethodField(read_only=True)

    _image_serializer_class = HeadwearProductImageSerializer

    class Meta:
        model = HeadwearProduct
        fields = [
            'id', 'base_product_id', 'name', 'slug', 'description', 'price', 'currency', 'old_price',
            'price_formatted', 'old_price_formatted', 'is_available', 'is_active',
            'stock_quantity', 'category', 'category_slug', 'category_name', 
            'brand', 'brand_name', 'brand_slug', 'main_image', 'main_image_url', 'images',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'size', 'color', 'video_url', 'sizes', 
            'dynamic_attributes', 'product_type',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url'
        ]

    def get_main_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "main_image_file", None), request)
        if file_url:
            return file_url
        if obj.main_image:
            return _resolve_media_url(obj.main_image, request)
        img = obj.images.filter(is_main=True).first() or obj.images.first()
        if img:
            file_url = _resolve_file_url(getattr(img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(img.image_url, request)
        return _SimpleDomainMixin.get_main_image_url(self, obj)

    def get_images(self, obj):
        from_context = self.context
        imgs = list(obj.images.all())
        image_serializer = self._image_serializer_class
        if not imgs:
            base = getattr(obj, "base_product", None)
            if base:
                return ProductImageSerializer(base.images.all(), many=True, context=from_context).data
        return image_serializer(imgs, many=True, context=from_context).data

    def get_dynamic_attributes(self, obj):
        try:
            return ProductDynamicAttributeSerializer(obj.dynamic_attributes.all(), many=True, context=self.context).data
        except Exception:
            return []

    def _get_default_variant(self, obj):
        return obj.variants.filter(is_active=True).order_by("sort_order", "id").first()

    def _get_active_variant(self, obj):
        active_slug = self.context.get("active_variant_slug")
        if active_slug:
            return obj.variants.filter(slug=active_slug, is_active=True).first()
        return self._get_default_variant(obj)

    def get_variants(self, obj):
        qs = obj.variants.filter(is_active=True).order_by("sort_order", "id").prefetch_related("images", "sizes")
        return HeadwearVariantSerializer(qs, many=True, context=self.context).data

    def get_default_variant_slug(self, obj):
        variant = self._get_default_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_slug(self, obj):
        variant = self._get_active_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_price(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return f"{variant.price} {variant.currency or obj.currency}"
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None

    def get_active_variant_currency(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return variant.currency or obj.currency
        return obj.currency

    def get_active_variant_stock_quantity(self, obj):
        variant = self._get_active_variant(obj)
        return variant.stock_quantity if variant else None

    def get_active_variant_main_image_url(self, obj):
        variant = self._get_active_variant(obj)
        if not variant:
            return None
        return HeadwearVariantSerializer(variant, context=self.context).data.get("main_image_url")

    def get_active_variant_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.old_price is not None:
            return f"{variant.old_price} {variant.currency or obj.currency}"
        if obj.old_price is not None:
            return f"{obj.old_price} {obj.currency}"
        return None

    def get_product_type(self, obj):
        return _SimpleDomainMixin.get_product_type(self, obj)


class UnderwearProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    class Meta:
        model = UnderwearProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image_file:
            return _resolve_file_url(obj.image_file, request)
        return _resolve_media_url(obj.image_url, request)

class UnderwearProductSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnderwearProductSize
        fields = ['id', 'size', 'is_available', 'stock_quantity', 'sort_order']

class UnderwearVariantImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = UnderwearVariantImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image_file:
            return _resolve_file_url(obj.image_file, request)
        return _resolve_media_url(obj.image_url, request)

class UnderwearVariantSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnderwearVariantSize
        fields = ['id', 'size', 'is_available', 'stock_quantity', 'sort_order']

class UnderwearVariantSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    name_en = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    description_en = serializers.SerializerMethodField()
    images = UnderwearVariantImageSerializer(many=True, read_only=True)
    sizes = UnderwearVariantSizeSerializer(many=True, read_only=True)
    main_image_url = serializers.SerializerMethodField()

    class Meta:
        model = UnderwearVariant
        fields = [
            'id', 'name', 'name_en', 'description', 'description_en', 'slug', 'color', 'size',
            'sku', 'barcode', 'gtin', 'mpn',
            'price', 'currency', 'old_price',
            'is_available', 'stock_quantity',
            'main_image', 'main_image_url',
            'external_id', 'external_url', 'external_data',
            'is_active', 'sort_order',
            'images', 'sizes',
        ]

    def get_name(self, obj):
        return _get_variant_draft_title(obj, "ru") or obj.name

    def get_name_en(self, obj):
        return _get_variant_draft_title(obj, "en") or obj.name_en

    def get_description(self, obj):
        return _get_variant_localized_description(obj, "ru")

    def get_description_en(self, obj):
        return _get_variant_localized_description(obj, "en")

    def get_main_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "main_image_file", None), request)
        if file_url:
            return file_url
        if obj.main_image:
            return _resolve_media_url(obj.main_image, request)
        img = obj.images.filter(is_main=True).first() or obj.images.first()
        if img:
            file_url = _resolve_file_url(getattr(img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(img.image_url, request)
        return None

class UnderwearProductSerializer(_SimpleDomainMixin, serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    brand_slug = serializers.CharField(source='brand.slug', read_only=True)
    
    main_image_url = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
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
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    
    dynamic_attributes = serializers.SerializerMethodField()
    sizes = UnderwearProductSizeSerializer(many=True, read_only=True)
    product_type = serializers.SerializerMethodField(read_only=True)

    _image_serializer_class = UnderwearProductImageSerializer

    class Meta:
        model = UnderwearProduct
        fields = [
            'id', 'base_product_id', 'name', 'slug', 'description', 'price', 'currency', 'old_price',
            'price_formatted', 'old_price_formatted', 'is_available', 'is_active',
            'stock_quantity', 'category', 'category_slug', 'category_name', 
            'brand', 'brand_name', 'brand_slug', 'main_image', 'main_image_url', 'images',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'size', 'color', 'video_url', 'sizes', 
            'dynamic_attributes', 'product_type',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url'
        ]

    def get_main_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "main_image_file", None), request)
        if file_url:
            return file_url
        if obj.main_image:
            return _resolve_media_url(obj.main_image, request)
        img = obj.images.filter(is_main=True).first() or obj.images.first()
        if img:
            file_url = _resolve_file_url(getattr(img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(img.image_url, request)
        return _SimpleDomainMixin.get_main_image_url(self, obj)

    def get_images(self, obj):
        from_context = self.context
        imgs = list(obj.images.all())
        image_serializer = self._image_serializer_class
        if not imgs:
            base = getattr(obj, "base_product", None)
            if base:
                return ProductImageSerializer(base.images.all(), many=True, context=from_context).data
        return image_serializer(imgs, many=True, context=from_context).data

    def get_dynamic_attributes(self, obj):
        try:
            return ProductDynamicAttributeSerializer(obj.dynamic_attributes.all(), many=True, context=self.context).data
        except Exception:
            return []

    def _get_default_variant(self, obj):
        return obj.variants.filter(is_active=True).order_by("sort_order", "id").first()

    def _get_active_variant(self, obj):
        active_slug = self.context.get("active_variant_slug")
        if active_slug:
            return obj.variants.filter(slug=active_slug, is_active=True).first()
        return self._get_default_variant(obj)

    def get_variants(self, obj):
        qs = obj.variants.filter(is_active=True).order_by("sort_order", "id").prefetch_related("images", "sizes")
        return UnderwearVariantSerializer(qs, many=True, context=self.context).data

    def get_default_variant_slug(self, obj):
        variant = self._get_default_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_slug(self, obj):
        variant = self._get_active_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_price(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return f"{variant.price} {variant.currency or obj.currency}"
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None

    def get_active_variant_currency(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return variant.currency or obj.currency
        return obj.currency

    def get_active_variant_stock_quantity(self, obj):
        variant = self._get_active_variant(obj)
        return variant.stock_quantity if variant else None

    def get_active_variant_main_image_url(self, obj):
        variant = self._get_active_variant(obj)
        if not variant:
            return None
        return UnderwearVariantSerializer(variant, context=self.context).data.get("main_image_url")

    def get_active_variant_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.old_price is not None:
            return f"{variant.old_price} {variant.currency or obj.currency}"
        if obj.old_price is not None:
            return f"{obj.old_price} {obj.currency}"
        return None

    def get_product_type(self, obj):
        return _SimpleDomainMixin.get_product_type(self, obj)


class IslamicClothingProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    class Meta:
        model = IslamicClothingProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image_file:
            return _resolve_file_url(obj.image_file, request)
        return _resolve_media_url(obj.image_url, request)

class IslamicClothingProductSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = IslamicClothingProductSize
        fields = ['id', 'size', 'is_available', 'stock_quantity', 'sort_order']

class IslamicClothingVariantImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = IslamicClothingVariantImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order', 'is_main']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image_file:
            return _resolve_file_url(obj.image_file, request)
        return _resolve_media_url(obj.image_url, request)

class IslamicClothingVariantSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = IslamicClothingVariantSize
        fields = ['id', 'size', 'is_available', 'stock_quantity', 'sort_order']

class IslamicClothingVariantSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    name_en = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    description_en = serializers.SerializerMethodField()
    images = IslamicClothingVariantImageSerializer(many=True, read_only=True)
    sizes = IslamicClothingVariantSizeSerializer(many=True, read_only=True)
    main_image_url = serializers.SerializerMethodField()

    class Meta:
        model = IslamicClothingVariant
        fields = [
            'id', 'name', 'name_en', 'description', 'description_en', 'slug', 'color', 'size',
            'sku', 'barcode', 'gtin', 'mpn',
            'price', 'currency', 'old_price',
            'is_available', 'stock_quantity',
            'main_image', 'main_image_url',
            'external_id', 'external_url', 'external_data',
            'is_active', 'sort_order',
            'images', 'sizes',
        ]

    def get_name(self, obj):
        return _get_variant_draft_title(obj, "ru") or obj.name

    def get_name_en(self, obj):
        return _get_variant_draft_title(obj, "en") or obj.name_en

    def get_description(self, obj):
        return _get_variant_localized_description(obj, "ru")

    def get_description_en(self, obj):
        return _get_variant_localized_description(obj, "en")

    def get_main_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "main_image_file", None), request)
        if file_url:
            return file_url
        if obj.main_image:
            return _resolve_media_url(obj.main_image, request)
        img = obj.images.filter(is_main=True).first() or obj.images.first()
        if img:
            file_url = _resolve_file_url(getattr(img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(img.image_url, request)
        return None

class IslamicClothingProductSerializer(_SimpleDomainMixin, serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    brand_slug = serializers.CharField(source='brand.slug', read_only=True)
    
    main_image_url = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
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
    active_variant_old_price_formatted = serializers.SerializerMethodField()
    
    dynamic_attributes = serializers.SerializerMethodField()
    sizes = IslamicClothingProductSizeSerializer(many=True, read_only=True)
    product_type = serializers.SerializerMethodField(read_only=True)

    _image_serializer_class = IslamicClothingProductImageSerializer

    class Meta:
        model = IslamicClothingProduct
        fields = [
            'id', 'base_product_id', 'name', 'slug', 'description', 'price', 'currency', 'old_price',
            'price_formatted', 'old_price_formatted', 'is_available', 'is_active',
            'stock_quantity', 'category', 'category_slug', 'category_name', 
            'brand', 'brand_name', 'brand_slug', 'main_image', 'main_image_url', 'images',
            'variants', 'default_variant_slug', 'active_variant_slug',
            'active_variant_price', 'active_variant_currency', 'active_variant_stock_quantity',
            'active_variant_main_image_url', 'active_variant_old_price_formatted',
            'size', 'color', 'video_url', 'sizes', 
            'dynamic_attributes', 'product_type',
            'meta_title', 'meta_description', 'meta_keywords',
            'og_title', 'og_description', 'og_image_url'
        ]

    def get_main_image_url(self, obj):
        request = self.context.get('request')
        file_url = _resolve_file_url(getattr(obj, "main_image_file", None), request)
        if file_url:
            return file_url
        if obj.main_image:
            return _resolve_media_url(obj.main_image, request)
        img = obj.images.filter(is_main=True).first() or obj.images.first()
        if img:
            file_url = _resolve_file_url(getattr(img, "image_file", None), request)
            if file_url:
                return file_url
            return _resolve_media_url(img.image_url, request)
        return _SimpleDomainMixin.get_main_image_url(self, obj)

    def get_images(self, obj):
        from_context = self.context
        imgs = list(obj.images.all())
        image_serializer = self._image_serializer_class
        if not imgs:
            base = getattr(obj, "base_product", None)
            if base:
                return ProductImageSerializer(base.images.all(), many=True, context=from_context).data
        return image_serializer(imgs, many=True, context=from_context).data

    def get_dynamic_attributes(self, obj):
        try:
            return ProductDynamicAttributeSerializer(obj.dynamic_attributes.all(), many=True, context=self.context).data
        except Exception:
            return []

    def _get_default_variant(self, obj):
        return obj.variants.filter(is_active=True).order_by("sort_order", "id").first()

    def _get_active_variant(self, obj):
        active_slug = self.context.get("active_variant_slug")
        if active_slug:
            return obj.variants.filter(slug=active_slug, is_active=True).first()
        return self._get_default_variant(obj)

    def get_variants(self, obj):
        qs = obj.variants.filter(is_active=True).order_by("sort_order", "id").prefetch_related("images", "sizes")
        return IslamicClothingVariantSerializer(qs, many=True, context=self.context).data

    def get_default_variant_slug(self, obj):
        variant = self._get_default_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_slug(self, obj):
        variant = self._get_active_variant(obj)
        return variant.slug if variant else None

    def get_active_variant_price(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return f"{variant.price} {variant.currency or obj.currency}"
        if obj.price is not None:
            return f"{obj.price} {obj.currency}"
        return None

    def get_active_variant_currency(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.price is not None:
            return variant.currency or obj.currency
        return obj.currency

    def get_active_variant_stock_quantity(self, obj):
        variant = self._get_active_variant(obj)
        return variant.stock_quantity if variant else None

    def get_active_variant_main_image_url(self, obj):
        variant = self._get_active_variant(obj)
        if not variant:
            return None
        return IslamicClothingVariantSerializer(variant, context=self.context).data.get("main_image_url")

    def get_active_variant_old_price_formatted(self, obj):
        variant = self._get_active_variant(obj)
        if variant and variant.old_price is not None:
            return f"{variant.old_price} {variant.currency or obj.currency}"
        if obj.old_price is not None:
            return f"{obj.old_price} {obj.currency}"
        return None

    def get_product_type(self, obj):
        return _SimpleDomainMixin.get_product_type(self, obj)
