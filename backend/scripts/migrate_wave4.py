import os
import django

# Настройка окружения Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.catalog.models import (
    Product, Category, 
    JewelryProduct, FurnitureProduct, ClothingProduct,
    JewelryVariant, FurnitureVariant, ClothingProductSize
)
from django.db import transaction

def get_descendant_ids(slugs):
    ids = set()
    categories = Category.objects.filter(slug__in=slugs)
    
    def add_children(cat_id):
        child_ids = list(Category.objects.filter(parent_id=cat_id).values_list('id', flat=True))
        for cid in child_ids:
            if cid not in ids:
                ids.add(cid)
                add_children(cid)

    for cat in categories:
        ids.add(cat.id)
        add_children(cat.id)
    return ids

@transaction.atomic
def migrate():
    # 1. JEWELRY
    jewelry_cat_ids = get_descendant_ids(['jewelry'])
    jewelry_products = Product.objects.filter(
        models.Q(product_type='jewelry') | models.Q(category_id__in=jewelry_cat_ids)
    ).distinct()
    
    print(f"Checking {jewelry_products.count()} potential jewelry products...")
    for p in jewelry_products:
        if JewelryProduct.objects.filter(base_product=p).exists():
            continue
        
        # Check if slug exists in JewelryProduct
        slug = p.slug
        if JewelryProduct.objects.filter(slug=slug).exists():
            slug = f"{slug}-j"

        jp = JewelryProduct.objects.create(
            base_product=p,
            name=p.name,
            slug=slug,
            description=p.description or "",
            category=p.category,
            brand=p.brand,
            price=p.price,
            currency=p.currency or 'RUB',
            old_price=p.old_price,
            is_available=p.is_available,
            stock_quantity=p.stock_quantity,
            main_image=p.main_image or "",
            external_id=p.external_id or "",
            external_url=p.external_url or "",
            external_data=p.external_data or {},
            is_active=p.is_active,
            is_new=p.is_new,
            is_featured=p.is_featured,
            jewelry_type='ring' if 'кольцо' in p.name.lower() else 'bracelet' if 'браслет' in p.name.lower() else 'necklace',
        )
        p.product_type = 'jewelry'
        p.save()
        print(f"  - Created JewelryProduct for {p.name} (ID: {p.id})")

    # 2. FURNITURE
    furniture_cat_ids = get_descendant_ids(['furniture'])
    furniture_products = Product.objects.filter(
        models.Q(product_type='furniture') | models.Q(category_id__in=furniture_cat_ids)
    ).distinct()
    
    print(f"Checking {furniture_products.count()} potential furniture products...")
    for p in furniture_products:
        if FurnitureProduct.objects.filter(base_product=p).exists():
            continue

        slug = p.slug
        if FurnitureProduct.objects.filter(slug=slug).exists():
            slug = f"{slug}-f"

        fp = FurnitureProduct.objects.create(
            base_product=p,
            name=p.name,
            slug=slug,
            description=p.description or "",
            category=p.category,
            brand=p.brand,
            price=p.price,
            currency=p.currency or 'RUB',
            old_price=p.old_price,
            is_available=p.is_available,
            stock_quantity=p.stock_quantity,
            main_image=p.main_image or "",
            external_id=p.external_id or "",
            external_url=p.external_url or "",
            external_data=p.external_data or {},
            is_active=p.is_active,
            is_new=p.is_new,
            is_featured=p.is_featured,
        )
        p.product_type = 'furniture'
        p.save()
        print(f"  - Created FurnitureProduct for {p.name} (ID: {p.id})")

    # 3. CLOTHING (Underwear, Headwear)
    clothing_cat_ids = get_descendant_ids(['clothing', 'underwear', 'headwear'])
    clothing_products = Product.objects.filter(
        models.Q(product_type__in=['clothing', 'underwear', 'headwear', 'headgear']) | models.Q(category_id__in=clothing_cat_ids)
    ).distinct()
    
    print(f"Checking {clothing_products.count()} potential clothing products...")
    for p in clothing_products:
        if ClothingProduct.objects.filter(base_product=p).exists():
            continue

        slug = p.slug
        if ClothingProduct.objects.filter(slug=slug).exists():
            slug = f"{slug}-c"

        cp = ClothingProduct.objects.create(
            base_product=p,
            name=p.name,
            slug=slug,
            description=p.description or "",
            category=p.category,
            brand=p.brand,
            price=p.price,
            currency=p.currency or 'RUB',
            old_price=p.old_price,
            is_available=p.is_available,
            stock_quantity=p.stock_quantity,
            main_image=p.main_image or "",
            external_id=p.external_id or "",
            external_url=p.external_url or "",
            external_data=p.external_data or {},
            is_active=p.is_active,
            is_new=p.is_new,
            is_featured=p.is_featured,
        )
        p.product_type = 'clothing'
        p.save()
        print(f"  - Created ClothingProduct for {p.name} (ID: {p.id})")

if __name__ == '__main__':
    from django.db import models
    migrate()
