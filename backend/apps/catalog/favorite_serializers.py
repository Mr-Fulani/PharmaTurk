"""Favorite API serializers and public product-identity resolution."""

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import (
    BookProduct,
    BookVariant,
    ClothingProduct,
    ClothingVariant,
    ElectronicsProduct,
    Favorite,
    FurnitureProduct,
    FurnitureVariant,
    HeadwearProduct,
    HeadwearVariant,
    IslamicClothingProduct,
    IslamicClothingVariant,
    JewelryProduct,
    JewelryVariant,
    PerfumeryVariant,
    Product,
    Service,
    ShoeProduct,
    ShoeVariant,
    UnderwearProduct,
    UnderwearVariant,
)


class FavoriteSerializer(serializers.ModelSerializer):
    """Serialize favorites while preserving canonical public product identity."""

    product = serializers.SerializerMethodField()

    class Meta:
        model = Favorite
        fields = ["id", "product", "chosen_size", "created_at"]
        read_only_fields = ["id", "chosen_size", "created_at"]

    @staticmethod
    def _get_variant_parent_slug(product, external_data):
        variant_slug = external_data.get("source_variant_slug")
        source_type = str(
            external_data.get("effective_type")
            or external_data.get("source_type")
            or getattr(product, "product_type", "")
        ).strip().lower().replace("-", "_")
        if not variant_slug:
            return None

        variant_models = {
            "clothing": ClothingVariant,
            "shoes": ShoeVariant,
            "furniture": FurnitureVariant,
            "jewelry": JewelryVariant,
            "books": BookVariant,
            "perfumery": PerfumeryVariant,
            "headwear": HeadwearVariant,
            "underwear": UnderwearVariant,
            "islamic_clothing": IslamicClothingVariant,
        }
        variant_model = variant_models.get(source_type)
        if variant_model is None:
            return None

        variant = (
            variant_model.objects.filter(slug=variant_slug, is_active=True)
            .select_related("product")
            .first()
        )
        parent = getattr(variant, "product", None)
        return getattr(parent, "slug", None) or None

    def get_product(self, obj):
        """Serialize the concrete product type behind a favorite."""
        # Imported lazily because catalog.serializers re-exports this class.
        from .serializers import (
            BookProductSerializer,
            ClothingProductSerializer,
            ElectronicsProductSerializer,
            FurnitureProductSerializer,
            HeadwearProductSerializer,
            IslamicClothingProductSerializer,
            JewelryProductSerializer,
            ProductSerializer,
            ServiceSerializer,
            ShoeProductSerializer,
            UnderwearProductSerializer,
        )

        product = obj.product
        request = self.context.get("request")

        def _pin_base_product_fields(data: dict, base_pk: int) -> dict:
            """Keep favorite IDs aligned with the canonical Product object."""
            data["id"] = base_pk
            data["base_product_id"] = base_pk
            return data

        product_type = "medicines"
        if isinstance(product, ClothingProduct):
            product_type = "clothing"
            product_data = ClothingProductSerializer(
                product, context={"request": request}
            ).data
        elif isinstance(product, ShoeProduct):
            product_type = "shoes"
            product_data = ShoeProductSerializer(
                product, context={"request": request}
            ).data
        elif isinstance(product, ElectronicsProduct):
            product_type = "electronics"
            product_data = ElectronicsProductSerializer(
                product, context={"request": request}
            ).data
        elif isinstance(product, FurnitureProduct):
            product_type = "furniture"
            product_data = FurnitureProductSerializer(
                product, context={"request": request}
            ).data
        elif isinstance(product, JewelryProduct):
            product_type = "jewelry"
            product_data = JewelryProductSerializer(
                product, context={"request": request}
            ).data
        elif isinstance(product, BookProduct):
            product_type = "books"
            product_data = BookProductSerializer(
                product, context={"request": request}
            ).data
            if product.base_product_id:
                _pin_base_product_fields(product_data, product.base_product_id)
        elif isinstance(product, HeadwearProduct):
            product_type = "headwear"
            product_data = HeadwearProductSerializer(
                product, context={"request": request}
            ).data
            if product.base_product_id:
                _pin_base_product_fields(product_data, product.base_product_id)
        elif isinstance(product, UnderwearProduct):
            product_type = "underwear"
            product_data = UnderwearProductSerializer(
                product, context={"request": request}
            ).data
            if product.base_product_id:
                _pin_base_product_fields(product_data, product.base_product_id)
        elif isinstance(product, IslamicClothingProduct):
            product_type = "islamic_clothing"
            product_data = IslamicClothingProductSerializer(
                product, context={"request": request}
            ).data
            if product.base_product_id:
                _pin_base_product_fields(product_data, product.base_product_id)
        elif isinstance(product, Product):
            product_external = getattr(product, "external_data", None) or {}
            external_type = (
                product_external.get("effective_type")
                if isinstance(product_external, dict)
                else None
            )
            raw_type = (
                external_type
                or getattr(product, "product_type", None)
                or "medicines"
            )
            product_type = str(raw_type).strip().lower().replace("-", "_")
            headwear_item = underwear_item = islamic_item = None
            if product_type == "headwear":
                try:
                    headwear_item = product.headwear_item
                except HeadwearProduct.DoesNotExist:
                    headwear_item = None
            if product_type == "underwear":
                try:
                    underwear_item = product.underwear_item
                except UnderwearProduct.DoesNotExist:
                    underwear_item = None
            if product_type in ("islamic_clothing", "islamic-clothing"):
                try:
                    islamic_item = product.islamic_clothing_item
                except IslamicClothingProduct.DoesNotExist:
                    islamic_item = None
            book_item = None
            if product_type == "books":
                try:
                    book_item = product.book_item
                except BookProduct.DoesNotExist:
                    book_item = None
            if book_item is not None:
                product_data = BookProductSerializer(
                    book_item, context={"request": request}
                ).data
                _pin_base_product_fields(product_data, product.id)
            elif headwear_item is not None:
                product_data = HeadwearProductSerializer(
                    headwear_item, context={"request": request}
                ).data
                _pin_base_product_fields(product_data, product.id)
            elif underwear_item is not None:
                product_data = UnderwearProductSerializer(
                    underwear_item, context={"request": request}
                ).data
                _pin_base_product_fields(product_data, product.id)
            elif islamic_item is not None:
                product_data = IslamicClothingProductSerializer(
                    islamic_item, context={"request": request}
                ).data
                _pin_base_product_fields(product_data, product.id)
            else:
                product_data = ProductSerializer(
                    product, context={"request": request}
                ).data
        elif isinstance(product, Service):
            product_type = "uslugi"
            product_data = ServiceSerializer(
                product, context={"request": request}
            ).data
        else:
            base_product_id = getattr(product, "base_product_id", None)
            base_product = (
                getattr(product, "base_product", None)
                if base_product_id
                else None
            )
            product_type = (
                getattr(base_product, "product_type", None)
                or getattr(product, "_domain_product_type", None)
                or product_type
            )
            product_data = {
                "id": getattr(product, "id", None),
                "name": getattr(product, "name", "Unknown"),
                "slug": getattr(product, "slug", ""),
                "price": (
                    str(getattr(product, "price", ""))
                    if hasattr(product, "price")
                    else None
                ),
                "currency": getattr(product, "currency", ""),
                "main_image_url": (
                    getattr(product, "main_image", None)
                    or getattr(product, "main_image_url", None)
                ),
                "video_url": (
                    getattr(product, "video_url", None)
                    or getattr(product, "main_video_url", None)
                    or getattr(product, "main_video", None)
                ),
            }

        canonical_product_id = getattr(product, "base_product_id", None)
        if canonical_product_id:
            _pin_base_product_fields(product_data, canonical_product_id)

        product_data["_product_type"] = str(product_type).replace("_", "-")
        product_data["favorite_chosen_size"] = (
            getattr(obj, "chosen_size", "") or ""
        )
        external_data = (
            getattr(product, "external_data", None)
            if isinstance(product, Product)
            else None
        )
        if isinstance(external_data, dict):
            variant_slug = external_data.get("source_variant_slug")
            if variant_slug:
                product_data["favorite_variant_slug"] = variant_slug
                parent_slug = self._get_variant_parent_slug(
                    product, external_data
                )
                if parent_slug:
                    product_data["favorite_parent_slug"] = parent_slug
        return product_data


