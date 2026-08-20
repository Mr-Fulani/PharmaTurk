import pytest
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.views import APIView

from api.views import HealthCheckView, LivenessCheckView
from apps.catalog.views import (
    AccessoryProductViewSet,
    AutoPartProductViewSet,
    BannerViewSet,
    BookProductViewSet,
    BrandViewSet,
    CategoryViewSet,
    ClothingCategoryViewSet,
    ClothingProductViewSet,
    ElectronicsCategoryViewSet,
    ElectronicsProductViewSet,
    FurnitureProductViewSet,
    HeadwearProductViewSet,
    IncenseProductViewSet,
    IslamicClothingProductViewSet,
    JewelryProductViewSet,
    MedicalEquipmentProductViewSet,
    MedicineProductViewSet,
    PerfumeryProductViewSet,
    ProductViewSet,
    ServiceViewSet,
    ShoeCategoryViewSet,
    ShoeProductViewSet,
    SportsProductViewSet,
    SupplementProductViewSet,
    TablewareProductViewSet,
    UnderwearProductViewSet,
)
from apps.payments.views import CryptoWebhookView, PaymentInitView
from apps.settings.views import FooterSettingsViewSet


PUBLIC_CATALOG_VIEWS = (
    CategoryViewSet,
    BannerViewSet,
    BrandViewSet,
    ProductViewSet,
    ClothingCategoryViewSet,
    ClothingProductViewSet,
    ShoeCategoryViewSet,
    ShoeProductViewSet,
    ElectronicsCategoryViewSet,
    ElectronicsProductViewSet,
    JewelryProductViewSet,
    FurnitureProductViewSet,
    ServiceViewSet,
    BookProductViewSet,
    PerfumeryProductViewSet,
    MedicineProductViewSet,
    SupplementProductViewSet,
    MedicalEquipmentProductViewSet,
    TablewareProductViewSet,
    AccessoryProductViewSet,
    IncenseProductViewSet,
    SportsProductViewSet,
    AutoPartProductViewSet,
    HeadwearProductViewSet,
    UnderwearProductViewSet,
    IslamicClothingProductViewSet,
)


def test_unannotated_drf_views_are_authenticated_by_default():
    class ProtectedByDefault(APIView):
        pass

    assert ProtectedByDefault.permission_classes == [IsAuthenticated]


@pytest.mark.parametrize("view_class", PUBLIC_CATALOG_VIEWS)
def test_public_catalog_contract_is_explicit(view_class):
    assert view_class.permission_classes == [AllowAny]


def test_other_public_and_diagnostic_endpoints_are_explicit():
    assert HealthCheckView.permission_classes == [AllowAny]
    assert LivenessCheckView.permission_classes == [AllowAny]
    assert FooterSettingsViewSet.permission_classes == [AllowAny]
    assert CryptoWebhookView.permission_classes == [AllowAny]


def test_dummy_payment_initialization_is_staff_only():
    assert PaymentInitView.permission_classes == [IsAdminUser]
