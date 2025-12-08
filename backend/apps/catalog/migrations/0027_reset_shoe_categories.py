from django.db import migrations


def reset_shoe_categories(apps, schema_editor):
    ShoeCategory = apps.get_model("catalog", "ShoeCategory")

    parents = [
        {"name": "Женская обувь", "slug": "women-shoes", "gender": "women", "sort_order": 1},
        {"name": "Мужская обувь", "slug": "men-shoes", "gender": "men", "sort_order": 2},
        {"name": "Унисекс обувь", "slug": "unisex-shoes", "gender": "unisex", "sort_order": 3},
        {"name": "Детская обувь", "slug": "kids-shoes", "gender": "kids", "sort_order": 4},
    ]

    child_types = [
        {"name": "Кроссовки", "slug": "sneakers", "shoe_type": "sneakers", "sort_order": 1},
        {"name": "Ботинки", "slug": "boots", "shoe_type": "boots", "sort_order": 2},
        {"name": "Сандалии", "slug": "sandals", "shoe_type": "sandals", "sort_order": 3},
        {"name": "Туфли", "slug": "dress-shoes", "shoe_type": "dress", "sort_order": 4},
        {"name": "Домашняя обувь", "slug": "home-shoes", "shoe_type": "home", "sort_order": 5},
    ]

    desired_slugs = set()

    # Создаем/обновляем верхний уровень
    parent_map = {}
    for p in parents:
        obj, _ = ShoeCategory.objects.update_or_create(
            slug=p["slug"],
            defaults={
                "name": p["name"],
                "description": "",
                "parent": None,
                "gender": p["gender"],
                "shoe_type": "",
                "external_id": "",
                "external_data": {},
                "is_active": True,
                "sort_order": p["sort_order"],
            },
        )
        parent_map[p["slug"]] = obj
        desired_slugs.add(p["slug"])

    # Создаем/обновляем подкатегории для каждого верхнего уровня
    for parent_slug, parent in parent_map.items():
        gender = parent.gender
        for ct in child_types:
            child_slug = f"{ct['slug']}-{parent_slug}"
            obj, _ = ShoeCategory.objects.update_or_create(
                slug=child_slug,
                defaults={
                    "name": f"{ct['name']} ({parent.name})",
                    "description": "",
                    "parent": parent,
                    "gender": gender,
                    "shoe_type": ct["shoe_type"],
                    "external_id": "",
                    "external_data": {},
                    "is_active": True,
                    "sort_order": ct["sort_order"],
                },
            )
            desired_slugs.add(child_slug)

    # Удаляем старые/ненужные записи, чтобы список был чистым
    ShoeCategory.objects.exclude(slug__in=desired_slugs).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0026_categoryaccessories_categoryfurniture_and_more"),
    ]

    operations = [
        migrations.RunPython(reset_shoe_categories, migrations.RunPython.noop),
    ]

