from rest_framework import serializers
from .models import AIProcessingLog, AITemplate, AIModerationQueue


class AIProcessingLogSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = AIProcessingLog
        fields = [
            "id",
            "product",
            "product_name",
            "status",
            "application_status",
            "processing_type",
            "generated_title",
            "generated_description",
            "category_confidence",
            "created_at",
            "completed_at",
            "applied_at",
        ]
        read_only_fields = fields


class AIProcessingDetailSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = AIProcessingLog
        fields = "__all__"


class AIModerationQueueSerializer(serializers.ModelSerializer):
    log_entry_id = serializers.IntegerField(source="log_entry.id", read_only=True)
    product_id = serializers.IntegerField(source="log_entry.product_id", read_only=True)
    product_name = serializers.CharField(
        source="log_entry.product.name", read_only=True
    )

    class Meta:
        model = AIModerationQueue
        fields = [
            "id",
            "log_entry",
            "log_entry_id",
            "product_id",
            "product_name",
            "priority",
            "reason",
            "assigned_to",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = ["created_at", "resolved_at"]


class AITemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AITemplate
        fields = [
            "id",
            "name",
            "template_type",
            "category",
            "content",
            "language",
            "is_active",
            "usage_count",
            "success_rate",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["usage_count", "success_rate", "created_at", "updated_at"]


class GenerateContentRequestSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    processing_type = serializers.ChoiceField(
        choices=AIProcessingLog.PROCESSING_TYPES, default="full"
    )
    auto_apply = serializers.BooleanField(default=False)
    generate_description = serializers.BooleanField(required=False)
    categorize = serializers.BooleanField(required=False)
    analyze_images = serializers.BooleanField(required=False)
    use_images = serializers.BooleanField(required=False)


class ProcessProductRequestSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    generate_description = serializers.BooleanField(default=True)
    categorize = serializers.BooleanField(default=True)
    analyze_images = serializers.BooleanField(default=True)
    use_images = serializers.BooleanField(default=True)
    auto_apply = serializers.BooleanField(default=False)


class ProcessProductBodySerializer(serializers.Serializer):
    """Client-supplied fields; product_id is taken exclusively from the URL."""

    generate_description = serializers.BooleanField(default=True)
    categorize = serializers.BooleanField(default=True)
    analyze_images = serializers.BooleanField(default=True)
    use_images = serializers.BooleanField(default=True)
    auto_apply = serializers.BooleanField(default=False)


class AIStatsQuerySerializer(serializers.Serializer):
    days = serializers.IntegerField(default=30, min_value=1, max_value=365)


class AIQueuedResponseSerializer(serializers.Serializer):
    """Response returned by the asynchronous AI processing endpoints."""

    task_id = serializers.CharField(allow_blank=True)
    log_id = serializers.IntegerField()
    submitted = serializers.BooleanField()
    product_id = serializers.IntegerField()
    status = serializers.CharField()
    message = serializers.CharField(required=False)


class AIStatsSummarySerializer(serializers.Serializer):
    total_processed = serializers.IntegerField()
    successful = serializers.IntegerField()
    completed = serializers.IntegerField()
    failed = serializers.IntegerField()
    moderation = serializers.IntegerField()
    avg_confidence = serializers.FloatField(allow_null=True)
    # The view returns raw aggregate data, so DRF's JSON encoder emits Decimal as a number.
    total_cost = serializers.FloatField(allow_null=True)
    avg_processing_time = serializers.FloatField(allow_null=True)


class AIStatsByStatusSerializer(serializers.Serializer):
    status = serializers.CharField()
    count = serializers.IntegerField()


class AIStatsResponseSerializer(serializers.Serializer):
    period_days = serializers.IntegerField()
    summary = AIStatsSummarySerializer()
    by_status = AIStatsByStatusSerializer(many=True)
