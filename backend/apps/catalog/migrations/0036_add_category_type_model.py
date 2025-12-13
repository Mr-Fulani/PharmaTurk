from django.db import migrations, models
import django.db.models.deletion


def create_category_types(apps, schema_editor):
    """Создаём типы категорий из существующих значений."""
    CategoryType = apps.get_model("catalog", "CategoryType")
    
    # Список существующих типов категорий
    types = [
        ("medicines", "Медицина"),
        ("supplements", "БАДы"),
        ("medical-equipment", "Медтехника"),
        ("clothing", "Одежда"),
        ("underwear", "Нижнее бельё"),
        ("headwear", "Головные уборы"),
        ("shoes", "Обувь"),
        ("electronics", "Электроника"),
        ("furniture", "Мебель"),
        ("tableware", "Посуда"),
        ("accessories", "Аксессуары"),
        ("jewelry", "Украшения"),
    ]
    
    sort_order = 0
    for slug, name in types:
        CategoryType.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "is_active": True,
                "sort_order": sort_order,
            }
        )
        sort_order += 1


def migrate_category_data(apps, schema_editor):
    """Заполняем новое поле category_type_new на основе старого category_type."""
    Category = apps.get_model("catalog", "Category")
    CategoryType = apps.get_model("catalog", "CategoryType")
    
    # Маппинг старых значений в новые slug
    type_mapping = {
        "medicines": "medicines",
        "supplements": "supplements",
        "medical_equipment": "medical-equipment",
        "clothing": "clothing",
        "underwear": "underwear",
        "headwear": "headwear",
        "shoes": "shoes",
        "electronics": "electronics",
        "furniture": "furniture",
        "tableware": "tableware",
        "accessories": "accessories",
        "jewelry": "jewelry",
    }
    
    for category in Category.objects.all():
        old_type = getattr(category, 'category_type', None)
        if old_type:
            new_slug = type_mapping.get(old_type, "medicines")
            try:
                category_type = CategoryType.objects.get(slug=new_slug)
                category.category_type_new = category_type
                category.save(update_fields=['category_type_new'])
            except CategoryType.DoesNotExist:
                # Если типа нет, используем medicines
                category_type = CategoryType.objects.get(slug="medicines")
                category.category_type_new = category_type
                category.save(update_fields=['category_type_new'])


def reverse_migrate(apps, schema_editor):
    """Обратная миграция - не требуется, так как мы не можем восстановить CharField."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0035_brand_card_media_external_url'),
    ]

    operations = [
        # 1. Создаём модель CategoryType
        migrations.CreateModel(
            name='CategoryType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Название')),
                ('slug', models.SlugField(max_length=100, unique=True, verbose_name='Slug')),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активен')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Порядок сортировки')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Дата обновления')),
            ],
            options={
                'verbose_name': 'Тип категории',
                'verbose_name_plural': 'Типы категорий',
                'ordering': ['sort_order', 'name'],
            },
        ),
        # 2. Заполняем CategoryType данными
        migrations.RunPython(create_category_types, migrations.RunPython.noop),
        # 3. Добавляем временное поле для хранения ForeignKey (nullable)
        migrations.AddField(
            model_name='category',
            name='category_type_new',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='categories_new',
                to='catalog.categorytype',
                verbose_name='Тип категории'
            ),
        ),
        # 4. Мигрируем данные из старого поля в новое
        migrations.RunPython(migrate_category_data, reverse_migrate),
        # 5. Удаляем старое поле
        migrations.RemoveField(
            model_name='category',
            name='category_type',
        ),
        # 6. Переименовываем новое поле в старое имя
        migrations.RenameField(
            model_name='category',
            old_name='category_type_new',
            new_name='category_type',
        ),
        # 7. Делаем поле обязательным (после того как все данные заполнены)
        migrations.AlterField(
            model_name='category',
            name='category_type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='categories',
                to='catalog.categorytype',
                verbose_name='Тип категории',
                db_index=True,
                help_text='Выберите тип категории. Если нужного типа нет, создайте его в разделе "Типы категорий".'
            ),
        ),
    ]
