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
            "processing_type",
            "generated_title",
            "generated_description",
            "category_confidence",
            "created_at",
            "completed_at",
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


class GenerateContentRequestSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    processing_type = serializers.ChoiceField(
        choices=AIProcessingLog.PROCESSING_TYPES, default="full"
    )
    auto_apply = serializers.BooleanField(default=False)
    generate_description = serializers.BooleanField(required=False)
    categorize = serializers.BooleanField(required=False)
    analyze_images = serializers.BooleanField(required=False)
