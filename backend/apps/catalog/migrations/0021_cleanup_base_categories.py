from django.db import migrations


def cleanup_categories(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Product = apps.get_model("catalog", "Product")

    obsolete_slugs = [
        "clothing-general",
        "tableware-serveware",
        "furniture-living",
    ]

    cats = Category.objects.filter(slug__in=obsolete_slugs)
    cat_ids = list(cats.values_list("id", flat=True))
    if cat_ids:
        Product.objects.filter(category_id__in=cat_ids).update(category=None)
        cats.delete()


def reverse_cleanup_categories(apps, schema_editor):
    # Ничего не восстанавливаем
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0020_update_product_types_and_accessories"),
    ]

    operations = [
        migrations.RunPython(cleanup_categories, reverse_cleanup_categories),
    ]

