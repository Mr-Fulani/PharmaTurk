import random
import string
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.catalog.models import (
    Category,
    ClothingProduct,
    ShoeProduct,
    JewelryProduct,
    ElectronicsProduct,
    FurnitureProduct,
    BookProduct,
    PerfumeryProduct,
    MedicineProduct,
    SupplementProduct,
    MedicalEquipmentProduct,
    TablewareProduct,
    AccessoryProduct,
    IncenseProduct,
    SportsProduct,
    AutoPartProduct,
)

# Mapping from root category slug to Domain Product Model and its specific fields
MODEL_MAPPING = {
    'medicines': (MedicineProduct, {'dosage_form': 'Таблетки', 'active_ingredient': 'Парацетамол', 'prescription_required': False}),
    'supplements': (SupplementProduct, {'form': 'Капсулы', 'main_ingredient': 'Витамин C'}),
    'medical-equipment': (MedicalEquipmentProduct, {'equipment_type': 'Тонометр', 'manufacturer_name': 'Omron'}),
    'clothing': (ClothingProduct, {'size': 'M', 'color': 'Черный', 'material': 'Хлопок', 'season': 'Лето', 'gender': 'unisex'}),
    'underwear': (ClothingProduct, {'size': 'S', 'color': 'Белый', 'material': 'Хлопок'}), 
    'shoes': (ShoeProduct, {'size': '42', 'color': 'Коричневый', 'material': 'Кожа', 'gender': 'unisex'}),
    'headwear': (ClothingProduct, {'size': 'L', 'color': 'Серый', 'material': 'Шерсть', 'season': 'Зима'}),
    'electronics': (ElectronicsProduct, {'brand_name': 'TestBrand', 'manufacturer': 'TestManufacturer'}),
    'furniture': (FurnitureProduct, {'material': 'Дерево', 'dimensions': '100x50x50', 'color': 'Дуб'}),
    'jewelry': (JewelryProduct, {'metal_type': 'Золото', 'gemstone': 'Бриллиант', 'weight': '5.5'}),
    'books': (BookProduct, {'isbn': '978-3-16-148410-0', 'publisher': 'TestPublisher', 'publication_year': 2023, 'binding_type': 'Твердый'}),
    'perfumery': (PerfumeryProduct, {'fragrance_family': 'Цветочные', 'volume_ml': 50}),
    'tableware': (TablewareProduct, {'material': 'Керамика', 'color': 'Белый'}),
    'accessories': (AccessoryProduct, {'material': 'Кожа', 'color': 'Черный', 'accessory_type': 'Сумка', 'gender': 'unisex'}),
    'incense': (IncenseProduct, {'scent': 'Сандал', 'form': 'Палочки'}),
    'sports': (SportsProduct, {'sport_type': 'Фитнес', 'material': 'Пластик'}),
    'auto-parts': (AutoPartProduct, {'part_number': '12345-ABC', 'oem_number': 'OEM-9876', 'compatibility': 'Toyota, Honda'}),
    'uslugi': None, # Products not clearly defined here, maybe ignore
}

# Add fallback mappings if root slugs differ slightly
MODEL_MAPPING['medical_equipment'] = MODEL_MAPPING['medical-equipment']
MODEL_MAPPING['auto_parts'] = MODEL_MAPPING['auto-parts']

# Additional mappings from dry run
for shoe_type in ['kids-shoes', 'women-shoes', 'men-shoes', 'unisex-shoes']:
    MODEL_MAPPING[shoe_type] = MODEL_MAPPING['shoes']
MODEL_MAPPING['islamic-clothing'] = MODEL_MAPPING['clothing']

def get_root_category(category):
    current = category
    while current.parent_id:
        current = current.parent
    return current

class Command(BaseCommand):
    help = 'Generates 1-3 test products for each leaf category using domain-specific models.'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=2, help='Amount of products to create per category')
        parser.add_argument('--clear', action='store_true', help='Clear previously generated test products before creating new ones')
        parser.add_argument('--dry-run', action='store_true', help='Run without saving to DB')

    def handle(self, *args, **options):
        count_per_cat = options['count']
        clear = options['clear']
        dry_run = options['dry_run']

        if clear and not dry_run:
            self.stdout.write("Clearing previous test products...")
            # Delete products ending with [TEST]
            deleted = 0
            models_to_clear = set()
            for value in MODEL_MAPPING.values():
                if value:
                    models_to_clear.add(value[0])
                    
            for model_class in models_to_clear:
                try:
                    qs = model_class.objects.filter(name__endswith="[TEST]")
                    deleted += qs.count()
                    qs.delete()
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Error clearing {model_class.__name__}: {str(e)}"))
            self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} test products."))

        # Find leaf categories (categories that have no children)
        leaf_categories = Category.objects.filter(children__isnull=True)
        self.stdout.write(f"Found {leaf_categories.count()} leaf categories.")

        created_count = 0
        categories_handled = set()
        
        try:
            for category in leaf_categories:
                root = get_root_category(category)
                root_slug = root.slug.lower()
                
                mapping = MODEL_MAPPING.get(root_slug) or MODEL_MAPPING.get(root_slug.replace('-', '_'))
                
                if not mapping:
                    if root_slug not in categories_handled:
                        self.stdout.write(self.style.WARNING(f"No domain model mapping found for root slug '{root_slug}'. Skipping category '{category.name}'."))
                        categories_handled.add(root_slug)
                    continue
                
                model_class, specific_fields = mapping
                
                # Create products
                for i in range(count_per_cat):
                    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
                    name = f"Test {category.name} {i+1}-{suffix} [TEST]"
                    
                    slug = f"test-product-{category.id}-{i+1}-{suffix}".lower()
                    price = round(random.uniform(10.0, 5000.0), 2)
                    
                    base_fields = {
                        'name': name[:200],  # just in case it gets too long
                        'slug': slug[:200],
                        'description': f"This is an auto-generated test product for category {category.name}.",
                        'category': category,
                        'price': price,
                        'currency': 'RUB',
                        'is_available': True,
                        'stock_quantity': random.randint(10, 100),
                        'is_active': True,
                    }
                    
                    # Apply category specific data
                    product_data = base_fields.copy()
                    for key, value in specific_fields.items():
                        # Check if model actually has this field to prevent errors
                        if hasattr(model_class, key) or key in [f.name for f in model_class._meta.get_fields()]:
                            product_data[key] = value
                    
                    if not dry_run:
                        try:
                            product = model_class(**product_data)
                            product.save()
                            created_count += 1
                        except Exception as inner_e:
                            self.stdout.write(self.style.ERROR(f"Fail creating product '{name}': {inner_e}"))
                    else:
                        created_count += 1
            
            if dry_run:
                self.stdout.write(self.style.SUCCESS(f"Dry run completed. Would have generated {created_count} test products."))
            else:
                self.stdout.write(self.style.SUCCESS(f"Successfully generated {created_count} test products."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during execution: {str(e)}"))
