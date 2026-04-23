"""API представления для каталога товаров."""

from typing import List
from decimal import Decimal
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import F, Exists, OuterRef, Subquery, Count, Q
from django.db.models.functions import Coalesce, Least
from django.db.models import Case, When
from django.http import HttpResponse, JsonResponse, Http404
from django.views.decorators.http import require_GET
from django.core.cache import cache
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import ValidationError as FavoriteResolveValidationError
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
import logging
import requests
import hashlib
import os

from api.authentication import JWTSafeAuthentication

logger = logging.getLogger(__name__)

from .models import (
    Category, Brand, Product, PriceHistory, Favorite, Author,
    ProductAttributeValue,
    ClothingProduct, ClothingVariant,
    ShoeProduct, ShoeVariant,
    ElectronicsProduct,
    FurnitureProduct, FurnitureVariant,
    JewelryProduct,
    BookProduct,
    PerfumeryProduct,
    MedicineProduct,
    SupplementProduct,
    MedicalEquipmentProduct,
    TablewareProduct,
    AccessoryProduct,
    IncenseProduct,
    SportsProduct,
    AutoPartProduct,
    Service,
    Banner, BannerMedia,
)
from .services import CatalogService
from .serializers import (
    CategorySerializer,
    BrandSerializer,
    ProductSerializer,
    ProductDetailSerializer,
    BookGenreSerializer,
    PriceHistorySerializer,
    FavoriteSerializer,
    AddToFavoriteSerializer,
    resolve_product_for_favorites_api,
    ClothingCategorySerializer,
    ClothingProductSerializer,
    ShoeCategorySerializer,
    ShoeProductSerializer,
    ElectronicsCategorySerializer,
    ElectronicsProductSerializer,
    FurnitureProductSerializer,
    JewelryProductSerializer,
    BookProductSerializer,
    PerfumeryProductSerializer,
    MedicineProductSerializer,
    SupplementProductSerializer,
    MedicalEquipmentProductSerializer,
    TablewareProductSerializer,
    AccessoryProductSerializer,
    IncenseProductSerializer,
    SportsProductSerializer,
    SportsProductDetailSerializer,
    AutoPartProductSerializer,
    AutoPartProductDetailSerializer,
    ServiceSerializer,
    BannerSerializer
)


def _get_category_ids_with_descendants(slugs: list[str]) -> set[int]:
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
        if not children:
            break
        all_ids.update(children)
        current_ids = children
    return all_ids


class SmartSlugLookupMixin:
    """
    Mixin для умного поиска объекта по slug.
    Поддерживает случаи, когда в БД слаг продублирован (напр. name-name),
    а фронтенд прислал очищенную (короткую) версию, и наоборот.
    Также обрабатывает доменные префиксы (напр. 'headwear-' + 'cap').
    """
    def get_object(self):
        queryset = self.get_queryset()
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        slug = self.kwargs.get(lookup_url_kwarg)
        
        if not slug:
            return super().get_object()

        try:
            # 1. Прямой поиск (как обычно)
            return queryset.get(**{self.lookup_field: slug})
        except queryset.model.DoesNotExist:
            # 2. Если слаг продублирован в БД (ABC-ABC), а пришел короткий (ABC)
            doubled_slug = f"{slug}-{slug}"
            try:
                return queryset.get(**{self.lookup_field: doubled_slug})
            except queryset.model.DoesNotExist:
                # 3. Если слаг "очищен" на фронте (отрезан префикс типа)
                # Попробуем добавить префикс типа товара (напр. 'headwear-' + 'cap')
                if hasattr(queryset.model, '_domain_product_type'):
                    # Убираем подчеркивания, как это делает фронт
                    prefix = f"{queryset.model._domain_product_type}-".lower().replace('_', '-')
                    if not slug.lower().startswith(prefix):
                        prefixed_slug = f"{prefix}{slug}"
                        try:
                            # Пробуем и префикс, и префикс + дубль
                            return queryset.get(**{self.lookup_field: prefixed_slug})
                        except queryset.model.DoesNotExist:
                            doubled_prefixed = f"{prefixed_slug}-{prefixed_slug}"
                            try:
                                return queryset.get(**{self.lookup_field: doubled_prefixed})
                            except queryset.model.DoesNotExist:
                                pass

                # 4. Если слаг продублирован в URL (ABC-ABC), а в БД он короткий (ABC)
                if '-' in slug:
                    parts = slug.split('-')
                    if len(parts) >= 2 and len(parts) % 2 == 0:
                        half = len(parts) // 2
                        if parts[:half] == parts[half:]:
                            short_slug = "-".join(parts[:half])
                            try:
                                return queryset.get(**{self.lookup_field: short_slug})
                            except queryset.model.DoesNotExist:
                                pass
                
                # 5. Если в URL префикс есть, а в базе его нет (экстремальный случай)
                if hasattr(queryset.model, '_domain_product_type'):
                    prefix = f"{queryset.model._domain_product_type}-".lower().replace('_', '-')
                    if slug.lower().startswith(prefix):
                        no_prefix_slug = slug[len(prefix):]
                        try:
                            return queryset.get(**{self.lookup_field: no_prefix_slug})
                        except queryset.model.DoesNotExist:
                            pass
                                
                # Если ничего не помогло - выбрасываем 404 через стандартный метод
                return super().get_object()


def _get_preferred_currency(request) -> str:
    preferred = None
    if request:
        preferred = request.headers.get('X-Currency') or request.query_params.get('currency')
    return (preferred or '').upper()


def _effective_selling_price_expr():
    """Эффективная цена для фильтра: при скидке (old_price > price) — цена со скидкой (min)."""
    return Case(
        When(old_price__isnull=False, old_price__gt=0, then=Least(F('price'), F('old_price'))),
        default=F('price'),
    )


def _resolve_price_filter_expression(queryset, request):
    """Выражение для фильтра по цене: итоговая цена в выбранной валюте (с маржой), fallback — эффективная базовая (со скидкой)."""
    preferred = _get_preferred_currency(request)
    if queryset.model is Product:
        effective = _effective_selling_price_expr()
        if preferred == 'USD':
            return Coalesce(F('final_price_usd'), F('price_info__usd_price_with_margin'), effective)
        if preferred == 'RUB':
            return Coalesce(F('final_price_rub'), F('price_info__rub_price_with_margin'), effective)
        if preferred == 'KZT':
            return Coalesce(F('price_info__kzt_price_with_margin'), effective)
        if preferred == 'EUR':
            return Coalesce(F('price_info__eur_price_with_margin'), effective)
        if preferred == 'TRY':
            return Coalesce(F('price_info__try_price_with_margin'), effective)
    return F('price')


def _parse_decimal(value):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        return None


def _apply_gender_filter(queryset, request, multi_param: bool = True):
    """Фильтр по полу: product.gender ИЛИ category.gender (e-commerce best practice)."""
    if multi_param:
        slugs = _parse_multi_param(request, 'gender')
    else:
        raw = request.query_params.get('gender')
        slugs = [raw] if raw and str(raw).strip() else []
    if not slugs:
        return queryset
    return queryset.filter(
        models.Q(gender__in=slugs) | models.Q(category__gender__in=slugs)
    )


def _parse_multi_param(request, param_name: str) -> list[str]:
    """Парсит query-параметр: поддерживает gender=women,men и gender[]=women&gender[]=men."""
    raw_list = request.query_params.getlist(param_name) or []
    if not raw_list:
        raw = request.query_params.get(param_name)
        if raw:
            raw_list = raw.split(',')
    return [v.strip().lower().replace('_', '-') for v in raw_list if v and str(v).strip()]


from django.db.models import Q

def _apply_availability_filter(queryset, request):
    in_stock = request.query_params.get('in_stock')
    is_available = request.query_params.get('is_available')
    
    if in_stock is not None:
        in_stock_val = str(in_stock).lower() in ('true', '1', 'yes')
        if in_stock_val:
            if hasattr(queryset.model, 'availability_status') and hasattr(queryset.model, 'stock_quantity'):
                # Require is_available=True AND either status=in_stock OR stock_quantity > 0
                queryset = queryset.filter(is_available=True).filter(Q(availability_status='in_stock') | Q(stock_quantity__gt=0))
            else:
                queryset = queryset.filter(is_available=True)
    elif is_available is not None:
        is_avail_val = str(is_available).lower() in ('true', '1', 'yes')
        queryset = queryset.filter(is_available=is_avail_val)
        
    availability_status = request.query_params.get('availability_status')
    if availability_status and hasattr(queryset.model, 'availability_status'):
        queryset = queryset.filter(availability_status=availability_status)
        
    return queryset

def _apply_price_filter(queryset, request):
    min_price_raw = request.query_params.get('min_price') or request.query_params.get('price_min')
    max_price_raw = request.query_params.get('max_price') or request.query_params.get('price_max')
    min_price = _parse_decimal(min_price_raw)
    max_price = _parse_decimal(max_price_raw)
    if not min_price and not max_price:
        return queryset
    if queryset.model is Product:
        price_expr = _resolve_price_filter_expression(queryset, request)
        queryset = queryset.annotate(_price_filter_value=price_expr)
        if min_price is not None:
            queryset = queryset.filter(_price_filter_value__gte=min_price)
        if max_price is not None:
            queryset = queryset.filter(_price_filter_value__lte=max_price)
        return queryset
    preferred = _get_preferred_currency(request)
    if not preferred or not hasattr(queryset.model, 'currency'):
        if min_price is not None:
            queryset = queryset.filter(price__gte=min_price)
        if max_price is not None:
            queryset = queryset.filter(price__lte=max_price)
        return queryset
    from .utils.currency_converter import currency_converter
    currencies = list(
        queryset.exclude(currency__isnull=True).values_list('currency', flat=True).distinct()
    )
    q = models.Q()
    for currency in currencies:
        currency_code = (currency or '').upper()
        if not currency_code:
            continue
        try:
            if currency_code == preferred:
                rate = Decimal('1')
            else:
                _, converted, _ = currency_converter.convert_price(
                    Decimal('1'), currency_code, preferred, apply_margin=False
                )
                rate = Decimal(str(converted))
            margin_rate = currency_converter._get_margin_rate(currency_code, preferred)
            margin_decimal = Decimal(str(margin_rate))
            denom = rate * (Decimal('1') + margin_decimal / Decimal('100'))
            if denom <= 0:
                continue
            sub = models.Q(currency=currency_code)
            if min_price is not None:
                sub &= models.Q(price__gte=(min_price / denom))
            if max_price is not None:
                sub &= models.Q(price__lte=(max_price / denom))
            q |= sub
        except Exception:
            continue
    if min_price is not None or max_price is not None:
        null_currency = models.Q(currency__isnull=True)
        if min_price is not None:
            null_currency &= models.Q(price__gte=min_price)
        if max_price is not None:
            null_currency &= models.Q(price__lte=max_price)
        q |= null_currency
    if q:
        return queryset.filter(q)
    return queryset


def _apply_is_new_filter(queryset, request, use_flag: bool = False):
    raw = request.query_params.get('is_new')
    if raw is None:
        raw = request.query_params.get('is_new[]') or request.query_params.get('isNew')
    if raw is None:
        return queryset
    is_new = str(raw).lower() in ('true', '1', 'yes', 'on')
    if not is_new:
        return queryset
    if use_flag and hasattr(queryset.model, 'is_new'):
        q = models.Q(is_new=True)
        if hasattr(queryset.model, 'created_at'):
            threshold = timezone.now() - timedelta(days=30)
            q |= models.Q(created_at__gte=threshold)
        if hasattr(queryset.model, 'publication_date'):
            threshold_date = timezone.now().date() - timedelta(days=30)
            q |= models.Q(publication_date__gte=threshold_date)
        return queryset.filter(q)
    if hasattr(queryset.model, 'created_at'):
        threshold = timezone.now() - timedelta(days=30)
        q = models.Q(created_at__gte=threshold)
        if hasattr(queryset.model, 'publication_date'):
            threshold_date = timezone.now().date() - timedelta(days=30)
            q |= models.Q(publication_date__gte=threshold_date)
        return queryset.filter(q)
    return queryset


def _apply_brand_filter(queryset, request):
    brand_ids_raw = request.query_params.getlist('brand_id') or request.query_params.getlist('brand_id[]')
    if not brand_ids_raw:
        return queryset
    try:
        brand_ids = [int(bid) for bid in brand_ids_raw if bid is not None and str(bid).strip() != '']
    except (ValueError, TypeError):
        return queryset
    if not brand_ids:
        return queryset
    other_brand_id = Brand.objects.filter(slug='other').values_list('id', flat=True).first()
    wants_other = 0 in brand_ids or (other_brand_id and other_brand_id in brand_ids)
    brand_ids = [bid for bid in brand_ids if bid > 0 and bid != other_brand_id]
    if wants_other and brand_ids:
        q_other = models.Q(brand__isnull=True)
        if other_brand_id:
            q_other |= models.Q(brand_id=other_brand_id)
        return queryset.filter(q_other | models.Q(brand_id__in=brand_ids))
    if wants_other:
        q_other = models.Q(brand__isnull=True)
        if other_brand_id:
            q_other |= models.Q(brand_id=other_brand_id)
        return queryset.filter(q_other)
    return queryset.filter(brand_id__in=brand_ids)


def _apply_attr_filters(queryset, request):
    """Фильтрация по динамическим атрибутам (attr_{slug}=value1,value2)."""
    params = request.query_params
    attr_params = {k: v for k, v in params.items() if k.startswith('attr_') and v}
    if not attr_params:
        return queryset
    model = queryset.model
    if not hasattr(model, 'dynamic_attributes'):
        return queryset
    ct = ContentType.objects.get_for_model(model)
    product_ids = list(queryset.values_list('id', flat=True))
    if not product_ids:
        return queryset
    for param_key, param_val in attr_params.items():
        slug = param_key[5:]  # убираем "attr_"
        if not slug:
            continue
        values = [s.strip() for s in param_val.split(',') if s.strip()]
        if not values:
            continue
        matching_ids = set(
            ProductAttributeValue.objects.filter(
                content_type=ct,
                object_id__in=product_ids,
                attribute_key__slug=slug,
            ).filter(
                models.Q(value__in=values) |
                models.Q(value_ru__in=values) |
                models.Q(value_en__in=values)
            ).values_list('object_id', flat=True).distinct()
        )
        product_ids = [pid for pid in product_ids if pid in matching_ids]
        if not product_ids:
            return queryset.none()
    return queryset.filter(id__in=product_ids)


