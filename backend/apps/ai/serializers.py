from rest_framework import serializers
from .models import AIProcessingLog, AITemplate

class AIProcessingLogSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = AIProcessingLog
        fields = [
            'id', 'product', 'product_name', 'status', 'processing_type',
            'generated_title', 'generated_description', 
            'category_confidence', 'created_at', 'completed_at'
        ]
        read_only_fields = fields

class AIProcessingDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIProcessingLog
        fields = '__all__'

class GenerateContentRequestSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    processing_type = serializers.ChoiceField(choices=AIProcessingLog.PROCESSING_TYPES, default='full')
    auto_apply = serializers.BooleanField(default=False)
