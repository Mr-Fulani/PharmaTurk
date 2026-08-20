"""Request serializers for recommendation endpoints."""
from rest_framework import serializers

from .services.safe_image_fetcher import ImageFetchError, validate_image_url_syntax


class VisualSearchRequestSerializer(serializers.Serializer):
    image_url = serializers.CharField(max_length=2048, trim_whitespace=True)
    limit = serializers.IntegerField(default=20, min_value=1, max_value=24)

    def validate_image_url(self, value: str) -> str:
        try:
            validate_image_url_syntax(value)
        except ImageFetchError:
            raise serializers.ValidationError("Invalid image URL.") from None
        return value


class CompleteTheLookRequestSerializer(serializers.Serializer):
    """Bound and type-check the public product lookup before ORM access."""

    product_id = serializers.IntegerField(min_value=1)


class RecommendationErrorSerializer(serializers.Serializer):
    error = serializers.CharField(required=False)
    detail = serializers.CharField(required=False)
    message = serializers.CharField(required=False)


class VisualSearchMatchSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    similarity = serializers.FloatField()
    product = serializers.JSONField()


class VisualSearchResponseSerializer(serializers.Serializer):
    results = VisualSearchMatchSerializer(many=True)


class PersonalizedRecommendationsResponseSerializer(serializers.Serializer):
    based_on = serializers.CharField()
    count = serializers.IntegerField(required=False)
    # A personalized row wraps a card in `product`; a trending row is the card.
    results = serializers.ListField(child=serializers.JSONField())


class ComplementaryGroupSerializer(serializers.Serializer):
    relation_type = serializers.CharField()
    category_id = serializers.IntegerField()
    items = serializers.ListField(child=serializers.JSONField())


class CompleteTheLookResponseSerializer(serializers.Serializer):
    base_product_id = serializers.IntegerField()
    complementary_items = ComplementaryGroupSerializer(many=True)
