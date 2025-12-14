# Generated migration for data migration
from django.db import migrations
import logging

logger = logging.getLogger(__name__)


def validate_data_before_migration(apps, schema_editor):
    """Валидация данных перед миграцией."""
    Category = apps.get_model('catalog', 'Category')
    ClothingCategory = apps.get_model('catalog', 'ClothingCategory')
    ShoeCategory = apps.get_model('catalog', 'ShoeCategory')
    ElectronicsCategory = apps.get_model('catalog', 'ElectronicsCategory')
    
    # Проверка на дубликаты slug
    existing_slugs = set(Category.objects.values_list('slug', flat=True))
    conflicts = []
    
    for old_cat in ClothingCategory.objects.all():
        if old_cat.slug in existing_slugs:
            conflicts.append(('clothing', old_cat.id, old_cat.slug))
    
    for old_cat in ShoeCategory.objects.all():
        if old_cat.slug in existing_slugs:
            conflicts.append(('shoe', old_cat.id, old_cat.slug))
    
    for old_cat in ElectronicsCategory.objects.all():
        if old_cat.slug in existing_slugs:
            conflicts.append(('electronics', old_cat.id, old_cat.slug))
    
    if conflicts:
        logger.warning(f"Найдены конфликты slug: {conflicts}")
    
    # Проверка целостности parent связей
    for old_cat in ClothingCategory.objects.all():
        if old_cat.parent_id and not ClothingCategory.objects.filter(id=old_cat.parent_id).exists():
            logger.warning(f"ClothingCategory {old_cat.id} имеет несуществующий parent {old_cat.parent_id}")
    
    for old_cat in ShoeCategory.objects.all():
        if old_cat.parent_id and not ShoeCategory.objects.filter(id=old_cat.parent_id).exists():
            logger.warning(f"ShoeCategory {old_cat.id} имеет несуществующий parent {old_cat.parent_id}")
    
    for old_cat in ElectronicsCategory.objects.all():
        if old_cat.parent_id and not ElectronicsCategory.objects.filter(id=old_cat.parent_id).exists():
            logger.warning(f"ElectronicsCategory {old_cat.id} имеет несуществующий parent {old_cat.parent_id}")


