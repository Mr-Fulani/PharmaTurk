import os
import sys
import django
from django.conf import settings

# Setup Django path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
try:
    django.setup()
except Exception as e:
    print(f"Django setup failed: {e}")
    sys.exit(1)

from apps.catalog.serializers import (
    ShoeProductSerializer, JewelryProductSerializer, MedicineProductSerializer, 
    SportsProductSerializer, ProductSerializer,
    AutoPartProductSerializer
)

serializers_list = [
    ShoeProductSerializer, 
    JewelryProductSerializer, 
    MedicineProductSerializer, 
    SportsProductSerializer,
    ProductSerializer,
    AutoPartProductSerializer
]

print("Verifying Serializers for SEO fields...")
for serializer_class in serializers_list:
    name = serializer_class.__name__
    try:
        # Check Meta.fields
        meta_fields = getattr(serializer_class.Meta, 'fields', [])
        if 'meta_title' in meta_fields:
            print(f"[OK] {name} has 'meta_title' in Meta.fields")
        else:
            print(f"[FAIL] {name} MISSING 'meta_title' in Meta.fields")
            
        # Check actual field binding
        instance = serializer_class()
        fields = instance.fields
        if 'meta_title' in fields:
             print(f"[OK] {name} binds 'meta_title'")
        else:
             print(f"[FAIL] {name} does NOT bind 'meta_title'")

    except Exception as e:
        print(f"[ERROR] Checking {name}: {e}")
        if name == "SportsProductSerializer":
             print(f"MRO: {serializer_class.mro()}")
             print(f"Declared fields: {serializer_class._declared_fields}")


# Also verify resolve_book_seo_value import
try:
    from apps.catalog.seo_defaults import resolve_book_seo_value
    print("[OK] resolve_book_seo_value imported successfully")
except ImportError:
    print("[FAIL] could not import resolve_book_seo_value")