def resolve_product_for_favorites_api(product_id, product_type_raw):
    """Resolve the canonical public identity accepted by favorite APIs."""
    try:
        product_id = int(product_id)
    except (TypeError, ValueError):
        raise serializers.ValidationError(
            {"product_id": "Некорректный product_id"}
        )

    requested_type = str(product_type_raw or "").strip().lower().replace("-", "_")
    requested_type = {
        "medical_accessories": "accessories",
        "medical_accessory": "accessories",
        "accessory": "accessories",
    }.get(requested_type, requested_type)

    if requested_type in {"uslugi", "services", "service"}:
        service = Service.objects.filter(id=product_id, is_active=True).first()
        if service is None:
            raise serializers.ValidationError(
                {"product_id": "Услуга не найдена"}
            )
        return service, "uslugi"

    product = Product.objects.filter(id=product_id, is_active=True).first()
    if product is None:
        raise serializers.ValidationError({"product_id": "Товар не найден"})

    external_data = (
        product.external_data if isinstance(product.external_data, dict) else {}
    )
    actual_type = str(
        external_data.get("effective_type")
        or product.product_type
        or "medicines"
    ).strip().lower().replace("-", "_")
    actual_type = {
        "medical_accessories": "accessories",
        "medical_accessory": "accessories",
        "accessory": "accessories",
    }.get(actual_type, actual_type)

    if requested_type and requested_type != actual_type:
        raise serializers.ValidationError(
            {"product_id": "Тип товара не соответствует product_id"}
        )
    return product, actual_type


