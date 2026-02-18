# Catalog Refactoring Status

## Objective
Refactor the product catalog to use a unified `AbstractDomainProduct` base class and generic `Product` model (shadow copy pattern). Also, expand the catalog with new domains.

## Progress

### Wave 1: Refactor Existing Legacy Models (✅ Done)
- [x] **ClothingProduct**
  - Inherits from `AbstractDomainProduct`
  - Redundant fields removed
  - `base_product` link established
  - `save()` syncs to `Product`
  - Upload paths compatible
- [x] **ShoeProduct**
  - Inherits from `AbstractDomainProduct`
  - Redundant fields removed
  - `save()` syncs to `Product`
- [x] **ElectronicsProduct**
  - Inherits from `AbstractDomainProduct`
  - Redundant fields removed
- [x] **FurnitureProduct**
  - Inherits from `AbstractDomainProduct`
  - Redundant fields removed
- [x] **JewelryProduct**
  - Inherits from `AbstractDomainProduct`
  - Custom upload paths preserved
- [x] **Verification**: All generic fields map correctly to `Product`. Signals cleaned up. Migrations applied.

### Wave 2: Create New Medical/Health Domains (✅ Done in previous session)
- [x] **MedicineProduct**
- [x] **VitaminProduct** (Supplements)
- [x] **MedicalEquipmentProduct**

### Wave 3: Create New Lifestyle Domains (✅ Done)
- [x] **SportsProduct** (Sporting Goods)
  - Fields: `sport_type`, `equipment_type`, `material` (size moved to variant)
  - Variants implemented
- [x] **AutoPartProduct** (Auto Parts)
  - Fields: `part_number`, `car_brand`, `car_model`, `compatibility_years`
  - Variants implemented

### Future Tasks
- [ ] Update Frontend to handle new `product_type` values.
- [ ] Refactor `Admin` for Wave 1 to use `_SimpleDomainAdmin` (low priority).
