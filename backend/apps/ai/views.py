from django.db.models import Count, Avg, Sum, Q
from django.utils import timezone
from datetime import timedelta
from rest_framework import viewsets, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema

from .models import AIProcessingLog, AIProcessingStatus, AIModerationQueue, AITemplate
from .serializers import (
    AIProcessingLogSerializer,
    AIProcessingDetailSerializer,
    AIModerationQueueSerializer,
    AITemplateSerializer,
    AIStatsQuerySerializer,
    GenerateContentRequestSerializer,
    ProcessProductBodySerializer,
    ProcessProductRequestSerializer,
    AIQueuedResponseSerializer,
    AIStatsResponseSerializer,
)
from .tasks import enqueue_product_ai_task
from .services.moderation import reject_log


class AIProcessingLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AIProcessingLog.objects.all()
    serializer_class = AIProcessingLogSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        qs = AIProcessingLog.objects.select_related(
            "product", "suggested_category", "processed_by"
        )
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        if self.request.query_params.get("product_id"):
            qs = qs.filter(product_id=self.request.query_params["product_id"])
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return AIProcessingDetailSerializer
        return AIProcessingLogSerializer

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Проверить результат и применить к товару; вернуть фактический итог."""
        log = self.get_object()
        if log.status not in (AIProcessingStatus.COMPLETED, AIProcessingStatus.MODERATION):
            return Response(
                {"error": "Can only approve completed or moderation status"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from .services.content_generator import ContentGenerator
        gen = ContentGenerator()
        try:
            gen.apply_log_to_product(log, user=request.user)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "status": log.status,
                "application_status": log.application_status,
                "partial": log.status == AIProcessingStatus.MODERATION,
            }
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Отклонить результат."""
        log = self.get_object()
        try:
            reject_log(
                log,
                user=request.user,
                notes=request.data.get("notes", "") or "",
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": "rejected"})

    @action(detail=True, methods=["post"])
    def reprocess(self, request, pk=None):
        """Повторная обработка товара."""
        log = self.get_object()
        queued_log, task_id, submitted = enqueue_product_ai_task(
            product_id=log.product_id,
            processing_type=log.processing_type,
            auto_apply=False,
            force=True,
        )
        return Response({"task_id": task_id, "log_id": queued_log.id, "submitted": submitted})


class AIModerationQueueViewSet(viewsets.ModelViewSet):
    queryset = AIModerationQueue.objects.all()
    serializer_class = AIModerationQueueSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return AIModerationQueue.objects.select_related(
            "log_entry",
            "log_entry__product",
            "assigned_to",
        )

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """Назначить задачу на себя."""
        task = self.get_object()
        task.assigned_to = request.user
        task.save(update_fields=["assigned_to"])
        return Response({"assigned": True})

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """Разрешить задачу: approve или reject по логу."""
        task = self.get_object()
        action_type = request.data.get("action")
        log = task.log_entry
        if action_type == "approve":
            from .services.content_generator import ContentGenerator
            gen = ContentGenerator()
            try:
                gen.apply_log_to_product(log, user=request.user)
            except ValueError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            resolved = log.status == AIProcessingStatus.APPROVED
        elif action_type == "reject":
            try:
                reject_log(
                    log,
                    user=request.user,
                    notes=request.data.get("notes", "") or "",
                )
            except ValueError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            resolved = True
        else:
            return Response(
                {"error": "action must be 'approve' or 'reject'"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        task.refresh_from_db(fields=["resolved_at"])
        return Response(
            {
                "resolved": resolved,
                "action": action_type,
                "status": log.status,
                "application_status": log.application_status,
            }
        )


class AITemplateViewSet(viewsets.ModelViewSet):
    queryset = AITemplate.objects.select_related("category").all()
    serializer_class = AITemplateSerializer
    permission_classes = [permissions.IsAdminUser]


class GenerateContentView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        summary="Запустить AI-обработку товара",
        request=GenerateContentRequestSerializer,
        responses={
            202: AIQueuedResponseSerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Ошибки валидации по полям",
            ),
        },
    )
    def post(self, request):
        serializer = GenerateContentRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        product_id = data["product_id"]
        processing_type = data.get("processing_type", "full")
        auto_apply = data.get("auto_apply", False)
        options = None
        if any(k in data for k in ("generate_description", "categorize", "analyze_images", "use_images")):
            options = {
                "generate_description": data.get("generate_description", True),
                "categorize": data.get("categorize", True),
                "analyze_images": data.get("analyze_images", True),
                "use_images": data.get("use_images", True),
            }
        log_entry, task_id, submitted = enqueue_product_ai_task(
            product_id=product_id,
            processing_type=processing_type,
            auto_apply=auto_apply,
            options=options,
        )
        return Response(
            {
                "status": "queued",
                "task_id": task_id,
                "log_id": log_entry.id,
                "submitted": submitted,
                "product_id": product_id,
                "message": f"Processing started for product {product_id}",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ProcessProductView(APIView):
    """Ручной запуск обработки товара по ID в URL."""

    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        summary="Запустить полную AI-обработку товара",
        request=ProcessProductBodySerializer,
        responses={
            202: AIQueuedResponseSerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Ошибки валидации по полям",
            ),
        },
    )
    def post(self, request, product_id):
        payload = request.data.copy()
        payload["product_id"] = product_id
        serializer = ProcessProductRequestSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        options = {
            "generate_description": data["generate_description"],
            "categorize": data["categorize"],
            "analyze_images": data["analyze_images"],
            "use_images": data["use_images"],
        }
        log_entry, task_id, submitted = enqueue_product_ai_task(
            product_id=data["product_id"],
            processing_type="full",
            auto_apply=data["auto_apply"],
            options=options,
        )
        return Response(
            {
                "task_id": task_id,
                "log_id": log_entry.id,
                "submitted": submitted,
                "product_id": product_id,
                "status": "queued",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class AIStatsView(APIView):
    """Статистика AI обработки за период."""

    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        summary="Получить статистику AI-обработки",
        parameters=[AIStatsQuerySerializer],
        responses={
            200: AIStatsResponseSerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Ошибки валидации query-параметров",
            ),
        },
    )
    def get(self, request):
        serializer = AIStatsQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        days = serializer.validated_data["days"]
        since = timezone.now() - timedelta(days=days)
        qs = AIProcessingLog.objects.filter(created_at__gte=since)
        stats = qs.aggregate(
            total_processed=Count("id"),
            successful=Count("id", filter=Q(status=AIProcessingStatus.APPROVED)),
            completed=Count("id", filter=Q(status=AIProcessingStatus.COMPLETED)),
            failed=Count("id", filter=Q(status=AIProcessingStatus.FAILED)),
            moderation=Count("id", filter=Q(status=AIProcessingStatus.MODERATION)),
            avg_confidence=Avg("category_confidence"),
            total_cost=Sum("cost_usd"),
            avg_processing_time=Avg("processing_time_ms"),
        )
        by_status = (
            qs.values("status")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        return Response(
            {
                "period_days": days,
                "summary": stats,
                "by_status": list(by_status),
            }
        )
