from rest_framework import serializers


class VapiPullQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(default=1, min_value=1, max_value=10_000)
    page_size = serializers.IntegerField(default=100, min_value=1, max_value=100)
    category = serializers.CharField(required=False, allow_blank=False, max_length=128)
    brand = serializers.CharField(required=False, allow_blank=False, max_length=128)
    search = serializers.CharField(required=False, allow_blank=False, max_length=256)


class VapiProductDetailsQuerySerializer(serializers.Serializer):
    product_id = serializers.CharField(min_length=1, max_length=128)


class VapiSearchQuerySerializer(serializers.Serializer):
    query = serializers.CharField(min_length=1, max_length=256)
    limit = serializers.IntegerField(default=50, min_value=1, max_value=100)


class VapiFullSyncQuerySerializer(serializers.Serializer):
    max_pages = serializers.IntegerField(default=100, min_value=1, max_value=100)


class VapiPullParametersSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    category = serializers.CharField(allow_null=True)
    brand = serializers.CharField(allow_null=True)
    search = serializers.CharField(allow_null=True)


class VapiPullResponseSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    message = serializers.CharField()
    parameters = VapiPullParametersSerializer()


class VapiProductDetailsResponseSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    message = serializers.CharField()
    product_id = serializers.CharField()


class VapiSearchResponseSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    message = serializers.CharField()
    query = serializers.CharField()
    limit = serializers.IntegerField()


class VapiTaskResponseSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    message = serializers.CharField()


class VapiFullSyncResponseSerializer(VapiTaskResponseSerializer):
    max_pages = serializers.IntegerField()