class AddToFavoriteSerializer(serializers.Serializer):
    """Validate adding or removing a product from favorites."""

    product_id = serializers.IntegerField(required=False, allow_null=True)
    product_type = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    product_slug = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    size = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )

    def validate(self, attrs):
        from apps.orders.serializers import resolve_product_like_add_to_cart

        slug = (attrs.get("product_slug") or "").strip()
        product_type = attrs.get("product_type")
        size_raw = attrs.get("size")
        size = (size_raw or "").strip() if size_raw is not None else ""

        if slug:
            normalized_type = (
                str(product_type or "").strip().lower().replace("-", "_")
            )
            if not normalized_type:
                raise serializers.ValidationError(
                    {
                        "product_type": _(
                            "product_type обязателен при использовании product_slug"
                        )
                    }
                )
            if normalized_type in {"uslugi", "services", "service"}:
                service = Service.objects.filter(
                    slug=slug, is_active=True
                ).first()
                if service is None:
                    raise serializers.ValidationError(
                        {"product_slug": _("Услуга не найдена")}
                    )
                attrs["_product"] = service
                attrs["_chosen_size"] = ""
                attrs["_product_type"] = "uslugi"
                return attrs

            if size:
                product, chosen = resolve_product_like_add_to_cart(
                    product_id=None,
                    product_type=product_type,
                    product_slug=slug,
                    size=size,
                )
            else:
                from apps.orders.serializers import resolve_variant_product

                try:
                    product = resolve_variant_product(normalized_type, slug)
                except Product.DoesNotExist:
                    raise serializers.ValidationError(
                        {"product_slug": _("Товар не найден")}
                    )
                chosen = ""
            attrs["_product"] = product
            attrs["_chosen_size"] = chosen or ""
            resolved_type = (
                getattr(product, "product_type", None)
                or product_type
                or "medicines"
            )
            attrs["_product_type"] = (
                str(resolved_type).strip().lower().replace("-", "_")
            )
            return attrs

        product_id = attrs.get("product_id")
        normalized_id = None
        if product_id is not None and product_id != "":
            try:
                normalized_id = int(product_id)
            except (TypeError, ValueError):
                normalized_id = None
        if not normalized_id or normalized_id <= 0:
            raise serializers.ValidationError(
                {"detail": _("Нужен product_id или product_slug")}
            )

        product, normalized_type = resolve_product_for_favorites_api(
            normalized_id, product_type
        )
        attrs["_product"] = product
        attrs["_chosen_size"] = ""
        attrs["_product_type"] = normalized_type
        return attrs