class FacetedModelViewSetMixin:
    """Миксин для ViewSet'ов товаров: вычисление available_attributes и фильтр attr_*.
    ViewSet должен вызывать _apply_facet_filters(queryset) в конце своего get_queryset."""

    def _apply_facet_filters(self, queryset):
        """Применяет фильтр по attr_* к queryset. Вызывать в конце get_queryset."""
        return _apply_attr_filters(queryset, self.request)

    def _calculate_available_genders(self, queryset):
        """Вычисляет доступные значения пола в текущем queryset (product.gender | category.gender)."""
        model = queryset.model
        if not hasattr(model, 'gender') and 'category' not in [f.name for f in model._meta.get_fields()]:
            return []
        valid = {'men', 'women', 'unisex', 'kids'}
        seen = set()
        if hasattr(model, 'gender'):
            for v in queryset.exclude(gender__in=[None, '']).values_list('gender', flat=True).distinct():
                if v and str(v).strip().lower() in valid:
                    seen.add(str(v).strip().lower())
        if hasattr(model, 'category'):
            for v in queryset.exclude(category__gender__in=[None, '']).values_list('category__gender', flat=True).distinct():
                if v and str(v).strip().lower() in valid:
                    seen.add(str(v).strip().lower())
        return sorted(seen)

    def _calculate_available_attributes(self, queryset):
        """Вычисляет доступные атрибуты для текущего отфильтрованного queryset."""
        model = queryset.model
        if not hasattr(model, 'dynamic_attributes'):
            return []
        ct = ContentType.objects.get_for_model(model)
        product_ids = list(queryset.values_list('id', flat=True)[:5000])
        if not product_ids:
            return []
        from django.utils import translation
        lang = translation.get_language() or 'ru'
        if '-' in lang:
            lang = lang.split('-')[0]
        use_ru = lang.startswith('ru')
        qs = ProductAttributeValue.objects.filter(
            content_type=ct,
            object_id__in=product_ids,
        ).select_related('attribute_key').order_by('attribute_key__sort_order', 'attribute_key__slug')
        grouped: dict[str, set[str]] = {}
        key_names: dict[str, str] = {}
        for pav in qs:
            key_slug = pav.attribute_key.slug if pav.attribute_key else ''
            if not key_slug:
                continue
            if key_slug not in grouped:
                grouped[key_slug] = set()
                key_names[key_slug] = pav.attribute_key.name if pav.attribute_key else key_slug
            val = (pav.value_ru or pav.value) if use_ru else (pav.value_en or pav.value)
            if val:
                grouped[key_slug].add(val)
        return [
            {'key': k, 'name': key_names.get(k, k), 'values': sorted(grouped[k])}
            for k in sorted(grouped.keys())
        ]

    def _get_facet_queryset(self):
        """Возвращает queryset для расчета фасетов, игнорируя текущие фильтры по полу и динамическим атрибутам."""
        original_get = self.request._request.GET
        mutable_get = original_get.copy()
        
        keys_to_remove = []
        for key in mutable_get.keys():
            if key in ('gender', 'gender[]') or key.startswith('attr_'):
                keys_to_remove.append(key)
                
        for key in keys_to_remove:
            del mutable_get[key]
            
        try:
            self.request._request.GET = mutable_get
            qs = self.filter_queryset(self.get_queryset())
        finally:
            self.request._request.GET = original_get
            
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        # Получаем базовый queryset для фасетов, чтобы они не пропадали при выборе
        facet_queryset = self._get_facet_queryset()
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            data = self.get_paginated_response(serializer.data).data
            data['available_attributes'] = self._calculate_available_attributes(facet_queryset)
            data['available_genders'] = self._calculate_available_genders(facet_queryset)
            return Response(data)
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'available_attributes': self._calculate_available_attributes(facet_queryset),
            'available_genders': self._calculate_available_genders(facet_queryset),
        })


