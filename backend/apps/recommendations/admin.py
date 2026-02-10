"""Admin for recommendations app."""
from django.contrib import admin
from .models import ProductVector, RecommendationEvent, UserEmbedding


@admin.register(ProductVector)
class ProductVectorAdmin(admin.ModelAdmin):
    list_display = ("product", "qdrant_id", "vector_type", "is_active", "last_synced")
    list_filter = ("vector_type", "is_active")
    search_fields = ("product__name", "qdrant_id")
    raw_id_fields = ("product",)


@admin.register(RecommendationEvent)
class RecommendationEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "event_type",
        "algorithm",
        "source_product",
        "recommended_product",
        "position",
        "created_at",
    )
    list_filter = ("event_type", "algorithm", "created_at")
    search_fields = ("session_id",)
    raw_id_fields = ("source_product", "recommended_product", "user")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)


@admin.register(UserEmbedding)
class UserEmbeddingAdmin(admin.ModelAdmin):
    list_display = ("user", "last_updated", "price_sensitivity")
    list_filter = ("price_sensitivity",)
    search_fields = ("user__email", "user__username")
    raw_id_fields = ("user",)
    readonly_fields = ("last_updated",)
