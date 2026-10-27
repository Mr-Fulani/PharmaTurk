"""
YML-экспорт товаров для ВК Маркета и Яндекс.Маркета.

Эндпоинт: GET /api/catalog/export/yml/catalog.yml
Параметры:
  ?category=<slug>  — фильтр по слагу категории (и всем её потомкам)
  (без параметра)   — полный каталог

Полный каталог и корневые категории отдаются готовым файлом, который собирает
задача catalog.generate_yml_feeds; подкатегории — потоком на лету.
Сборка фида — apps/catalog/services/yml_feed.py.
Категории ВК настраиваются через Django Admin → Маппинги категорий ВК.
"""
from django.core.cache import cache
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.cache import get_conditional_response
from django.utils.http import http_date
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema

from .models_vk import YMLFeedSnapshot
from .services.yml_feed import is_prepared_feed_key, iter_snapshot_file, iter_yml_feed
from .throttles import YMLExportThrottle, YMLFeedFileThrottle

GENERATION_REQUEST_LOCK = "yml_feeds_generation_requested"


class YMLExportView(APIView):
    """
    Отдаёт YML-фид (Yandex Market Language) для импорта товаров в ВК Маркет.

    Готовый файл дешёвый — у него свой мягкий лимит; сборка на лету — 2 в минуту.
    """
    permission_classes = [AllowAny]

    def _category_slug(self) -> str:
        return (self.request.query_params.get("category") or "").strip()

    def get_throttles(self):
        if is_prepared_feed_key(self._category_slug()):
            return [YMLFeedFileThrottle()]
        return [YMLExportThrottle()]

    @extend_schema(
        summary="Экспортировать публичный каталог в YML",
        parameters=[
            OpenApiParameter(
                name="category",
                type=str,
                required=False,
                description="Slug категории; экспорт включает её потомков",
            )
        ],
        responses={(200, "application/xml"): OpenApiTypes.BINARY},
    )
    def get(self, request, *args, **kwargs):
        category_slug = self._category_slug()
        if not is_prepared_feed_key(category_slug):
            return StreamingHttpResponse(
                iter_yml_feed(category_slug),
                content_type="application/xml",
            )

        snapshot = YMLFeedSnapshot.objects.filter(category_slug=category_slug).first()
        if snapshot is None or not snapshot.file or snapshot.generated_at is None:
            # Фид ещё не собирался (например, сразу после деплоя) — просим собрать.
            if cache.add(GENERATION_REQUEST_LOCK, True, 600):
                from .tasks import generate_yml_feeds

                generate_yml_feeds.delay()
            response = HttpResponse(
                "Фид готовится, повторите запрос через 10 минут.\n",
                status=503,
                content_type="text/plain; charset=utf-8",
            )
            response["Retry-After"] = "600"
            return response

        etag = f'"{snapshot.pk}-{int(snapshot.generated_at.timestamp())}"'
        last_modified = int(snapshot.generated_at.timestamp())
        not_modified = get_conditional_response(request, etag=etag, last_modified=last_modified)
        if not_modified is not None:
            return not_modified

        response = StreamingHttpResponse(iter_snapshot_file(snapshot), content_type="application/xml")
        response["Content-Length"] = str(snapshot.size_bytes)
        response["ETag"] = etag
        response["Last-Modified"] = http_date(last_modified)
        return response