class StandardPagination(PageNumberPagination):
    """Стандартная пагинация для API."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class CategoryPagination(PageNumberPagination):
    """Пагинация для категорий: допускает больший page_size для полного дерева (услуги и др.)."""
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 500


class CategoryViewSet(SmartSlugLookupMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с категориями."""
    
    queryset = Category.objects.filter(is_active=True).select_related('category_type').prefetch_related('translations')
    serializer_class = CategorySerializer
    pagination_class = CategoryPagination

    def _parse_bool(self, value: str | None) -> bool | None:
        """Безопасно парсит булево из query-параметра."""
        if value is None:
            return None
        return value.lower() in ('true', '1', 'yes')

    def _parse_slug_list(self, param: str) -> list[str]:
        """Парсит список slug из query-параметров."""
        raw = self.request.query_params.get(param)
        if not raw:
            return []
        return [s.strip() for s in raw.split(',') if s.strip()]

    def _parse_int_list(self, param: str) -> list[int]:
        """Парсит список ID из query-параметров."""
        values = self.request.query_params.getlist(param) or self.request.query_params.getlist(f'{param}[]')
        result: list[int] = []
        for value in values:
            try:
                result.append(int(value))
            except (TypeError, ValueError):
                continue
        return result

    def get_queryset(self):
        """
        Фильтрует категории.

        Поддерживаемые параметры:
        - all=true               — вернуть все активные категории без ограничений.
        - top_level=true         — только корневые категории (parent is null).
        - slug / category_slug   — одна или несколько через запятую; вернёт указанную категорию и (по умолчанию) её дочерние.
        - include_children=false — если передан slug, можно отключить добавление детей.
        - parent_slug            — вернуть только детей указанного родителя (slug).
        - parent_id              — вернуть только детей указанного родителя (id).
        """
        base_qs = Category.objects.filter(is_active=True).select_related('category_type').prefetch_related('translations').order_by('sort_order', 'name')

        # Явный запрос "все категории"
        if self._parse_bool(self.request.query_params.get('all')) is True:
            return base_qs

        # Фильтр по parent_id / parent_slug
        parent_ids = self._parse_int_list('parent_id')
        parent_slugs = self._parse_slug_list('parent_slug')

        # Фильтр по slug (или category_slug)
        slug_list = self._parse_slug_list('slug') or self._parse_slug_list('category_slug')
        include_children = self._parse_bool(self.request.query_params.get('include_children'))
        if include_children is None:
            include_children = True  # по умолчанию берём детей, если указан slug

        # Если задан slug — возвращаем саму категорию и её потомков
        if slug_list:
            include_children = self._parse_bool(self.request.query_params.get('include_children'))
            if include_children is None:
                include_children = True
            
            if not include_children:
                return base_qs.filter(slug__in=slug_list)
            
            # Используем рекурсивный поиск ID
            all_ids = _get_category_ids_with_descendants(slug_list)
            return base_qs.filter(id__in=all_ids).order_by('sort_order', 'name')

        # Если задан parent — возвращаем только детей
        if parent_ids or parent_slugs:
            qs = base_qs
            if parent_ids:
                qs = qs.filter(parent_id__in=parent_ids)
            if parent_slugs:
                qs = qs.filter(parent__slug__in=parent_slugs)
            return qs

        # Если top_level=true — только корневые
        if self._parse_bool(self.request.query_params.get('top_level')) is True:
            return base_qs.filter(parent__isnull=True)

        # По умолчанию безопасно отдаём только корневые, чтобы не засорять фронт
        return base_qs.filter(parent__isnull=True)
    
    @extend_schema(
        summary="Получить список категорий",
        description="Возвращает активные категории с серверной фильтрацией",
        parameters=[
            OpenApiParameter(name="all", type=bool, required=False, description="Вернуть все активные категории без ограничений"),
            OpenApiParameter(name="top_level", type=bool, required=False, description="Только корневые категории"),
            OpenApiParameter(name="slug", type=str, required=False, description="Slug категории (или несколько через запятую)"),
            OpenApiParameter(name="category_slug", type=str, required=False, description="Алиас slug категории"),
            OpenApiParameter(name="include_children", type=bool, required=False, description="Добавлять ли дочерние при фильтре по slug (по умолчанию true)"),
            OpenApiParameter(name="parent_slug", type=str, required=False, description="Вернуть только детей категории с указанным slug"),
            OpenApiParameter(name="parent_id", type=int, required=False, description="Вернуть только детей категории с указанным ID"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary="Получить категорию по ID",
        description="Возвращает детальную информацию о категории"
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Скрываем описание и счетчики ТОЛЬКО для главной страницы
        if self.request.query_params.get('main_page') == 'true':
            context['hide_description'] = True
            context['hide_counts'] = True
        return context

    def children(self, request, pk=None):
        """Получить подкатегории."""
        category = self.get_object()
        children = Category.objects.filter(parent=category, is_active=True).select_related('category_type').prefetch_related('translations')
        serializer = self.get_serializer(children, many=True)
        return Response(serializer.data)


class BrandViewSet(SmartSlugLookupMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с брендами."""
    
    queryset = Brand.objects.filter(is_active=True).prefetch_related('translations')
    serializer_class = BrandSerializer
    pagination_class = StandardPagination

    PRODUCT_TYPE_ALIASES = {
        'supplements': 'supplements',
        'medical-equipment': 'medical_equipment',
        'medical_equipment': 'medical_equipment',
        'accessories': 'accessories',
        'medical-accessories': 'accessories',
        'medical_accessories': 'accessories',
        'furniture': 'furniture',
        'tableware': 'tableware',
        'jewelry': 'jewelry',
        'perfumery': 'perfumery',
        'underwear': 'underwear',
        'headwear': 'headwear',
        'books': 'books',
    }
    
    PRODUCT_MODEL_MAP = {
        'medicines': Product,
        'supplements': Product,
        'medical_equipment': Product,
        'tableware': Product,
        'accessories': Product,
        'jewelry': JewelryProduct,
        'perfumery': Product,
        'underwear': Product,
        'headwear': Product,
        'clothing': ClothingProduct,
        'shoes': ShoeProduct,
        'electronics': ElectronicsProduct,
        'furniture': FurnitureProduct,
        'books': Product,
    }

    PRODUCT_TYPE_CATEGORY_SLUGS = {
        # Для базовых типов (медицина/БАДы/медтехника/аксессуары) список slug задаётся при необходимости.
    }

    def _normalize_product_type(self, raw_type: str | None) -> str | None:
        """Нормализует тип товара (учитываем алиасы)."""
        if not raw_type:
            return None
        raw_type = raw_type.lower()
        return self.PRODUCT_TYPE_ALIASES.get(raw_type, raw_type)

    def _parse_id_list(self, param: str) -> list[int]:
        """Парсит список ID из query-параметров."""
        values = self.request.query_params.getlist(param) or self.request.query_params.getlist(f'{param}[]')
        result: list[int] = []
        for value in values:
            try:
                result.append(int(value))
            except (TypeError, ValueError):
                continue
        return result

    def _parse_slug_list(self, param: str) -> list[str]:
        """Парсит список slug из query-параметров."""
        value = self.request.query_params.get(param)
        if not value:
            return []
        return [slug.strip() for slug in value.split(',') if slug.strip()]

    def get_queryset(self):
        """Фильтрует бренды по типу товара/категории."""
        queryset = Brand.objects.filter(is_active=True).order_by('name')

        # Прямой фильтр по primary_category_slug
        primary_slugs = self._parse_slug_list('primary_category_slug')
        product_type = self._normalize_product_type(self.request.query_params.get('product_type'))
        normalized_primary_slugs = [s.replace('-', '_') for s in primary_slugs]
        if product_type == 'books' or 'books' in normalized_primary_slugs:
            return queryset.none()

        if primary_slugs:
            # Бренд подходит, если: slug в category_slugs ИЛИ (для обратной совместимости) primary_category_slug
            slugs_canonical = [s.strip().lower().replace('_', '-') for s in primary_slugs if s]
            q = models.Q(category_slugs__overlap=slugs_canonical) | models.Q(primary_category_slug__in=slugs_canonical)
            result = queryset.filter(q).distinct()
            if result.exists():
                return result.order_by('name')
            if not product_type:
                return result.order_by('name')

        if not product_type:
            return queryset

        product_model = self.PRODUCT_MODEL_MAP.get(product_type)
        if not product_model:
            return queryset

        product_qs = product_model.objects.filter(is_active=True, brand__isnull=False)
        if product_model is Product:
            product_qs = product_qs.filter(product_type=product_type)

        category_slugs_filter = self.PRODUCT_TYPE_CATEGORY_SLUGS.get(product_type)
        if category_slugs_filter and product_model is Product:
            product_qs = product_qs.filter(category__slug__in=category_slugs_filter)

        category_ids = self._parse_id_list('category_id')
        if category_ids:
            product_qs = product_qs.filter(category_id__in=category_ids)

        category_slugs = self._parse_slug_list('category_slug')
        if category_slugs:
            cat_ids = _get_category_ids_with_descendants(category_slugs)
            if cat_ids:
                product_qs = product_qs.filter(category_id__in=cat_ids)

        in_stock = self.request.query_params.get('in_stock')
        if in_stock and in_stock.lower() in ('true', '1', 'yes'):
            product_qs = product_qs.filter(is_available=True)

        brand_ids = product_qs.values_list('brand_id', flat=True).distinct()
        return queryset.filter(id__in=brand_ids).distinct()
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Скрываем счетчики ТОЛЬКО для главной страницы
        if self.request.query_params.get('main_page') == 'true':
            context['hide_counts'] = True
        return context

    @extend_schema(
        summary="Получить список брендов",
        description="Возвращает список активных брендов (можно фильтровать по типу товара или основной категории)",
        parameters=[
            OpenApiParameter(name="primary_category_slug", type=str, required=False, description="Основная категория бренда (slug или несколько через запятую, например furniture)"),
            OpenApiParameter(name="product_type", type=str, required=False, description="Тип товара для фильтра (medicines, supplements, shoes, clothing, electronics, furniture и т.д.)"),
            OpenApiParameter(name="category_id", type=int, required=False, description="ID категории для фильтрации по товарам"),
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории для фильтрации по товарам"),
            OpenApiParameter(name="in_stock", type=bool, required=False, description="Только бренды с товарами в наличии"),
        ],
    )
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        data = response.data
        primary_slugs = self._parse_slug_list('primary_category_slug')
        product_type = self._normalize_product_type(self.request.query_params.get('product_type'))
        if not product_type and primary_slugs:
            product_type = self._normalize_product_type(primary_slugs[0].replace('-', '_'))
        product_model = self.PRODUCT_MODEL_MAP.get(product_type) if product_type else None
        if not product_model:
            return response
        product_qs = product_model.objects.filter(
            is_active=True, brand__isnull=True, is_available=True
        )
        if product_model is Product and product_type:
            product_qs = product_qs.filter(product_type=product_type)
        category_slugs_filter = self.PRODUCT_TYPE_CATEGORY_SLUGS.get(product_type)
        if category_slugs_filter and product_model is Product:
            product_qs = product_qs.filter(category__slug__in=category_slugs_filter)
        category_ids = self._parse_id_list('category_id')
        if category_ids:
            product_qs = product_qs.filter(category_id__in=category_ids)
        category_slugs = self._parse_slug_list('category_slug')
        if category_slugs:
            cat_ids = _get_category_ids_with_descendants(category_slugs)
            if cat_ids:
                product_qs = product_qs.filter(category_id__in=cat_ids)
        other_count = product_qs.count()
        if other_count <= 0:
            return response
        primary_slug_value = primary_slugs[0] if primary_slugs else (product_type or '')
        if primary_slug_value:
            primary_slug_value = primary_slug_value.replace('_', '-')
        
        context = self.get_serializer_context()
        other_brand_obj = Brand.objects.filter(slug='other', is_active=True).prefetch_related('translations').first()
        if other_brand_obj:
            other_brand = BrandSerializer(other_brand_obj, context=context).data
            other_brand['products_count'] = other_count if not context.get('hide_counts') else None
            other_brand['primary_category_slug'] = primary_slug_value
        else:
            other_brand = {
                "id": 0,
                "name": "Другое",
                "slug": "other",
                "description": "",
                "logo": "",
                "website": "",
                "card_media_url": None,
                "primary_category_slug": primary_slug_value,
                "external_id": "",
                "is_active": True,
                "products_count": other_count if not context.get('hide_counts') else None,
                "translations": [
                    {"locale": "ru", "name": "Другое", "description": ""},
                    {"locale": "en", "name": "Other", "description": ""},
                ],
                "created_at": None,
                "updated_at": None,
            }
        if isinstance(data, list):
            if not any(isinstance(item, dict) and item.get('slug') == 'other' for item in data):
                data.append(other_brand)
        else:
            results = data.get('results')
            if isinstance(results, list) and not any(isinstance(item, dict) and item.get('slug') == 'other' for item in results):
                results.append(other_brand)
        return response
    
    @extend_schema(
        summary="Получить бренд по ID",
        description="Возвращает детальную информацию о бренде"
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class ProductViewSet(SmartSlugLookupMixin, FacetedModelViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с товарами."""
    
    # Теневые варианты исключены на уровне класса (защита от случаев когда get_queryset не вызывается)
    queryset = Product.objects.filter(is_active=True).exclude(
        models.Q(external_data__has_key='source_variant_id') |
        models.Q(external_data__has_key='source_variant_slug')
    )
    serializer_class = ProductSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'
    
    def get_object(self):
        """Умный поиск объекта по slug для базовой модели Product."""
        queryset = self.get_queryset()
        slug = self.kwargs.get(self.lookup_field)
        if not slug:
            return super().get_object()

        try:
            return queryset.get(slug=slug)
        except Product.DoesNotExist:
            # Fallback 1: В БД дубль (A-A), пришел короткий (A)
            doubled_slug = f"{slug}-{slug}"
            try:
                return queryset.get(slug=doubled_slug)
            except Product.DoesNotExist:
                # Fallback 2: В URL дубль (A-A), в БД короткий (A)
                if '-' in slug:
                    parts = slug.split('-')
                    if len(parts) >= 2 and len(parts) % 2 == 0:
                        half = len(parts) // 2
                        if parts[:half] == parts[half:]:
                            short_slug = "-".join(parts[:half])
                            try:
                                return queryset.get(slug=short_slug)
                            except Product.DoesNotExist:
                                pass
                from django.http import Http404
                raise Http404("Product not found.")
    
    def _normalize_ordering(self, ordering: str) -> str:
        """Преобразует формат сортировки из фронтенда в формат Django.
        
        Преобразует:
        - name_asc -> name
        - name_desc -> -name
        - price_asc -> price
        - price_desc -> -price
        - newest -> -created_at
        - popular -> -is_featured, -created_at
        """
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',  # Популярные = рекомендуемые товары
        }
        return ordering_map.get(ordering, ordering)
    
    def get_queryset(self):
        """Фильтрация товаров по параметрам."""
        queryset = Product.objects.filter(is_active=True)
        queryset = queryset.exclude(product_type='jewelry')
        # Универсально исключаем все теневые варианты (для любых product_type)
        queryset = queryset.exclude(
            models.Q(external_data__has_key='source_variant_id') |
            models.Q(external_data__has_key='source_variant_slug')
        )
        
        # Фильтр по категории (поддержка массивов)
        category_ids = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        if category_ids:
            try:
                category_ids = [int(cid) for cid in category_ids if cid]
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по slug категории (поддержка нескольких через запятую).
        # Включает товары из самой категории и всех её подкатегорий (descendants).
        # Дополнительно: товары без категории (category=None), но с product_type,
        # совпадающим с category_type корневой категории.
        # subcategory_slug приоритетнее category_slug (более узкий фильтр).
        category_slug = self.request.query_params.get('subcategory_slug') or self.request.query_params.get('category_slug')
        if category_slug:
            slugs = [s.strip() for s in category_slug.split(',') if s.strip()]
            if slugs:
                all_ids = _get_category_ids_with_descendants(slugs)
                cats = Category.objects.filter(slug__in=slugs, is_active=True).select_related('category_type')
                type_values = set()
                for c in cats:
                    if c.category_type_id:
                        ts = (c.category_type.slug or '').lower().replace('-', '_')
                        if ts:
                            type_values.add(ts)
                for s in slugs:
                    type_values.add(s.lower().replace('-', '_'))
                if all_ids or type_values:
                    from django.db.models import Q
                    q = Q()
                    if all_ids:
                        q |= Q(category_id__in=all_ids)
                    
                    # Если категория не найдена по слагам, но слаг совпадает с типом товара (напр. 'headwear')
                    # ищем товары этого типа без жесткой привязки к дереву категорий
                    for s in slugs:
                        pt = s.lower().replace('-', '_')
                        q |= Q(product_type=pt)
                        
                    if q:
                        queryset = queryset.filter(q)
        
        # Фильтр по бренду (поддержка массивов)
        queryset = _apply_brand_filter(queryset, self.request)
        
        # Фильтр по полу (product.gender | category.gender)
        queryset = _apply_gender_filter(queryset, self.request)
        
        # Фильтр по поиску
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Фильтр по цене
        queryset = _apply_price_filter(queryset, self.request)
        
        # Фильтр по типу товара
        product_type = self.request.query_params.get('product_type')
        if product_type:
            queryset = queryset.filter(product_type=product_type)
            
            if product_type == 'books':
                # Фильтр по автору (поддержка массивов)
                author_ids = self.request.query_params.getlist('author_id') or self.request.query_params.getlist('author_id[]')
                if author_ids:
                    try:
                        author_ids = [int(aid) for aid in author_ids if aid]
                        if author_ids:
                            queryset = queryset.filter(book_item__book_authors__author_id__in=author_ids)
                    except (ValueError, TypeError):
                        pass

                # Фильтр по жанру книги
                genre_ids = self.request.query_params.getlist('genre_id') or self.request.query_params.getlist('genre_id[]')
                if genre_ids:
                    try:
                        genre_ids = [int(gid) for gid in genre_ids if gid]
                        if genre_ids:
                            queryset = queryset.filter(book_item__book_genres__genre_id__in=genre_ids)
                    except (ValueError, TypeError):
                        pass

                # Фильтр по издательству
                publishers = self.request.query_params.get('publisher')
                if publishers:
                    publisher_list = [p.strip() for p in publishers.split(',') if p.strip()]
                    if publisher_list:
                        queryset = queryset.filter(book_item__publisher__in=publisher_list)

                # Фильтр по языку
                languages = self.request.query_params.get('language')
                if languages:
                    language_list = [l.strip() for l in languages.split(',') if l.strip()]
                    if language_list:
                        queryset = queryset.filter(book_item__language__in=language_list)

        # Фильтр по стране происхождения
        country_of_origin = self.request.query_params.get('country_of_origin')
        if country_of_origin:
            countries = [c.strip() for c in country_of_origin.split(',') if c.strip()]
            if countries:
                queryset = queryset.filter(country_of_origin__in=countries)
        
        queryset = _apply_availability_filter(queryset, self.request)
        queryset = _apply_is_new_filter(queryset, self.request, use_flag=True)
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)

        queryset = self._apply_facet_filters(queryset)
        # Prefetch для main_image_url и images (medicine, supplement, books, clothing и др.)
        queryset = queryset.prefetch_related(
            'images',
            'medicine_item__gallery_images',
            'supplement_item__gallery_images',
            'medical_equipment_item__gallery_images',
            'tableware_item__gallery_images',
            'accessory_item__gallery_images',
            'incense_item__gallery_images',
            'book_item__images',
            'clothing_item__images',
            'shoe_item__images',
            'jewelry_item__images',
            'electronics_item__images',
            'furniture_item__images',
            'perfumery_item__images',
            'sports_item__images',
            'auto_part_item__images',
        )
        return queryset
    
    def get_serializer_class(self):
        """Выбираем сериализатор в зависимости от действия."""
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductSerializer
    
    @extend_schema(
        summary="Получить список товаров",
        description="Возвращает список товаров с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_id", type=int, required=False, description="ID категории"),
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории (включая подкатегории)"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="min_price", type=float, required=False, description="Минимальная цена"),
            OpenApiParameter(name="max_price", type=float, required=False, description="Максимальная цена"),
            OpenApiParameter(name="is_available", type=bool, required=False, description="В наличии"),
            OpenApiParameter(name="is_new", type=bool, required=False, description="Новинки"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
                OpenApiParameter(name="product_type", type=str, required=False, description="Тип товара (например, medicines, clothing)"),
                OpenApiParameter(name="availability_status", type=str, required=False, description="Статус доступности (in_stock, backorder, preorder, out_of_stock, discontinued)"),
                OpenApiParameter(name="country_of_origin", type=str, required=False, description="Страна происхождения (можно через запятую)"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary="Получить товар по slug",
        description="Возвращает детальную информацию о товаре"
    )
    def retrieve(self, request, *args, **kwargs):
        product = self.get_object()
        external = getattr(product, "external_data", {}) or {}
        source_variant_id = external.get("source_variant_id")
        source_variant_slug = external.get("source_variant_slug")
        source_type = (external.get("source_type") or external.get("effective_type") or product.product_type or "").lower()

        if source_variant_id or source_variant_slug:
            if source_type == "clothing":
                qs = ClothingVariant.objects.filter(is_active=True)
                if source_variant_id:
                    qs = qs.filter(id=source_variant_id)
                if source_variant_slug:
                    qs = qs.filter(slug=source_variant_slug)
                if not qs.exists():
                    raise Http404()
            elif source_type == "shoes":
                qs = ShoeVariant.objects.filter(is_active=True)
                if source_variant_id:
                    qs = qs.filter(id=source_variant_id)
                if source_variant_slug:
                    qs = qs.filter(slug=source_variant_slug)
                if not qs.exists():
                    raise Http404()

        serializer = self.get_serializer(product)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=['get'],
        url_path=r'resolve/(?P<product_slug>[^/.]+)',
    )
    @extend_schema(
        summary='Единая резолюция товара или услуги по slug',
        description=(
            'Один запрос: поиск в generic Product, затем в доменных каталогах, затем в услугах. '
            'Тело payload совпадает с соответствующим detail. Query-параметры (например active_variant_slug) '
            'пробрасываются как у обычного retrieve.'
        ),
        parameters=[
            OpenApiParameter(
                name='product_slug',
                type=str,
                location=OpenApiParameter.PATH,
                required=True,
                description='Slug товара или услуги',
            ),
            OpenApiParameter(
                name='active_variant_slug',
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Slug активного варианта (где поддерживается в detail)',
            ),
        ],
    )
    def resolve_product(self, request, product_slug=None, **kwargs):
        from apps.catalog.services.product_resolve import build_resolve_response

        return build_resolve_response(request, (product_slug or '').strip())

    @action(detail=False, methods=['get'], url_path='book-filters')
    @extend_schema(
        summary="Фильтры для книг",
        description="Возвращает авторов, издателей и языки для фильтрации книг",
        parameters=[
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории (или несколько через запятую)"),
            OpenApiParameter(name="category_id", type=int, required=False, description="ID категории (можно несколько)"),
        ],
    )
    def book_filters(self, request, *args, **kwargs):
        queryset = Product.objects.filter(is_active=True, product_type='books')

        category_slug = request.query_params.get('category_slug') or request.query_params.get('subcategory_slug')
        if category_slug:
            slugs = [s.strip() for s in category_slug.split(',') if s.strip()]
            if slugs:
                category_ids = _get_category_ids_with_descendants(slugs)
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)

        category_ids_raw = request.query_params.getlist('category_id') or request.query_params.getlist('category_id[]')
        if category_ids_raw:
            try:
                category_ids = [int(cid) for cid in category_ids_raw if str(cid).strip() != '']
            except (TypeError, ValueError):
                category_ids = []
            if category_ids:
                queryset = queryset.filter(category_id__in=category_ids)

        authors_qs = Author.objects.filter(books__product__base_product__in=queryset).distinct().order_by('last_name', 'first_name')
        # Жанры: из ProductGenre (какие реально есть у товаров) + дочерние категории корня «Книги» (все возможные жанры для сайдбара)
        genre_ids_from_products = set(
            Category.objects.filter(
                book_genre_products__product__base_product__in=queryset, is_active=True
            ).values_list('id', flat=True).distinct()
        )
        books_root = Category.objects.filter(slug='books', is_active=True).first()
        if books_root:
            genre_ids_from_tree = set(
                Category.objects.filter(parent_id=books_root.id, is_active=True).values_list('id', flat=True)
            )
            genre_ids_from_products |= genre_ids_from_tree
        genres_qs = (
            Category.objects.filter(pk__in=genre_ids_from_products, is_active=True).order_by('name')
            if genre_ids_from_products
            else Category.objects.none()
        )

        from apps.catalog.models import BookProduct as BookProductModel
        publishers_raw = list(
            BookProductModel.objects.filter(base_product__in=queryset)
            .exclude(publisher__isnull=True).exclude(publisher__exact='')
            .values_list('publisher', flat=True).distinct()
        )
        languages_raw = list(
            BookProductModel.objects.filter(base_product__in=queryset)
            .exclude(language__isnull=True).exclude(language__exact='')
            .values_list('language', flat=True).distinct()
        )

        def normalize_list(values: list[str]) -> list[str]:
            cleaned: list[str] = []
            seen: set[str] = set()
            for value in values:
                v = (value or '').strip()
                if not v:
                    continue
                key = v.casefold()
                if key in seen:
                    continue
                seen.add(key)
                cleaned.append(v)
            return sorted(cleaned, key=lambda item: item.casefold())

        locale = getattr(request, "LANGUAGE_CODE", "") or request.headers.get("Accept-Language", "") or ""
        is_english = locale.lower().startswith("en")
        return Response({
            "authors": [
                {
                    "id": a.id,
                    "name": a.full_name_en if is_english and a.full_name_en else a.full_name
                }
                for a in authors_qs
            ],
            "genres": BookGenreSerializer(genres_qs, many=True).data,
            "publishers": normalize_list(publishers_raw),
            "languages": normalize_list(languages_raw),
        })
    
    @action(detail=True, methods=['get'])
    @extend_schema(
        summary="Получить историю цен",
        description="Возвращает историю изменения цен товара",
        parameters=[
            OpenApiParameter(name="days", type=int, required=False, description="Количество дней", default=30),
        ]
    )
    def price_history(self, request, slug=None):
        """Получить историю цен товара."""
        product = self.get_object()
        days = int(request.query_params.get('days', 30))
        
        service = CatalogService()
        history = service.get_price_history(product.id, days)
        serializer = PriceHistorySerializer(history, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    @extend_schema(
        summary="Поиск товаров",
        description="Поиск товаров по названию и описанию",
        parameters=[
            OpenApiParameter(name="q", type=str, required=True, description="Поисковый запрос"),
            OpenApiParameter(name="limit", type=int, required=False, description="Лимит результатов", default=20),
        ]
    )
    def search(self, request):
        """Поиск товаров."""
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response(
                {"error": "Поисковый запрос обязателен"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        limit = int(request.query_params.get('limit', 20))
        service = CatalogService()
        products = service.get_products(search=query, limit=limit)
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='featured', url_name='featured')
    @extend_schema(
        summary="Рекомендуемые товары",
        description="Возвращает список рекомендуемых товаров"
    )
    def featured(self, request):
        """Получить рекомендуемые товары."""
        featured_products = Product.objects.filter(
            is_active=True, 
            is_featured=True
        ).exclude(
            models.Q(product_type__in=['clothing', 'shoes']) &
            (
                models.Q(external_data__has_key='source_variant_id') |
                models.Q(external_data__has_key='source_variant_slug')
            )
        ).order_by('-created_at')[:10]
        serializer = self.get_serializer(featured_products, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    @extend_schema(
        summary="Похожие товары",
        description="Векторные рекомендации: похожие по контенту (текст + изображение) с реранкингом",
        parameters=[
            OpenApiParameter(name="limit", type=int, required=False, description="Лимит результатов", default=12),
            OpenApiParameter(name="strategy", type=str, required=False, description="Стратегия реранкинга: balanced, relevance, trending", default="balanced"),
            OpenApiParameter(name="exclude_same_brand", type=bool, required=False, description="Исключить товары того же бренда", default=False),
            OpenApiParameter(name="category_id", type=int, required=False),
            OpenApiParameter(name="price_min", type=float, required=False),
            OpenApiParameter(name="price_max", type=float, required=False),
            OpenApiParameter(name="color", type=str, required=False),
        ],
    )
    def similar(self, request, slug=None):
        """GET /api/catalog/products/{slug}/similar/ — похожие товары (RecSys)."""
        product = self.get_object()
        n_results = int(request.query_params.get("limit", 12))
        strategy = request.query_params.get("strategy", "balanced")
        exclude_brand = request.query_params.get("exclude_same_brand", "false").lower() == "true"
        filters = {}
        if request.query_params.get("category_id"):
            try:
                filters["category_id"] = int(request.query_params["category_id"])
            except (ValueError, TypeError):
                pass
        if request.query_params.get("price_min"):
            try:
                filters["price_min"] = float(request.query_params["price_min"])
            except (ValueError, TypeError):
                pass
        if request.query_params.get("price_max"):
            try:
                filters["price_max"] = float(request.query_params["price_max"])
            except (ValueError, TypeError):
                pass
        if request.query_params.get("color"):
            filters["color"] = request.query_params["color"]
        try:
            from apps.recommendations.services.vector_engine import QdrantRecommendationEngine
            from apps.recommendations.services.reranker import BusinessReranker
            engine = QdrantRecommendationEngine()
            reranker = BusinessReranker()
            similar_list = engine.find_similar(
                product_id=product.id,
                vector_type="combined",
                n_results=n_results * 2,
                filters=filters or None,
                exclude_same_brand=exclude_brand,
            )
            reranked = reranker.rerank(similar_list, product, strategy=strategy, request=request)
            rec_ids = [r["product"]["id"] for r in reranked]

            # Исключаем теневые варианты (shadow variants) из результатов
            if rec_ids:
                shadow_ids = set(
                    Product.objects.filter(id__in=rec_ids).filter(
                        models.Q(external_data__has_key='source_variant_id') |
                        models.Q(external_data__has_key='source_variant_slug')
                    ).values_list('id', flat=True)
                )
                if shadow_ids:
                    reranked = [r for r in reranked if r["product"]["id"] not in shadow_ids]
                    rec_ids = [rid for rid in rec_ids if rid not in shadow_ids]

            if rec_ids:
                session_key = getattr(request.session, "session_key", None) or ""
                from apps.recommendations.tasks import log_recommendation_event
                log_recommendation_event.delay(
                    event_type="impression",
                    source_product_id=product.id,
                    recommended_ids=rec_ids,
                    algorithm="vector_combined",
                    session_id=session_key,
                )
            return Response({"count": len(reranked), "strategy": strategy, "results": reranked})
        except Exception as e:
            logger.warning(
                "Similar products unavailable for product_id=%s: %s",
                product.id, e, exc_info=True,
            )
            return Response(
                {"count": 0, "strategy": strategy, "results": [], "error": str(e)},
                status=status.HTTP_200_OK,
            )

    @action(detail=True, methods=['get'])
    @extend_schema(
        summary="Визуально похожие товары",
        description="Похожие товары только по изображению (vector image)",
        parameters=[OpenApiParameter(name="limit", type=int, required=False, default=12)],
    )
    def visually_similar(self, request, slug=None):
        """GET /api/catalog/products/{slug}/visually_similar/ — по визуалу."""
        product = self.get_object()
        n_results = int(request.query_params.get("limit", 12))
        try:
            from apps.recommendations.services.vector_engine import QdrantRecommendationEngine
            engine = QdrantRecommendationEngine()
            similar_list = engine.find_similar(
                product_id=product.id,
                vector_type="image",
                n_results=n_results,
            )
            # Исключаем теневые варианты из результатов
            if similar_list:
                vis_ids = [r["product_id"] for r in similar_list]
                shadow_ids = set(
                    Product.objects.filter(id__in=vis_ids).filter(
                        models.Q(external_data__has_key='source_variant_id') |
                        models.Q(external_data__has_key='source_variant_slug')
                    ).values_list('id', flat=True)
                )
                if shadow_ids:
                    similar_list = [r for r in similar_list if r["product_id"] not in shadow_ids]
            return Response({"count": len(similar_list), "results": similar_list})
        except Exception as e:
            logger.warning(
                "Visually similar unavailable for product_id=%s: %s",
                product.id, e, exc_info=True,
            )
            return Response(
                {"count": 0, "results": [], "error": str(e)},
                status=status.HTTP_200_OK,
            )



# ============================================================================
# API ДЛЯ ОДЕЖДЫ, ОБУВИ И ЭЛЕКТРОНИКИ
# ============================================================================

class ClothingCategoryViewSet(SmartSlugLookupMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с категориями одежды."""
    
    queryset = Category.objects.filter(clothing_type__isnull=False).exclude(clothing_type='').filter(is_active=True)
    serializer_class = ClothingCategorySerializer
    pagination_class = StandardPagination
    
    def get_queryset(self):
        """Фильтрация категорий одежды."""
        queryset = Category.objects.filter(clothing_type__isnull=False).exclude(clothing_type='').filter(is_active=True)
        
        # Фильтр по полу
        gender = self.request.query_params.get('gender')
        if gender:
            queryset = queryset.filter(gender=gender)
        
        # Фильтр по типу одежды
        clothing_type = self.request.query_params.get('clothing_type')
        if clothing_type:
            queryset = queryset.filter(clothing_type=clothing_type)
        
        return queryset.order_by('sort_order', 'name')
    
    @extend_schema(
        summary="Получить список категорий одежды",
        description="Возвращает список активных категорий одежды",
        parameters=[
            OpenApiParameter(name="gender", type=str, required=False, description="Пол (men, women, unisex, kids)"),
            OpenApiParameter(name="clothing_type", type=str, required=False, description="Тип одежды"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=True, methods=['get'])
    @extend_schema(
        summary="Получить подкатегории одежды",
        description="Возвращает список подкатегорий для указанной категории одежды"
    )
    def children(self, request, pk=None):
        """Получить подкатегории."""
        category = self.get_object()
        children = Category.objects.filter(parent=category, clothing_type__isnull=False).exclude(clothing_type='').filter(is_active=True)
        serializer = self.get_serializer(children, many=True)
        return Response(serializer.data)


class ClothingProductViewSet(SmartSlugLookupMixin, FacetedModelViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с товарами одежды."""
    
    # Теневые варианты исключены на уровне класса
    queryset = ClothingProduct.objects.filter(is_active=True).exclude(
        models.Q(external_data__has_key='source_variant_id') |
        models.Q(external_data__has_key='source_variant_slug')
    )
    serializer_class = ClothingProductSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'
    
    def _normalize_ordering(self, ordering: str) -> str:
        """Преобразует формат сортировки из фронтенда в формат Django."""
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',
        }
        return ordering_map.get(ordering, ordering)
    
    def get_queryset(self):
        """Фильтрация товаров одежды по параметрам."""
        queryset = ClothingProduct.objects.filter(is_active=True).exclude(
            models.Q(external_data__has_key='source_variant_id') |
            models.Q(external_data__has_key='source_variant_slug')
        ).prefetch_related(
            'images',
            'variants',
            'variants__images',
        )
        
        # Фильтр по категории (поддержка массивов)
        category_ids = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        if category_ids:
            try:
                category_ids = [int(cid) for cid in category_ids if cid]
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по slug категории (включая подкатегории). subcategory_slug — алиас.
        category_slug = self.request.query_params.get('category_slug') or self.request.query_params.get('subcategory_slug')
        if category_slug:
            slugs = [s.strip() for s in category_slug.split(',') if s.strip()]
            if slugs:
                cat_ids = _get_category_ids_with_descendants(slugs)
                if cat_ids:
                    queryset = queryset.filter(category_id__in=cat_ids)
        
        # Фильтр по бренду (поддержка массивов)
        queryset = _apply_brand_filter(queryset, self.request)
        
        # Фильтр по полу (product.gender | category.gender)
        queryset = _apply_gender_filter(queryset, self.request)
        
        # Фильтр по размеру
        size = self.request.query_params.get('size')
        if size:
            queryset = queryset.filter(
                models.Q(size=size) | models.Q(variants__sizes__size=size)
            )
        
        # Фильтр по цвету
        color = self.request.query_params.get('color')
        if color:
            queryset = queryset.filter(models.Q(color__icontains=color) | models.Q(variants__color__icontains=color))
        
        # Фильтр по материалу
        material = self.request.query_params.get('material')
        if material:
            queryset = queryset.filter(material__icontains=material)
        
        # Фильтр по сезону
        season = self.request.query_params.get('season')
        if season:
            queryset = queryset.filter(season=season)
        
        # Фильтр по поиску
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Фильтр по цене
        queryset = _apply_price_filter(queryset, self.request)
        queryset = _apply_availability_filter(queryset, self.request)
        queryset = _apply_is_new_filter(queryset, self.request, use_flag=True)
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)
        
        return self._apply_facet_filters(queryset)
    
    @extend_schema(
        summary="Получить список товаров одежды",
        description="Возвращает список товаров одежды с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_id", type=int, required=False, description="ID категории"),
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории (включая подкатегории)"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="gender", type=str, required=False, description="Пол"),
            OpenApiParameter(name="size", type=str, required=False, description="Размер"),
            OpenApiParameter(name="color", type=str, required=False, description="Цвет"),
            OpenApiParameter(name="material", type=str, required=False, description="Материал"),
            OpenApiParameter(name="season", type=str, required=False, description="Сезон"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="min_price", type=float, required=False, description="Минимальная цена"),
            OpenApiParameter(name="max_price", type=float, required=False, description="Максимальная цена"),
            OpenApiParameter(name="is_new", type=bool, required=False, description="Новинки"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'], url_path='featured', url_name='featured')
    @extend_schema(
        summary="Рекомендуемые товары одежды",
        description="Возвращает список рекомендуемых товаров одежды"
    )
    def featured(self, request):
        """Получить рекомендуемые товары одежды."""
        featured_products = ClothingProduct.objects.filter(
            is_active=True, 
            is_featured=True
        ).exclude(
            models.Q(external_data__has_key='source_variant_id') |
            models.Q(external_data__has_key='source_variant_slug')
        ).order_by('-created_at')[:10]
        serializer = self.get_serializer(featured_products, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """Деталь по товару или по варианту (если slug варианта)."""
        slug = kwargs.get("slug")
        active_variant_slug = None
        obj = None
        if slug:
            variant = ClothingVariant.objects.filter(slug=slug, is_active=True).select_related('product').first()
            if variant:
                obj = variant.product
                active_variant_slug = variant.slug
        if obj is None:
            obj = self.get_object()
        serializer = self.get_serializer(
            obj,
            context={**self.get_serializer_context(), "active_variant_slug": active_variant_slug}
        )
        return Response(serializer.data)


class ShoeCategoryViewSet(SmartSlugLookupMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с категориями обуви. Использует иерархию (category_type), не shoe_type."""

    queryset = Category.objects.none()
    serializer_class = ShoeCategorySerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        """Категории обуви по иерархии (category_type__slug='shoes')."""
        queryset = Category.objects.filter(
            category_type__slug='shoes',
            is_active=True,
        ).select_related('category_type').prefetch_related('translations').order_by('sort_order', 'name')

        gender = self.request.query_params.get('gender')
        if gender:
            queryset = queryset.filter(gender=gender)

        return queryset

    @extend_schema(
        summary="Получить список категорий обуви",
        description="Возвращает список активных категорий обуви",
        parameters=[
            OpenApiParameter(name="gender", type=str, required=False, description="Пол (men, women, unisex, kids)"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    @extend_schema(
        summary="Получить подкатегории обуви",
        description="Возвращает список подкатегорий для указанной категории обуви"
    )
    def children(self, request, pk=None):
        """Получить подкатегории."""
        category = self.get_object()
        children = Category.objects.filter(parent=category, is_active=True).order_by('sort_order', 'name')
        serializer = self.get_serializer(children, many=True)
        return Response(serializer.data)


class ShoeProductViewSet(SmartSlugLookupMixin, FacetedModelViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с товарами обуви."""
    
    # Теневые варианты исключены на уровне класса
    queryset = ShoeProduct.objects.filter(is_active=True).exclude(
        models.Q(external_data__has_key='source_variant_id') |
        models.Q(external_data__has_key='source_variant_slug')
    )
    serializer_class = ShoeProductSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'
    
    def _normalize_ordering(self, ordering: str) -> str:
        """Преобразует формат сортировки из фронтенда в формат Django."""
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',
        }
        return ordering_map.get(ordering, ordering)
    
    def get_queryset(self):
        """Фильтрация товаров обуви по параметрам."""
        queryset = ShoeProduct.objects.filter(is_active=True).exclude(
            models.Q(external_data__has_key='source_variant_id') |
            models.Q(external_data__has_key='source_variant_slug')
        ).prefetch_related(
            'images',
            'variants',
            'variants__images',
        )

        # Фильтр по категории (поддержка массивов)
        category_ids = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        if category_ids:
            try:
                category_ids = [int(cid) for cid in category_ids if cid]
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по slug категории (включая подкатегории). subcategory_slug — алиас.
        category_slug = self.request.query_params.get('category_slug') or self.request.query_params.get('subcategory_slug')
        if category_slug:
            slugs = [s.strip() for s in category_slug.split(',') if s.strip()]
            if slugs:
                cat_ids = _get_category_ids_with_descendants(slugs)
                if cat_ids:
                    queryset = queryset.filter(category_id__in=cat_ids)

        # Фильтр по бренду (поддержка массивов)
        queryset = _apply_brand_filter(queryset, self.request)
        
        # Фильтр по полу (product.gender | category.gender)
        queryset = _apply_gender_filter(queryset, self.request)
        
        # Фильтр по размеру
        size = self.request.query_params.get('size')
        if size:
            queryset = queryset.filter(
                models.Q(size=size) | models.Q(variants__sizes__size=size)
            )
        
        # Фильтр по цвету
        color = self.request.query_params.get('color')
        if color:
            queryset = queryset.filter(models.Q(color__icontains=color) | models.Q(variants__color__icontains=color))
        
        # Фильтр по материалу
        material = self.request.query_params.get('material')
        if material:
            queryset = queryset.filter(material__icontains=material)
        
        # Фильтр по высоте каблука
        heel_height = self.request.query_params.get('heel_height')
        if heel_height:
            queryset = queryset.filter(heel_height=heel_height)
        
        # Фильтр по поиску
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Фильтр по цене
        queryset = _apply_price_filter(queryset, self.request)
        queryset = _apply_availability_filter(queryset, self.request)
        queryset = _apply_is_new_filter(queryset, self.request, use_flag=True)
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)
        
        return self._apply_facet_filters(queryset)
    
    @extend_schema(
        summary="Получить список товаров обуви",
        description="Возвращает список товаров обуви с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_id", type=int, required=False, description="ID категории"),
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории (включая подкатегории)"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="gender", type=str, required=False, description="Пол"),
            OpenApiParameter(name="size", type=str, required=False, description="Размер"),
            OpenApiParameter(name="color", type=str, required=False, description="Цвет"),
            OpenApiParameter(name="material", type=str, required=False, description="Материал"),
            OpenApiParameter(name="heel_height", type=str, required=False, description="Высота каблука"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="min_price", type=float, required=False, description="Минимальная цена"),
            OpenApiParameter(name="max_price", type=float, required=False, description="Максимальная цена"),
            OpenApiParameter(name="is_new", type=bool, required=False, description="Новинки"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'], url_path='featured', url_name='featured')
    @extend_schema(
        summary="Рекомендуемые товары обуви",
        description="Возвращает список рекомендуемых товаров обуви"
    )
    def featured(self, request):
        """Получить рекомендуемые товары обуви."""
        featured_products = ShoeProduct.objects.filter(
            is_active=True, 
            is_featured=True
        ).exclude(
            models.Q(external_data__has_key='source_variant_id') |
            models.Q(external_data__has_key='source_variant_slug')
        ).order_by('-created_at')[:10]
        serializer = self.get_serializer(featured_products, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """Деталь по товару или по варианту (если slug варианта)."""
        slug = kwargs.get("slug")
        active_variant_slug = None
        obj = None
        if slug:
            variant = ShoeVariant.objects.filter(slug=slug, is_active=True).select_related('product').first()
            if variant:
                obj = variant.product
                active_variant_slug = variant.slug
        if obj is None:
            obj = self.get_object()
        serializer = self.get_serializer(
            obj,
            context={**self.get_serializer_context(), "active_variant_slug": active_variant_slug}
        )
        return Response(serializer.data)


class ElectronicsCategoryViewSet(SmartSlugLookupMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с категориями электроники."""
    
    queryset = Category.objects.filter(device_type__isnull=False).exclude(device_type='').filter(is_active=True)
    serializer_class = ElectronicsCategorySerializer
    pagination_class = StandardPagination
    
    def get_queryset(self):
        """Фильтрация категорий электроники."""
        queryset = Category.objects.filter(device_type__isnull=False).exclude(device_type='').filter(is_active=True)
        
        # Фильтр по типу устройства
        device_type = self.request.query_params.get('device_type')
        if device_type:
            queryset = queryset.filter(device_type=device_type)
        
        return queryset.order_by('sort_order', 'name')
    
    @extend_schema(
        summary="Получить список категорий электроники",
        description="Возвращает список активных категорий электроники",
        parameters=[
            OpenApiParameter(name="device_type", type=str, required=False, description="Тип устройства"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=True, methods=['get'])
    @extend_schema(
        summary="Получить подкатегории электроники",
        description="Возвращает список подкатегорий для указанной категории электроники"
    )
    def children(self, request, pk=None):
        """Получить подкатегории."""
        category = self.get_object()
        children = Category.objects.filter(parent=category, device_type__isnull=False).exclude(device_type='').filter(is_active=True)
        serializer = self.get_serializer(children, many=True)
        return Response(serializer.data)


class ElectronicsProductViewSet(SmartSlugLookupMixin, FacetedModelViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с товарами электроники."""
    
    queryset = ElectronicsProduct.objects.filter(is_active=True)
    serializer_class = ElectronicsProductSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'
    
    def _normalize_ordering(self, ordering: str) -> str:
        """Преобразует формат сортировки из фронтенда в формат Django."""
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',
        }
        return ordering_map.get(ordering, ordering)
    
    def get_queryset(self):
        """Фильтрация товаров электроники по параметрам."""
        queryset = ElectronicsProduct.objects.filter(is_active=True)
        
        # Фильтр по категории (поддержка массивов)
        category_ids = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        if category_ids:
            try:
                category_ids = [int(cid) for cid in category_ids if cid]
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по slug категории (включая подкатегории). subcategory_slug — алиас.
        category_slug = self.request.query_params.get('category_slug') or self.request.query_params.get('subcategory_slug')
        if category_slug:
            slugs = [s.strip() for s in category_slug.split(',') if s.strip()]
            if slugs:
                cat_ids = _get_category_ids_with_descendants(slugs)
                if cat_ids:
                    queryset = queryset.filter(category_id__in=cat_ids)
        
        # Фильтр по бренду (поддержка массивов)
        queryset = _apply_brand_filter(queryset, self.request)
        
        # Фильтр по модели
        model = self.request.query_params.get('model')
        if model:
            queryset = queryset.filter(model__icontains=model)
        
        # Фильтр по поиску
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Фильтр по цене
        queryset = _apply_price_filter(queryset, self.request)
        queryset = _apply_availability_filter(queryset, self.request)
        queryset = _apply_is_new_filter(queryset, self.request, use_flag=True)
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)
        
        return self._apply_facet_filters(queryset)
    
    @extend_schema(
        summary="Получить список товаров электроники",
        description="Возвращает список товаров электроники с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_id", type=int, required=False, description="ID категории"),
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории (включая подкатегории)"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="model", type=str, required=False, description="Модель"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="min_price", type=float, required=False, description="Минимальная цена"),
            OpenApiParameter(name="max_price", type=float, required=False, description="Максимальная цена"),
            OpenApiParameter(name="is_new", type=bool, required=False, description="Новинки"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'], url_path='featured', url_name='featured')
    @extend_schema(
        summary="Рекомендуемые товары электроники",
        description="Возвращает список рекомендуемых товаров электроники"
    )
    def featured(self, request):
        """Получить рекомендуемые товары электроники."""
        featured_products = ElectronicsProduct.objects.filter(
            is_active=True, 
            is_featured=True
        ).order_by('-created_at')[:10]
        serializer = self.get_serializer(featured_products, many=True)
        return Response(serializer.data)


class JewelryProductViewSet(SmartSlugLookupMixin, FacetedModelViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """API для товаров украшений (с вариантами и размерами)."""
    queryset = JewelryProduct.objects.filter(is_active=True)
    serializer_class = JewelryProductSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'

    def _normalize_ordering(self, ordering: str) -> str:
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',
        }
        return ordering_map.get(ordering, ordering)

    def get_queryset(self):
        queryset = JewelryProduct.objects.filter(is_active=True)
        def parse_multi_param(param_name: str) -> list[str]:
            raw_list = self.request.query_params.getlist(param_name) or []
            if not raw_list:
                raw = self.request.query_params.get(param_name)
                if raw:
                    raw_list = raw.split(',')
            return [v.strip() for v in raw_list if v and str(v).strip()]

        # Категории:
        # - category_slug: "родительские" категории (например rings)
        # - subcategory_slug: узкие подкатегории (например signet-rings)
        # Поведение:
        # - только category_slug -> родитель + все потомки
        # - category_slug + subcategory_slug -> (товары прямо в родителе) OR (товары в выбранных подкатегориях)
        category_ids_raw = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        category_ids: list[int] = []
        if category_ids_raw:
            try:
                category_ids = [int(cid) for cid in category_ids_raw if cid]
            except (ValueError, TypeError):
                category_ids = []

        parent_slug_raw = self.request.query_params.get('category_slug') or ''
        child_slug_raw = self.request.query_params.get('subcategory_slug') or ''
        parent_slugs = [s.strip() for s in parent_slug_raw.split(',') if s.strip()]
        child_slugs = [s.strip() for s in child_slug_raw.split(',') if s.strip()]

        if parent_slugs or child_slugs or category_ids:
            q_cat = models.Q()

            if child_slugs:
                # Если выбраны подкатегории — это строгий фильтр: показываем ТОЛЬКО эти подкатегории
                # (и их потомков). Товары, лежащие прямо в родительской категории, НЕ включаем.
                child_ids = _get_category_ids_with_descendants(child_slugs)
                if child_ids:
                    q_cat |= models.Q(category_id__in=child_ids)
            else:
                # Только родительские slug: включаем потомков.
                if parent_slugs:
                    parent_ids = _get_category_ids_with_descendants(parent_slugs)
                    if parent_ids:
                        q_cat |= models.Q(category_id__in=parent_ids)
                # Явные category_id — строгая привязка без потомков (используем если slug не задан).
                if category_ids:
                    q_cat |= models.Q(category_id__in=category_ids)

            if q_cat:
                queryset = queryset.filter(q_cat)
        gender_slugs = _parse_multi_param(self.request, 'gender') or _parse_multi_param(self.request, 'jewelry_gender')
        if gender_slugs:
            normalized_genders = gender_slugs
            if normalized_genders:
                q = (
                    models.Q(gender__in=normalized_genders) |
                    models.Q(variants__gender__in=normalized_genders) |
                    models.Q(category__gender__in=normalized_genders)
                )
                queryset = queryset.filter(q).distinct()
        queryset = _apply_brand_filter(queryset, self.request)
        jewelry_types = parse_multi_param('jewelry_type')
        if jewelry_types:
            q = models.Q()
            for jt in jewelry_types:
                q |= models.Q(jewelry_type__icontains=jt)
            queryset = queryset.filter(q)
        materials = parse_multi_param('material')
        if materials:
            q = models.Q()
            for mat in materials:
                q |= models.Q(material__icontains=mat) | models.Q(variants__material__icontains=mat)
            queryset = queryset.filter(q).distinct()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        queryset = _apply_price_filter(queryset, self.request)
        queryset = _apply_availability_filter(queryset, self.request)
        queryset = _apply_is_new_filter(queryset, self.request, use_flag=True)
        ordering = self.request.query_params.get('ordering', '-created_at')
        queryset = queryset.order_by(self._normalize_ordering(ordering))
        return self._apply_facet_filters(queryset)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        active_slug = self.request.query_params.get('active_variant_slug')
        if active_slug:
            context['active_variant_slug'] = active_slug
        return context

    @action(detail=False, methods=['get'], url_path='featured', url_name='featured')
    def featured(self, request):
        featured_products = JewelryProduct.objects.filter(
            is_active=True, is_featured=True
        ).exclude(
            models.Q(external_data__has_key='source_variant_id') |
            models.Q(external_data__has_key='source_variant_slug')
        ).order_by('-created_at')[:10]
        serializer = self.get_serializer(featured_products, many=True)
        return Response(serializer.data)


class FurnitureProductViewSet(SmartSlugLookupMixin, FacetedModelViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с товарами мебели."""
    
    queryset = FurnitureProduct.objects.filter(is_active=True)
    serializer_class = FurnitureProductSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'
    
    def _normalize_ordering(self, ordering: str) -> str:
        """Преобразует формат сортировки из фронтенда в формат Django."""
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',
        }
        return ordering_map.get(ordering, ordering)

    pagination_class = StandardPagination
    lookup_field = 'slug'
    
    def _normalize_ordering(self, ordering: str) -> str:
        """Преобразует формат сортировки из фронтенда в формат Django."""
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',
        }
        return ordering_map.get(ordering, ordering)
    
    def get_queryset(self):
        """Фильтрация товаров мебели по параметрам."""
        queryset = FurnitureProduct.objects.filter(is_active=True)

        def parse_multi_param(param_name: str) -> list[str]:
            raw_list = (
                self.request.query_params.getlist(param_name)
                or self.request.query_params.getlist(f"{param_name}[]")
                or []
            )
            if not raw_list:
                raw = self.request.query_params.get(param_name)
                if raw:
                    raw_list = raw.split(',')
            return [v.strip() for v in raw_list if v and str(v).strip()]
        
        # Фильтр по категории (поддержка массивов)
        category_ids = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        if category_ids:
            try:
                category_ids = [int(cid) for cid in category_ids if cid]
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по slug категории (включая подкатегории). subcategory_slug — алиас.
        category_slug = self.request.query_params.get('category_slug') or self.request.query_params.get('subcategory_slug')
        if category_slug:
            slugs = [s.strip() for s in category_slug.split(',') if s.strip()]
            if slugs:
                cat_ids = _get_category_ids_with_descendants(slugs)
                if cat_ids:
                    queryset = queryset.filter(category_id__in=cat_ids)
        
        # Фильтр по бренду (поддержка массивов)
        queryset = _apply_brand_filter(queryset, self.request)
        
        # Фильтр по типу мебели
        furniture_types = parse_multi_param('furniture_type')
        if furniture_types:
            queryset = queryset.filter(furniture_type__in=furniture_types)
        
        # Фильтр по материалу
        material = self.request.query_params.get('material')
        if material:
            queryset = queryset.filter(material__icontains=material)
        
        # Фильтр по поиску
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Фильтр по цене
        queryset = _apply_price_filter(queryset, self.request)
        queryset = _apply_availability_filter(queryset, self.request)
        queryset = _apply_is_new_filter(queryset, self.request, use_flag=True)
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)
        
        return self._apply_facet_filters(queryset)
    
    @extend_schema(
        summary="Получить список товаров мебели",
        description="Возвращает список товаров мебели с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_id", type=int, required=False, description="ID категории"),
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории (включая подкатегории)"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="furniture_type", type=str, required=False, description="Тип мебели"),
            OpenApiParameter(name="material", type=str, required=False, description="Материал"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="min_price", type=float, required=False, description="Минимальная цена"),
            OpenApiParameter(name="max_price", type=float, required=False, description="Максимальная цена"),
            OpenApiParameter(name="is_new", type=bool, required=False, description="Новинки"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'], url_path='featured', url_name='featured')
    @extend_schema(
        summary="Рекомендуемые товары мебели",
        description="Возвращает список рекомендуемых товаров мебели"
    )
    def featured(self, request):
        """Получить рекомендуемые товары мебели."""
        featured_products = FurnitureProduct.objects.filter(
            is_active=True, 
            is_featured=True
        ).exclude(
            models.Q(external_data__has_key='source_variant_id') |
            models.Q(external_data__has_key='source_variant_slug')
        ).order_by('-created_at')[:10]
        serializer = self.get_serializer(featured_products, many=True)
        return Response(serializer.data)


class ServiceViewSet(SmartSlugLookupMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с услугами."""
    
    queryset = Service.objects.filter(is_active=True)
    serializer_class = ServiceSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'
    
    def _normalize_ordering(self, ordering: str) -> str:
        """Преобразует формат сортировки из фронтенда в формат Django."""
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-created_at',  # Услуги пока не имеют отдельного поля популярности
        }
        return ordering_map.get(ordering, ordering)
        
    def get_queryset(self):
        """Фильтрация услуг по параметрам."""
        queryset = Service.objects.filter(is_active=True)
        
        # Фильтр по категории (ID)
        category_id = self.request.query_params.get('category_id')
        if category_id:
            try:
                queryset = queryset.filter(category_id=int(category_id))
            except (ValueError, TypeError):
                pass
        
        # Фильтр по slug категории (включая подкатегории)
        category_slug = self.request.query_params.get('category_slug') or self.request.query_params.get('subcategory_slug')
        if category_slug:
            slugs = [s.strip() for s in category_slug.split(',') if s.strip()]
            if slugs:
                cat_ids = _get_category_ids_with_descendants(slugs)
                if cat_ids:
                    queryset = queryset.filter(category_id__in=cat_ids)
        
        # Фильтр по типу услуги
        service_type = self.request.query_params.get('service_type')
        if service_type:
            queryset = queryset.filter(service_type__icontains=service_type)
        
        # Фильтр по поиску (включая переводы и характеристики)
        search = self.request.query_params.get('search')
        if search:
            logger.info(f"Searching services for query: {search}")
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search) |
                Q(translations__name__icontains=search) |
                Q(translations__description__icontains=search) |
                Q(service_attributes__attribute_key__slug__icontains=search) |
                Q(service_attributes__attribute_key__translations__name__icontains=search) |
                Q(service_attributes__value__icontains=search)
            ).distinct()
            logger.info(f"Found {queryset.count()} services match")
        
        # Фильтр по цене
        queryset = _apply_price_filter(queryset, self.request)
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)
        
        return queryset


def _dedupe_favorites_serialized_rows(serialized_list):
    """
    Убирает дубликаты одной витринной позиции в ответе списка избранного.

    В БД могут сосуществовать несколько Favorite на один и тот же товар разными путями
    (например shadow Product и ShoeProduct с одним slug), в т.ч. после старых багов с id.
    Ключ совпадает с тем, как фронт строит ссылку на карточку: slug + тип.
    Оставляем самую свежую запись по created_at.
    """
    def _norm_type(raw):
        return (raw or 'medicines').replace('_', '-').strip().lower()

    rows = sorted(
        serialized_list,
        key=lambda x: x.get('created_at') or '',
        reverse=True,
    )
    seen = set()
    out = []
    for row in rows:
        p = row.get('product') or {}
        slug = (p.get('slug') or '').strip().lower()
        ptype = _norm_type(p.get('_product_type'))
        pid = p.get('id')
        csize = (row.get('chosen_size') or p.get('favorite_chosen_size') or '').strip().lower()
        key = (slug, ptype, csize) if slug else (str(pid or ''), ptype, csize)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


class FavoriteViewSet(viewsets.ViewSet):
    """API для работы с избранным."""
    from rest_framework.permissions import AllowAny
    from .models import Service
    permission_classes = [AllowAny]
    # Исключаем SessionAuthentication: она принудительно применяет CSRF к POST/DELETE
    # даже при AllowAny. Это ломает добавление в избранное для анонимов после
    # открытия Django-сессии (просмотра страницы). JWT-аутентификация достаточна.
    authentication_classes = [JWTSafeAuthentication]
    
    def _get_session_key(self, request):
        """Получить ключ сессии для анонимных пользователей."""
        header_session = request.META.get('HTTP_X_CART_SESSION') or getattr(request, 'headers', {}).get('X-Cart-Session')
        cookie_session = getattr(request, 'COOKIES', {}).get('cart_session')
        django_session = None
        if hasattr(request, 'session'):
            django_session = request.session.session_key
            if not django_session:
                request.session.save()
                django_session = request.session.session_key
        return header_session or cookie_session or django_session

    def _merge_session_favorites(self, user, session_key):
        if not user or not session_key:
            return

        session_favorites = list(Favorite.objects.filter(session_key=session_key))
        if not session_favorites:
            return

        existing_pairs = set(
            Favorite.objects.filter(user=user).values_list(
                'content_type_id', 'object_id', 'chosen_size'
            )
        )

        for favorite in session_favorites:
            pair = (favorite.content_type_id, favorite.object_id, favorite.chosen_size or '')
            if pair in existing_pairs:
                favorite.delete()
            else:
                favorite.user = user
                favorite.session_key = None
                favorite.save(update_fields=['user', 'session_key'])
    
    @extend_schema(
        summary="Получить список избранных товаров",
        description="Возвращает список товаров в избранном для текущего пользователя или сессии",
        responses=FavoriteSerializer(many=True),
        examples=[
            OpenApiExample(
                'Пример ответа',
                value=[
                    {
                        "id": 1,
                        "product": {
                            "id": 1,
                            "name": "Test Product",
                            "slug": "test-product",
                            "price": "10.00",
                            "currency": "USD",
                            "main_image_url": "https://example.com/image.jpg"
                        },
                        "created_at": "2024-01-01T12:00:00Z"
                    }
                ],
                response_only=True
            )
        ]
    )
    def list(self, request):
        """Получить список избранных товаров."""
        user = request.user if request.user.is_authenticated else None
        session_key = self._get_session_key(request)

        if user and session_key:
            self._merge_session_favorites(user, session_key)
        
        if user:
            favorites = Favorite.objects.filter(user=user).select_related('content_type')
        elif session_key:
            favorites = Favorite.objects.filter(session_key=session_key).select_related('content_type')
        else:
            favorites = Favorite.objects.none()
        
        serializer = FavoriteSerializer(favorites, many=True, context={'request': request})
        return Response(_dedupe_favorites_serialized_rows(serializer.data))
    
    @extend_schema(
        summary="Добавить товар в избранное",
        description=(
            "Добавляет товар в избранное для текущего пользователя или сессии. "
            "Повторное добавление того же товара (тот же вариант и размер) идемпотентно: 200 и существующая запись."
        ),
        request=AddToFavoriteSerializer,
        responses={201: FavoriteSerializer, 200: FavoriteSerializer},
        examples=[
            OpenApiExample(
                'Запрос',
                value={"product_id": 1},
                request_only=True
            ),
            OpenApiExample(
                'Ответ',
                value={
                    "id": 1,
                    "product": {
                        "id": 1,
                        "name": "Test Product",
                        "slug": "test-product",
                        "price": "10.00",
                        "currency": "USD"
                    },
                    "created_at": "2024-01-01T12:00:00Z"
                },
                response_only=True
            )
        ]
    )
    @action(detail=False, methods=['post'], url_path='add')
    def add(self, request):
        """Добавить товар в избранное."""
        from django.contrib.contenttypes.models import ContentType
        
        serializer = AddToFavoriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product = serializer.validated_data['_product']
        content_type = ContentType.objects.get_for_model(product)
        
        user = request.user if request.user.is_authenticated else None
        session_key = None if user else self._get_session_key(request)
        
        if not user and not session_key:
            return Response(
                {"detail": "Требуется авторизация или сессия"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Старые записи избранного по shadow Product для того же headwear/underwear/islamic
        base_pk = getattr(product, 'base_product_id', None)
        if base_pk and product.__class__.__name__ in (
            'HeadwearProduct', 'UnderwearProduct', 'IslamicClothingProduct', 'BookProduct',
        ):
            pct = ContentType.objects.get_for_model(Product)
            if user:
                Favorite.objects.filter(user=user, content_type=pct, object_id=base_pk).delete()
            else:
                Favorite.objects.filter(session_key=session_key, content_type=pct, object_id=base_pk).delete()
        
        chosen_size = serializer.validated_data.get('_chosen_size', '') or ''

        # Проверяем, не добавлен ли уже товар
        if user:
            favorite, created = Favorite.objects.get_or_create(
                user=user,
                content_type=content_type,
                object_id=product.id,
                chosen_size=chosen_size,
            )
        else:
            favorite, created = Favorite.objects.get_or_create(
                session_key=session_key,
                content_type=content_type,
                object_id=product.id,
                chosen_size=chosen_size,
            )

        favorite = Favorite.objects.filter(pk=favorite.pk).select_related('content_type').first()
        payload = FavoriteSerializer(favorite, context={'request': request}).data
        # Идемпотентность: двойной клик, гонки, React Strict Mode — не 400.
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(payload, status=status_code)
    
    @extend_schema(
        summary="Удалить товар из избранного",
        description="Удаляет товар из избранного по ID товара",
        request=AddToFavoriteSerializer,
        responses={200: {"detail": "Товар удален из избранного"}, 404: None},
        examples=[
            OpenApiExample(
                'Запрос',
                value={"product_id": 1},
                request_only=True
            )
        ]
    )
    @action(detail=False, methods=['delete'], url_path='remove')
    def remove(self, request):
        """Удалить товар из избранного."""
        from django.contrib.contenttypes.models import ContentType
        payload = request.data if request.data else request.query_params
        serializer = AddToFavoriteSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        
        product = serializer.validated_data['_product']
        content_type = ContentType.objects.get_for_model(product)
        chosen_size = serializer.validated_data.get('_chosen_size', '') or ''
        
        user = request.user if request.user.is_authenticated else None
        session_key = None if user else self._get_session_key(request)
        
        if not user and not session_key:
            return Response(
                {"detail": "Требуется авторизация или сессия"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Удаляем товар из избранного (и устаревшую запись по shadow Product, если была)
        base_pk = getattr(product, 'base_product_id', None)
        legacy_domain = product.__class__.__name__ in (
            'HeadwearProduct', 'UnderwearProduct', 'IslamicClothingProduct', 'BookProduct',
        )
        if user:
            deleted = Favorite.objects.filter(
                user=user,
                content_type=content_type,
                object_id=product.id,
                chosen_size=chosen_size,
            ).delete()[0]
            if legacy_domain and base_pk:
                pct = ContentType.objects.get_for_model(Product)
                deleted += Favorite.objects.filter(
                    user=user, content_type=pct, object_id=base_pk, chosen_size=''
                ).delete()[0]
        else:
            deleted = Favorite.objects.filter(
                session_key=session_key,
                content_type=content_type,
                object_id=product.id,
                chosen_size=chosen_size,
            ).delete()[0]
            if legacy_domain and base_pk:
                pct = ContentType.objects.get_for_model(Product)
                deleted += Favorite.objects.filter(
                    session_key=session_key, content_type=pct, object_id=base_pk, chosen_size=''
                ).delete()[0]
        
        if not deleted:
            return Response(
                {"detail": "Товар не найден в избранном"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response({"detail": "Товар удален из избранного"}, status=status.HTTP_200_OK)
    
    @extend_schema(
        summary="Проверить, находится ли товар в избранном",
        description="Проверяет, находится ли товар в избранном для текущего пользователя или сессии",
        parameters=[
            OpenApiParameter(name="product_id", type=int, required=True, description="ID товара")
        ],
        responses={200: {"is_favorite": True}, 404: None}
    )
    @action(detail=False, methods=['get'], url_path='check')
    def check(self, request):
        """Проверить, находится ли товар в избранном."""
        from django.contrib.contenttypes.models import ContentType

        product_id = request.query_params.get('product_id')
        product_slug = (request.query_params.get('product_slug') or '').strip()
        size_param = (request.query_params.get('size') or '').strip()
        product_type_param = request.query_params.get('product_type') or 'medicines'

        chosen_size = ''
        if product_slug:
            ser = AddToFavoriteSerializer(
                data={
                    'product_slug': product_slug,
                    'product_type': product_type_param,
                    'size': size_param,
                }
            )
            if not ser.is_valid():
                return Response({"is_favorite": False})
            product = ser.validated_data['_product']
            chosen_size = ser.validated_data.get('_chosen_size', '') or ''
        else:
            if not product_id:
                return Response(
                    {"detail": "Не указан product_id или product_slug"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                product, _ = resolve_product_for_favorites_api(product_id, product_type_param)
            except FavoriteResolveValidationError:
                return Response({"is_favorite": False})
            chosen_size = ''

        content_type = ContentType.objects.get_for_model(product)
        base_pk = getattr(product, 'base_product_id', None)
        legacy_domain = product.__class__.__name__ in (
            'HeadwearProduct', 'UnderwearProduct', 'IslamicClothingProduct', 'BookProduct',
        )
        pct_product = ContentType.objects.get_for_model(Product) if legacy_domain and base_pk else None
        
        user = request.user if request.user.is_authenticated else None
        session_key = self._get_session_key(request)

        if user and session_key:
            self._merge_session_favorites(user, session_key)
        
        if not user and not session_key:
            return Response({"is_favorite": False})
        
        if user:
            is_favorite = Favorite.objects.filter(
                user=user,
                content_type=content_type,
                object_id=product.id,
                chosen_size=chosen_size,
            ).exists()
            if not is_favorite and pct_product:
                is_favorite = Favorite.objects.filter(
                    user=user, content_type=pct_product, object_id=base_pk, chosen_size=''
                ).exists()
        else:
            is_favorite = Favorite.objects.filter(
                session_key=session_key,
                content_type=content_type,
                object_id=product.id,
                chosen_size=chosen_size,
            ).exists()
            if not is_favorite and pct_product:
                is_favorite = Favorite.objects.filter(
                    session_key=session_key, content_type=pct_product, object_id=base_pk, chosen_size=''
                ).exists()
        
        return Response({"is_favorite": is_favorite})
    
    @extend_schema(
        summary="Получить количество товаров в избранном",
        description="Возвращает количество товаров в избранном для текущего пользователя или сессии",
        responses={200: {"count": 5}}
    )
    @action(detail=False, methods=['get'], url_path='count')
    def count(self, request):
        """Получить количество товаров в избранном."""
        user = request.user if request.user.is_authenticated else None
        session_key = self._get_session_key(request)

        if user and session_key:
            self._merge_session_favorites(user, session_key)
        
        if user:
            favorites = Favorite.objects.filter(user=user).select_related('content_type')
        elif session_key:
            favorites = Favorite.objects.filter(session_key=session_key).select_related('content_type')
        else:
            favorites = Favorite.objects.none()

        serializer = FavoriteSerializer(favorites, many=True, context={'request': request})
        count = len(_dedupe_favorites_serialized_rows(serializer.data))
        return Response({"count": count})


class BannerViewSet(SmartSlugLookupMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с баннерами."""
    
    queryset = Banner.objects.filter(
        is_active=True
    ).annotate(
        media_count=models.Count('media_files')
    ).filter(
        media_count__gt=0
    ).prefetch_related(
        'translations',
        # Важно: порядок media_files здесь должен совпадать с Meta.ordering у BannerMedia,
        # чтобы API и админка показывали медиа в одном и том же порядке.
        models.Prefetch(
            'media_files',
            queryset=BannerMedia.objects.prefetch_related('translations'),
        ),
    )
    serializer_class = BannerSerializer
    permission_classes = []  # Публичный доступ
    
    @extend_schema(
        summary="Получить список баннеров",
        description="Возвращает список активных баннеров с медиа-файлами, отсортированных по позиции и порядку сортировки",
        parameters=[
            OpenApiParameter(
                name="position",
                type=str,
                required=False,
                description="Фильтр по позиции баннера: main, after_brands, before_footer",
                enum=['main', 'after_brands', 'before_footer']
            ),
        ],
        responses={200: BannerSerializer(many=True)},
    )
    def list(self, request):
        """Получить список баннеров с фильтрацией по позиции."""
        position = request.query_params.get('position')
        queryset = self.get_queryset()
        
        if position:
            queryset = queryset.filter(position=position)
        
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)


from django.views.decorators.http import require_GET, require_POST
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

@require_GET
def proxy_image(request):
    """
    Прокси для Instagram изображений с кешированием.
    Принимает URL изображения напрямую через параметр url.
    """
    from urllib.parse import unquote

    # Получаем URL и убираем лишнее кодирование (quote в сериализаторе мог закодировать уже закодированный %)
    raw_url = request.GET.get('url')
    if not raw_url:
        return JsonResponse({'error': 'url parameter required'}, status=400)

    # Нормализуем URL: убираем двойное/тройное кодирование (%2525 -> %25 -> %)
    image_url = raw_url
    for _ in range(5):
        prev = image_url
        image_url = unquote(image_url)
        if image_url == prev:
            break

    urls_to_try = [image_url]
    mid = unquote(raw_url)
    if mid not in urls_to_try:
        urls_to_try.append(mid)
    if raw_url not in urls_to_try:
        urls_to_try.append(raw_url)

    # Логирование для отладки
    logger.info(f"Resolved URL: {image_url[:120]}...")
    logger.info(f"Contains instagram.f: {'instagram.f' in image_url}")
    logger.info(f"Contains cdninstagram: {'cdninstagram.com' in image_url}")
    
    # Разрешённые домены для прокси (Instagram, CDN проекта)
    _ALLOWED_PROXY_DOMAINS = ('instagram.f', 'cdninstagram.com', 'cdn.mudaroba.com', 'r2.dev')
    if not any(d in image_url for d in _ALLOWED_PROXY_DOMAINS):
        logger.error(f"Invalid domain check failed for URL: {image_url[:100]}")
        return JsonResponse({'error': f'Invalid domain: {image_url[:100]}...'}, status=400)
    
    # Создаем ключ кеша
    cache_key = f"insta_img_{hashlib.md5(image_url.encode()).hexdigest()}"
    
    # Проверяем кеш
    cached_response = cache.get(cache_key)
    if cached_response:
        return HttpResponse(cached_response, content_type='image/jpeg')
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.instagram.com/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        }
        response = None
        for candidate in urls_to_try:
            try:
                r = requests.get(candidate, headers=headers, timeout=10)
                if r.status_code == 200:
                    response = r
                    image_url = candidate
                    break
            except Exception:
                continue
        if response is None:
            try:
                response = requests.get(image_url, headers=headers, timeout=10)
            except Exception:
                response = None

        if response is not None and response.status_code == 200:
            # Content-Type из ответа или по расширению
            ct = response.headers.get('Content-Type', '').split(';')[0].strip()
            if not ct or ct == 'application/octet-stream':
                path_lower = (image_url.split('?')[0] or '').lower()
                ext_map = {'.webp': 'image/webp', '.png': 'image/png', '.gif': 'image/gif',
                           '.jpeg': 'image/jpeg', '.jpg': 'image/jpeg'}
                ct = next((ext_map[e] for e in ['.webp', '.png', '.gif', '.jpeg', '.jpg'] if path_lower.endswith(e)), 'image/jpeg')
            cache.set(cache_key, response.content, 86400)
            django_response = HttpResponse(response.content, content_type=ct)
            django_response['Cache-Control'] = 'public, max-age=2592000, immutable'
            django_response['Access-Control-Allow-Origin'] = '*'
            return django_response

        # При любой ошибке CDN (404, 400, 403, 500 и т.д.) возвращаем placeholder
        gif_1x1 = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
        return HttpResponse(gif_1x1, content_type='image/gif')
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# Content-Type по расширению для прокси R2-медиа
_PROXY_MEDIA_TYPES = {
    '.mp4': 'video/mp4',
    '.webm': 'video/webm',
    '.mov': 'video/quicktime',
    '.m4v': 'video/x-m4v',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
}


@require_GET
def proxy_media(request):
    """
    Прокси для медиафайлов из R2 (видео/изображения).
    Устраняет ERR_SSL_PROTOCOL_ERROR при загрузке с pub-*.r2.dev.
    Поддерживает Range-запросы (206 Partial Content) для стриминга видео.
    """
    from django.conf import settings
    from django.core.files.storage import default_storage
    from django.http import FileResponse
    import re

    class PartialFileWrapper:
        """Обертка для чтения только части файла (для Range-запросов)."""
        def __init__(self, file_obj, start, length):
            self.file_obj = file_obj
            self.start = start
            self.remaining = length
            if hasattr(self.file_obj, 'seek'):
                self.file_obj.seek(start)

        def __iter__(self):
            chunk_size = 8192
            while self.remaining > 0:
                to_read = min(chunk_size, self.remaining)
                data = self.file_obj.read(to_read)
                if not data:
                    break
                self.remaining -= len(data)
                yield data
        
        def close(self):
            if hasattr(self.file_obj, 'close'):
                self.file_obj.close()

    path = request.GET.get('path')
    if not path or '..' in path or path.startswith('/'):
        return JsonResponse({'error': 'path parameter required and must be relative'}, status=400)

    r2_public = getattr(settings, 'R2_PUBLIC_URL', '') or ''
    if not r2_public:
        return JsonResponse({'error': 'R2 proxy not configured'}, status=503)

    from apps.catalog.utils.media_path import iter_storage_path_candidates, resolve_existing_media_storage_key

    resolved_path = resolve_existing_media_storage_key(path)
    candidates = iter_storage_path_candidates(path)

    if not resolved_path:
        # Пытаемся найти в локальной медиа-папке (fallback)
        media_root = str(settings.MEDIA_ROOT)
        for candidate in candidates:
            local_path = os.path.normpath(os.path.join(media_root, candidate))
            if local_path.startswith(media_root) and os.path.exists(local_path):
                resolved_path = candidate
                break

    if not resolved_path:
        return JsonResponse({'error': 'Not found'}, status=404)

    try:
        from PIL import Image, ImageOps
        import io
        import hashlib
        from django.core.cache import cache
        
        ext = resolved_path.rsplit('.', 1)[-1].lower() if '.' in resolved_path else ''
        content_type = _PROXY_MEDIA_TYPES.get(f'.{ext}', 'application/octet-stream')
        # Ключи в /videos/ без расширения (.mp4) — иначе octet-stream, Safari часто не запускает воспроизведение.
        if content_type == 'application/octet-stream' and '/videos/' in resolved_path.lower():
            content_type = 'video/mp4'

        # Уменьшение изображений для карточек в каталоге (?max_width= / ?w=, только jpeg/png/webp)
        max_w_raw = request.GET.get('max_width') or request.GET.get('w')
        max_w_int = None
        if max_w_raw:
            try:
                max_w_int = max(64, min(int(max_w_raw), 800))
            except (TypeError, ValueError):
                max_w_int = None

        if max_w_int and content_type in ('image/jpeg', 'image/png', 'image/webp'):
            cache_key_mw = f"r2mw_{hashlib.md5(resolved_path.encode()).hexdigest()}_{max_w_int}"
            webp_resized = cache.get(cache_key_mw)
            if webp_resized is None:
                try:
                    with default_storage.open(resolved_path, 'rb') as rf:
                        img = Image.open(rf)
                        img = ImageOps.exif_transpose(img)
                        if img.mode in ('RGBA', 'P', 'LA'):
                            if img.mode == 'P':
                                img = img.convert('RGBA')
                        else:
                            if img.mode != 'RGB':
                                img = img.convert('RGB')
                        img.thumbnail((max_w_int, max_w_int * 4), Image.Resampling.LANCZOS)
                        out = io.BytesIO()
                        img.save(out, format='WEBP', quality=80, method=2)
                        webp_resized = out.getvalue()
                    if len(webp_resized) < 5 * 1024 * 1024:
                        cache.set(cache_key_mw, webp_resized, 30 * 86400)
                except Exception as resize_err:
                    logger.warning('proxy_media max_width для %s: %s', resolved_path, resize_err)
                    webp_resized = None
            if webp_resized is not None:
                resp = HttpResponse(webp_resized, content_type='image/webp')
                resp['Content-Length'] = str(len(webp_resized))
                resp['Cache-Control'] = 'public, max-age=2592000, immutable'
                resp['Vary'] = 'Accept'
                return resp

        file_obj = default_storage.open(resolved_path, 'rb')
        
        # ✅ WebP Оптимизация на лету: экономия ресурса и трафика
        # Применяется только если браузер поддерживает image/webp и файл подходящего формата
        if content_type in ('image/jpeg', 'image/png'):
            accept_header = request.META.get('HTTP_ACCEPT', '')
            if 'image/webp' in accept_header or request.GET.get('format') == 'webp':
                # Ключ кэша на основе пути и даты изменения (опционально)
                cache_key = f"r2webp_{hashlib.md5(resolved_path.encode()).hexdigest()}"
                webp_data = cache.get(cache_key)
                
                if webp_data is None:
                    # Пропускаем преобразование на лету для файлов > 8MB чтобы избежать OOM
                    if file_obj.size > 8 * 1024 * 1024:
                        webp_data = None
                    else:
                        # Читаем файл в память
                        try:
                            img = Image.open(file_obj)
                            img = ImageOps.exif_transpose(img) # Сохраняем ориентацию
                            
                            # Конвертируем прозрачность/палитру в RGB для Jpeg/WebP
                            if img.mode in ('RGBA', 'P', 'LA'):
                                # Для PNG сохраняем прозрачность в WebP 
                                if img.mode == 'P':
                                    img = img.convert('RGBA')
                            else:
                                if img.mode != 'RGB':
                                    img = img.convert('RGB')
                            
                            output = io.BytesIO()
                            # Снижаем method до 1 или 2 чтобы значительно сократить потребление памяти и CPU 
                            img.save(output, format='WEBP', quality=80, method=1)
                            webp_data = output.getvalue()
                            
                            # Кэшируем до 5 МБ в Memcached/Redis на 30 дней
                            if len(webp_data) < 5 * 1024 * 1024:
                                cache.set(cache_key, webp_data, 30 * 86400)
                        except Exception as img_err:
                            # В случае ошибки конвертации падаем в фолбэк к оригиналу
                            logger.warning(f"WebP conversion failed for {resolved_path}: {img_err}")
                            file_obj.seek(0)
                            webp_data = None
                
                if webp_data is not None:
                    response = HttpResponse(webp_data, content_type='image/webp')
                    response['Content-Length'] = str(len(webp_data))
                    response['Cache-Control'] = 'public, max-age=2592000, immutable'
                    response['Vary'] = 'Accept'
                    return response

        # Стандартная обработка (для видео, GIF, SVG или если WebP не поддерживается)
        size = file_obj.size
        
        range_header = request.META.get('HTTP_RANGE', '').strip()
        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        
        if range_match:
            first_byte, last_byte = range_match.groups()
            first_byte = int(first_byte) if first_byte else 0
            last_byte = int(last_byte) if last_byte else size - 1
            if last_byte >= size:
                last_byte = size - 1
            length = last_byte - first_byte + 1
            
            # Используем обертку для ограничения стриминга
            stream_obj = PartialFileWrapper(file_obj, first_byte, length)
            response = FileResponse(stream_obj, content_type=content_type)
            response.status_code = 206
            response['Content-Range'] = f'bytes {first_byte}-{last_byte}/{size}'
            response['Content-Length'] = str(length)
        else:
            response = FileResponse(file_obj, content_type=content_type)
            response['Content-Length'] = str(size)

        response['Accept-Ranges'] = 'bytes'
        # Долгий кэш как в оптимизации PageSpeed; без дублирования CORS — его выставляет CorsMiddleware
        response['Cache-Control'] = 'public, max-age=2592000, immutable'
        # Отключаем буферизацию Nginx для потокового видео
        response['X-Accel-Buffering'] = 'no'
        return response

    except Exception as e:
        logger.exception('proxy_media error for path %s', path)
        return JsonResponse({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────
#                     BOOK PRODUCT
# ─────────────────────────────────────────────────────────────

class BookProductViewSet(SmartSlugLookupMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с товарами-книгами."""

    queryset = BookProduct.objects.filter(is_active=True)
    serializer_class = BookProductSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'

    def _normalize_ordering(self, ordering: str) -> str:
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',
            'rating': '-rating',
        }
        return ordering_map.get(ordering, ordering)

    def get_queryset(self):
        queryset = BookProduct.objects.filter(is_active=True).select_related(
            "base_product", "category", "brand"
        )

        # Фильтр по категории
        category_ids = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        if category_ids:
            try:
                category_ids = [int(cid) for cid in category_ids if cid]
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)
            except (ValueError, TypeError):
                pass

        # Фильтр по slug категории
        category_slug = self.request.query_params.get('category_slug') or self.request.query_params.get('subcategory_slug')
        if category_slug:
            slugs = [s.strip() for s in category_slug.split(',') if s.strip()]
            if slugs:
                cat_ids = _get_category_ids_with_descendants(slugs)
                if cat_ids:
                    queryset = queryset.filter(category_id__in=cat_ids)

        # Фильтр по бренду
        queryset = _apply_brand_filter(queryset, self.request)

        # Фильтр по издательству
        publisher = self.request.query_params.get('publisher')
        if publisher:
            queryset = queryset.filter(publisher__icontains=publisher)

        # Фильтр по языку
        language = self.request.query_params.get('language')
        if language:
            queryset = queryset.filter(language__icontains=language)

        # Фильтр по обложке
        cover_type = self.request.query_params.get('cover_type')
        if cover_type:
            queryset = queryset.filter(cover_type__iexact=cover_type)

        # Бестселлеры
        is_bestseller = self.request.query_params.get('is_bestseller')
        if is_bestseller and is_bestseller.lower() in ('true', '1', 'yes'):
            queryset = queryset.filter(is_bestseller=True)

        # Поиск
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)

        # Фильтр по цене
        queryset = _apply_price_filter(queryset, self.request)
        queryset = _apply_availability_filter(queryset, self.request)
        queryset = _apply_is_new_filter(queryset, self.request, use_flag=True)

        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)

        return queryset

    @extend_schema(
        summary="Получить список книг",
        description="Возвращает список книг с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="publisher", type=str, required=False, description="Издательство"),
            OpenApiParameter(name="language", type=str, required=False, description="Язык"),
            OpenApiParameter(name="cover_type", type=str, required=False, description="Тип обложки"),
            OpenApiParameter(name="is_bestseller", type=bool, required=False, description="Бестселлер"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
            OpenApiParameter(name="author", type=str, required=False, description="Автор (имя или часть)"),
            OpenApiParameter(name="genre_slug", type=str, required=False, description="Slug жанра"),
            OpenApiParameter(name="isbn", type=str, required=False, description="ISBN"),
            OpenApiParameter(name="pages_min", type=int, required=False, description="Мин. страниц"),
            OpenApiParameter(name="pages_max", type=int, required=False, description="Макс. страниц"),
            OpenApiParameter(name="rating_min", type=float, required=False, description="Мин. рейтинг"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Получить книгу по slug")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


# ─────────────────────────────────────────────────────────────
#                    PERFUMERY PRODUCT
# ─────────────────────────────────────────────────────────────

class PerfumeryProductViewSet(SmartSlugLookupMixin, viewsets.ReadOnlyModelViewSet):
    """API для работы с товарами парфюмерии."""

    queryset = PerfumeryProduct.objects.filter(is_active=True)
    serializer_class = PerfumeryProductSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'

    def _normalize_ordering(self, ordering: str) -> str:
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',
        }
        return ordering_map.get(ordering, ordering)

    def get_queryset(self):
        queryset = PerfumeryProduct.objects.filter(is_active=True)

        def parse_multi_param(param_name: str) -> list[str]:
            raw_list = (
                self.request.query_params.getlist(param_name)
                or self.request.query_params.getlist(f"{param_name}[]")
                or []
            )
            if not raw_list:
                raw = self.request.query_params.get(param_name)
                if raw:
                    raw_list = raw.split(',')
            return [v.strip() for v in raw_list if v and str(v).strip()]

        # Фильтр по категории
        category_ids = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        if category_ids:
            try:
                category_ids = [int(cid) for cid in category_ids if cid]
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)
            except (ValueError, TypeError):
                pass

        # Фильтр по slug категории
        category_slug = self.request.query_params.get('category_slug') or self.request.query_params.get('subcategory_slug')
        if category_slug:
            slugs = [s.strip() for s in category_slug.split(',') if s.strip()]
            if slugs:
                cat_ids = _get_category_ids_with_descendants(slugs)
                if cat_ids:
                    queryset = queryset.filter(category_id__in=cat_ids)

        # Фильтр по бренду
        queryset = _apply_brand_filter(queryset, self.request)

        # Фильтр по типу аромата
        fragrance_types = parse_multi_param('fragrance_type')
        if fragrance_types:
            queryset = queryset.filter(fragrance_type__in=fragrance_types)

        # Фильтр по семейству аромата
        fragrance_families = parse_multi_param('fragrance_family')
        if fragrance_families:
            queryset = queryset.filter(fragrance_family__in=fragrance_families)

        # Фильтр по полу (product.gender | category.gender)
        queryset = _apply_gender_filter(queryset, self.request)

        # Фильтр по объёму
        volume = self.request.query_params.get('volume')
        if volume:
            queryset = queryset.filter(volume__icontains=volume)

        # Поиск
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)

        # Фильтр по цене
        queryset = _apply_price_filter(queryset, self.request)
        queryset = _apply_availability_filter(queryset, self.request)
        queryset = _apply_is_new_filter(queryset, self.request, use_flag=True)

        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)

        return queryset

    @extend_schema(
        summary="Получить список товаров парфюмерии",
        description="Возвращает список товаров парфюмерии с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="fragrance_type", type=str, required=False, description="Тип аромата"),
            OpenApiParameter(name="fragrance_family", type=str, required=False, description="Семейство аромата"),
            OpenApiParameter(name="gender", type=str, required=False, description="Пол"),
            OpenApiParameter(name="volume", type=str, required=False, description="Объём"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Получить товар парфюмерии по slug")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


# ─────────────────────────────────────────────────────────────
#        ПРОСТЫЕ ДОМЕНЫ (Волна 2) — ViewSets
# ─────────────────────────────────────────────────────────────

class _SimpleDomainViewSet(SmartSlugLookupMixin, viewsets.ReadOnlyModelViewSet):
    """Базовый ViewSet для простых доменов без вариантов."""
    pagination_class = StandardPagination
    lookup_field = 'slug'

    _ORDERING_MAP = {
        'name_asc': 'name',
        'name_desc': '-name',
        'price_asc': 'price',
        'price_desc': '-price',
        'newest': '-created_at',
        'popular': '-is_featured',
    }

    def _normalize_ordering(self, ordering: str) -> str:
        return self._ORDERING_MAP.get(ordering, ordering)


    def _base_queryset(self):
        return self.queryset.all()

    def _apply_domain_filters(self, queryset):
        """Переопределить в подклассе для доменных фильтров."""
        return queryset

    def get_queryset(self):
        queryset = self._base_queryset()

        # Фильтр по категории
        category_ids = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        if category_ids:
            try:
                category_ids = [int(cid) for cid in category_ids if cid]
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)
            except (ValueError, TypeError):
                pass

        # Фильтр по slug категории
        category_slug = self.request.query_params.get('category_slug') or self.request.query_params.get('subcategory_slug')
        if category_slug:
            slugs = [s.strip() for s in category_slug.split(',') if s.strip()]
            if slugs:
                cat_ids = _get_category_ids_with_descendants(slugs)
                if cat_ids:
                    # Включаем товары с category_id в потомках И товары без категории
                    # (они принадлежат домену, но ещё не привязаны к подкатегории)
                    queryset = queryset.filter(
                        models.Q(category_id__in=cat_ids) | models.Q(category_id__isnull=True)
                    )

        # Фильтр по бренду
        queryset = _apply_brand_filter(queryset, self.request)

        # Поиск
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)

        # Фильтр по цене
        queryset = _apply_price_filter(queryset, self.request)
        queryset = _apply_availability_filter(queryset, self.request)
        queryset = _apply_is_new_filter(queryset, self.request, use_flag=True)

        # Доменные фильтры
        queryset = self._apply_domain_filters(queryset)

        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)

        return queryset


# ─── МЕДИКАМЕНТЫ ───

class MedicineProductViewSet(_SimpleDomainViewSet):
    """API для работы с медикаментами."""
    queryset = MedicineProduct.objects.filter(is_active=True)
    serializer_class = MedicineProductSerializer

    def _apply_domain_filters(self, queryset):
        dosage_form = self.request.query_params.get('dosage_form')
        if dosage_form:
            queryset = queryset.filter(dosage_form=dosage_form)
        active_ingredient = self.request.query_params.get('active_ingredient')
        if active_ingredient:
            queryset = queryset.filter(active_ingredient__icontains=active_ingredient)
        prescription = self.request.query_params.get('prescription_required')
        if prescription and prescription.lower() in ('true', '1', 'yes'):
            queryset = queryset.filter(prescription_required=True)
        return queryset

    @extend_schema(
        summary="Получить список медикаментов",
        description="Возвращает список медикаментов с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="dosage_form", type=str, required=False, description="Лекарственная форма"),
            OpenApiParameter(name="active_ingredient", type=str, required=False, description="Действующее вещество"),
            OpenApiParameter(name="prescription_required", type=bool, required=False, description="Требуется рецепт"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Получить медикамент по slug")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


# ─── БАДы ───

class SupplementProductViewSet(_SimpleDomainViewSet):
    """API для работы с БАДами."""
    queryset = SupplementProduct.objects.filter(is_active=True)
    serializer_class = SupplementProductSerializer

    def _apply_domain_filters(self, queryset):
        dosage_form = self.request.query_params.get('dosage_form')
        if dosage_form:
            queryset = queryset.filter(dosage_form=dosage_form)
        active_ingredient = self.request.query_params.get('active_ingredient')
        if active_ingredient:
            queryset = queryset.filter(active_ingredient__icontains=active_ingredient)
        return queryset

    @extend_schema(
        summary="Получить список БАДов",
        description="Возвращает список БАДов с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="dosage_form", type=str, required=False, description="Форма выпуска"),
            OpenApiParameter(name="active_ingredient", type=str, required=False, description="Активный ингредиент"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Получить БАД по slug")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


# ─── МЕДТЕХНИКА ───

class MedicalEquipmentProductViewSet(_SimpleDomainViewSet):
    """API для работы с медтехникой."""
    queryset = MedicalEquipmentProduct.objects.filter(is_active=True)
    serializer_class = MedicalEquipmentProductSerializer

    def _apply_domain_filters(self, queryset):
        equipment_type = self.request.query_params.get('equipment_type')
        if equipment_type:
            queryset = queryset.filter(equipment_type__icontains=equipment_type)
        return queryset

    @extend_schema(
        summary="Получить список медтехники",
        description="Возвращает список медтехники с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="equipment_type", type=str, required=False, description="Тип оборудования"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Получить медтехнику по slug")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


# ─── ПОСУДА ───

class TablewareProductViewSet(_SimpleDomainViewSet):
    """API для работы с посудой."""
    queryset = TablewareProduct.objects.filter(is_active=True)
    serializer_class = TablewareProductSerializer

    def _apply_domain_filters(self, queryset):
        material = self.request.query_params.get('material')
        if material:
            queryset = queryset.filter(material__icontains=material)
        return queryset

    @extend_schema(
        summary="Получить список посуды",
        description="Возвращает список посуды с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="material", type=str, required=False, description="Материал"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Получить посуду по slug")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


# ─── АКСЕССУАРЫ ───

class AccessoryProductViewSet(_SimpleDomainViewSet):
    """API для работы с аксессуарами."""
    queryset = AccessoryProduct.objects.filter(is_active=True)
    serializer_class = AccessoryProductSerializer

    def _apply_domain_filters(self, queryset):
        accessory_type = self.request.query_params.get('accessory_type')
        if accessory_type:
            queryset = queryset.filter(accessory_type__icontains=accessory_type)
        material = self.request.query_params.get('material')
        if material:
            queryset = queryset.filter(material__icontains=material)
        return queryset

    @extend_schema(
        summary="Получить список аксессуаров",
        description="Возвращает список аксессуаров с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="accessory_type", type=str, required=False, description="Тип аксессуара"),
            OpenApiParameter(name="material", type=str, required=False, description="Материал"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Получить аксессуар по slug")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


# ─── БЛАГОВОНИЯ ───

class IncenseProductViewSet(_SimpleDomainViewSet):
    """API для работы с благовониями."""
    queryset = IncenseProduct.objects.filter(is_active=True)
    serializer_class = IncenseProductSerializer

    def _apply_domain_filters(self, queryset):
        scent_type = self.request.query_params.get('scent_type')
        if scent_type:
            queryset = queryset.filter(scent_type__icontains=scent_type)
        return queryset

    @extend_schema(
        summary="Получить список благовоний",
        description="Возвращает список благовоний с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="scent_type", type=str, required=False, description="Тип аромата"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Получить благовоние по slug")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

# ============================================================================
# SPORTS
# ============================================================================

class SportsProductViewSet(_SimpleDomainViewSet):
    """API для работы со спорттоварами."""
    queryset = SportsProduct.objects.filter(is_active=True).order_by('-created_at')
    serializer_class = SportsProductSerializer

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return SportsProductDetailSerializer
        return SportsProductSerializer

    def _apply_domain_filters(self, queryset):
        sport_type = self.request.query_params.get('sport_type')
        if sport_type:
            queryset = queryset.filter(sport_type__icontains=sport_type)
        equipment_type = self.request.query_params.get('equipment_type')
        if equipment_type:
            queryset = queryset.filter(equipment_type__icontains=equipment_type)
        queryset = _apply_gender_filter(queryset, self.request)
        return queryset

    @extend_schema(
        summary="Получить список спорттоваров",
        description="Возвращает списов спортоваров с фильтрацией по виду спорта и типу инвентаря"
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Получить детали спорттовара")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


# ============================================================================
# AUTO PARTS
# ============================================================================

class AutoPartProductViewSet(_SimpleDomainViewSet):
    """API для работы с автозапчастями."""
    queryset = AutoPartProduct.objects.filter(is_active=True).order_by('-created_at')
    serializer_class = AutoPartProductSerializer

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return AutoPartProductDetailSerializer
        return AutoPartProductSerializer

    def _apply_domain_filters(self, queryset):
        car_brand = self.request.query_params.get('car_brand')
        if car_brand:
            queryset = queryset.filter(car_brand__icontains=car_brand)
        car_model = self.request.query_params.get('car_model')
        if car_model:
            queryset = queryset.filter(car_model__icontains=car_model)
        part_number = self.request.query_params.get('part_number')
        if part_number:
            queryset = queryset.filter(part_number__icontains=part_number)
        return queryset

    @extend_schema(summary="Получить список автозапчастей")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Получить детали автозапчасти")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

# ============================================================================
# ДОМЕН Headwear
# ============================================================================

from .models import HeadwearProduct, UnderwearProduct, IslamicClothingProduct
from .serializers import HeadwearProductSerializer, UnderwearProductSerializer, IslamicClothingProductSerializer

class HeadwearProductViewSet(_SimpleDomainViewSet):
    """API для работы с головными уборами."""
    queryset = HeadwearProduct.objects.filter(is_active=True).order_by('-created_at')
    serializer_class = HeadwearProductSerializer

    @extend_schema(summary="Получить список головных уборов")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Получить детали головного убора")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

class UnderwearProductViewSet(_SimpleDomainViewSet):
    """API для работы с нижним бельем."""
    queryset = UnderwearProduct.objects.filter(is_active=True).order_by('-created_at')
    serializer_class = UnderwearProductSerializer

    @extend_schema(summary="Получить список нижнего белья")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Получить детали нижнего белья")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

class IslamicClothingProductViewSet(_SimpleDomainViewSet):
    """API для работы с исламской одеждой."""
    queryset = IslamicClothingProduct.objects.filter(is_active=True).order_by('-created_at')
    serializer_class = IslamicClothingProductSerializer

    @extend_schema(summary="Получить список исламской одежды")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Получить детали исламской одежды")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