def migrate_category_data_forward(apps, schema_editor):
    """Переносит данные из ClothingCategory, ShoeCategory, ElectronicsCategory в Category."""
    Category = apps.get_model('catalog', 'Category')
    ClothingCategory = apps.get_model('catalog', 'ClothingCategory')
    ShoeCategory = apps.get_model('catalog', 'ShoeCategory')
    ElectronicsCategory = apps.get_model('catalog', 'ElectronicsCategory')
    
    # Валидация перед миграцией
    validate_data_before_migration(apps, schema_editor)
    
    # Словарь для маппинга старых категорий на новые (для обновления parent связей)
    category_mapping = {}
    
    # Получаем существующие slug для проверки конфликтов
    existing_slugs = set(Category.objects.values_list('slug', flat=True))
    
    # 1. Переносим ClothingCategory
    logger.info("Начинаем перенос ClothingCategory...")
    for old_cat in ClothingCategory.objects.all():
        # Обработка конфликтов slug
        slug_to_use = old_cat.slug
        if slug_to_use in existing_slugs:
            # Добавляем суффикс при конфликте
            counter = 1
            while f"{slug_to_use}-clothing-{counter}" in existing_slugs:
                counter += 1
            slug_to_use = f"{slug_to_use}-clothing-{counter}"
            logger.warning(f"Конфликт slug для ClothingCategory {old_cat.id}: {old_cat.slug} -> {slug_to_use}")
        
        new_cat, created = Category.objects.get_or_create(
            slug=slug_to_use,
            defaults={
                'name': old_cat.name,
                'description': old_cat.description,
                'gender': old_cat.gender,
                'clothing_type': old_cat.clothing_type,
                'external_id': old_cat.external_id,
                'external_data': old_cat.external_data,
                'is_active': old_cat.is_active,
                'sort_order': old_cat.sort_order,
                'created_at': old_cat.created_at,
                'updated_at': old_cat.updated_at,
            }
        )
        if not created:
            # Если категория уже существует, обновляем поля
            new_cat.gender = old_cat.gender
            new_cat.clothing_type = old_cat.clothing_type
            new_cat.save()
            logger.info(f"Обновлена существующая категория {new_cat.id} для ClothingCategory {old_cat.id}")
        else:
            logger.info(f"Создана новая категория {new_cat.id} для ClothingCategory {old_cat.id}")
        
        category_mapping[('clothing', old_cat.id)] = new_cat.id
        existing_slugs.add(slug_to_use)
    
    # 2. Переносим ShoeCategory
    logger.info("Начинаем перенос ShoeCategory...")
    for old_cat in ShoeCategory.objects.all():
        # Обработка конфликтов slug
        slug_to_use = old_cat.slug
        if slug_to_use in existing_slugs:
            counter = 1
            while f"{slug_to_use}-shoe-{counter}" in existing_slugs:
                counter += 1
            slug_to_use = f"{slug_to_use}-shoe-{counter}"
            logger.warning(f"Конфликт slug для ShoeCategory {old_cat.id}: {old_cat.slug} -> {slug_to_use}")
        
        new_cat, created = Category.objects.get_or_create(
            slug=slug_to_use,
            defaults={
                'name': old_cat.name,
                'description': old_cat.description,
                'gender': old_cat.gender,
                'shoe_type': old_cat.shoe_type,
                'external_id': old_cat.external_id,
                'external_data': old_cat.external_data,
                'is_active': old_cat.is_active,
                'sort_order': old_cat.sort_order,
                'created_at': old_cat.created_at,
                'updated_at': old_cat.updated_at,
            }
        )
        if not created:
            new_cat.gender = old_cat.gender
            new_cat.shoe_type = old_cat.shoe_type
            new_cat.save()
            logger.info(f"Обновлена существующая категория {new_cat.id} для ShoeCategory {old_cat.id}")
        else:
            logger.info(f"Создана новая категория {new_cat.id} для ShoeCategory {old_cat.id}")
        
        category_mapping[('shoe', old_cat.id)] = new_cat.id
        existing_slugs.add(slug_to_use)
    
    # 3. Переносим ElectronicsCategory
    logger.info("Начинаем перенос ElectronicsCategory...")
    for old_cat in ElectronicsCategory.objects.all():
        # Обработка конфликтов slug
        slug_to_use = old_cat.slug
        if slug_to_use in existing_slugs:
            counter = 1
            while f"{slug_to_use}-electronics-{counter}" in existing_slugs:
                counter += 1
            slug_to_use = f"{slug_to_use}-electronics-{counter}"
            logger.warning(f"Конфликт slug для ElectronicsCategory {old_cat.id}: {old_cat.slug} -> {slug_to_use}")
        
        new_cat, created = Category.objects.get_or_create(
            slug=slug_to_use,
            defaults={
                'name': old_cat.name,
                'description': old_cat.description,
                'device_type': old_cat.device_type,
                'external_id': old_cat.external_id,
                'external_data': old_cat.external_data,
                'is_active': old_cat.is_active,
                'sort_order': old_cat.sort_order,
                'created_at': old_cat.created_at,
                'updated_at': old_cat.updated_at,
            }
        )
        if not created:
            new_cat.device_type = old_cat.device_type
            new_cat.save()
            logger.info(f"Обновлена существующая категория {new_cat.id} для ElectronicsCategory {old_cat.id}")
        else:
            logger.info(f"Создана новая категория {new_cat.id} для ElectronicsCategory {old_cat.id}")
        
        category_mapping[('electronics', old_cat.id)] = new_cat.id
        existing_slugs.add(slug_to_use)
    
    # 4. Обновляем parent связи для ClothingCategory
    logger.info("Обновляем parent связи для ClothingCategory...")
    for old_cat in ClothingCategory.objects.all():
        if old_cat.parent_id:
            old_parent_id = old_cat.parent_id
            new_cat_id = category_mapping.get(('clothing', old_cat.id))
            new_parent_id = category_mapping.get(('clothing', old_parent_id))
            if new_cat_id and new_parent_id:
                Category.objects.filter(id=new_cat_id).update(parent_id=new_parent_id)
                logger.debug(f"Обновлен parent для категории {new_cat_id}: {new_parent_id}")
            else:
                logger.warning(f"Не удалось обновить parent для ClothingCategory {old_cat.id}: new_cat_id={new_cat_id}, new_parent_id={new_parent_id}")
    
    # 5. Обновляем parent связи для ShoeCategory
    logger.info("Обновляем parent связи для ShoeCategory...")
    for old_cat in ShoeCategory.objects.all():
        if old_cat.parent_id:
            old_parent_id = old_cat.parent_id
            new_cat_id = category_mapping.get(('shoe', old_cat.id))
            new_parent_id = category_mapping.get(('shoe', old_parent_id))
            if new_cat_id and new_parent_id:
                Category.objects.filter(id=new_cat_id).update(parent_id=new_parent_id)
                logger.debug(f"Обновлен parent для категории {new_cat_id}: {new_parent_id}")
            else:
                logger.warning(f"Не удалось обновить parent для ShoeCategory {old_cat.id}: new_cat_id={new_cat_id}, new_parent_id={new_parent_id}")
    
    # 6. Обновляем parent связи для ElectronicsCategory
    logger.info("Обновляем parent связи для ElectronicsCategory...")
    for old_cat in ElectronicsCategory.objects.all():
        if old_cat.parent_id:
            old_parent_id = old_cat.parent_id
            new_cat_id = category_mapping.get(('electronics', old_cat.id))
            new_parent_id = category_mapping.get(('electronics', old_parent_id))
            if new_cat_id and new_parent_id:
                Category.objects.filter(id=new_cat_id).update(parent_id=new_parent_id)
                logger.debug(f"Обновлен parent для категории {new_cat_id}: {new_parent_id}")
            else:
                logger.warning(f"Не удалось обновить parent для ElectronicsCategory {old_cat.id}: new_cat_id={new_cat_id}, new_parent_id={new_parent_id}")
    
    logger.info(f"Миграция завершена. Перенесено категорий: {len(category_mapping)}")
    logger.info(f"Маппинг категорий: {category_mapping}")


def migrate_category_data_reverse(apps, schema_editor):
    """Обратная миграция - не реализована, так как данные будут потеряны."""
    # В случае отката миграции данные из старых моделей уже будут удалены
    logger.warning("Обратная миграция не поддерживается - данные будут потеряны")
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0039_add_category_specific_fields'),
    ]

    operations = [
        migrations.RunPython(migrate_category_data_forward, migrate_category_data_reverse),
    ]
