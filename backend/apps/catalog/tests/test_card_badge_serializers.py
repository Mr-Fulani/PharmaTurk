import pytest

from apps.catalog.serializers import (
    AccessoryProductSerializer,
    AutoPartProductSerializer,
    BookProductSerializer,
    ClothingProductSerializer,
    ElectronicsProductSerializer,
    FurnitureProductSerializer,
    HeadwearProductSerializer,
    IncenseProductSerializer,
    IslamicClothingProductSerializer,
    JewelryProductSerializer,
    MedicalEquipmentProductSerializer,
    MedicineProductSerializer,
    PerfumeryProductSerializer,
    ProductSerializer,
    ProductSearchSerializer,
    ShoeProductSerializer,
    SportsProductSerializer,
    SupplementProductSerializer,
    TablewareProductSerializer,
    UnderwearProductSerializer,
)


@pytest.mark.parametrize(
    "serializer_class",
    [
        ProductSerializer,
        ProductSearchSerializer,
        ClothingProductSerializer,
        ShoeProductSerializer,
        ElectronicsProductSerializer,
        FurnitureProductSerializer,
        JewelryProductSerializer,
        BookProductSerializer,
        PerfumeryProductSerializer,
        MedicineProductSerializer,
        SupplementProductSerializer,
        MedicalEquipmentProductSerializer,
        TablewareProductSerializer,
        AccessoryProductSerializer,
        IncenseProductSerializer,
        SportsProductSerializer,
        AutoPartProductSerializer,
        HeadwearProductSerializer,
        UnderwearProductSerializer,
        IslamicClothingProductSerializer,
    ],
)
def test_product_card_serializers_expose_badge_flags(serializer_class):
    fields = set(serializer_class.Meta.fields)

    assert {"is_new", "is_featured"} <= fields
