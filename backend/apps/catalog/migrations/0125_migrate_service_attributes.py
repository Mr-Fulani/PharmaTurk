from django.db import migrations

def migrate_data(apps, schema_editor):
    ServiceAttribute = apps.get_model("catalog", "ServiceAttribute")
    ServiceAttributeKey = apps.get_model("catalog", "ServiceAttributeKey")
    ServiceAttributeKeyTranslation = apps.get_model("catalog", "ServiceAttributeKeyTranslation")
    Category = apps.get_model("catalog", "Category")

    attribute_key_choices = [
        ("area_sqm", "Площадь (м²)", "Area (sqm)"),
        ("duration_days", "Срок выполнения", "Duration (days)"),
        ("work_type", "Вид работ", "Work type"),
        ("work_region", "Регион / район", "Region / district"),
        ("weight_kg", "Вес груза (кг)", "Weight (kg)"),
        ("volume_m3", "Объём груза (м³)", "Volume (m3)"),
        ("cargo_type", "Тип груза", "Cargo type"),
        ("distance_km", "Расстояние (км)", "Distance (km)"),
        ("duration_hours", "Длительность (часов)", "Duration (hours)"),
        ("format", "Формат (онлайн/очно)", "Format (online/offline)"),
        ("language", "Язык консультации", "Language"),
        ("specialist", "Специалист", "Specialist"),
        ("rooms_count", "Количество комнат", "Number of rooms"),
        ("frequency", "Периодичность", "Frequency"),
        ("guarantee", "Гарантия", "Guarantee"),
        ("includes", "Что входит", "What's included"),
        ("excludes", "Что не входит", "What's excluded"),
        ("other", "Другое", "Other"),
    ]

    allowed_keys_by_subcategory = {
        "apartment-renovation": ["area_sqm", "duration_days", "work_type", "work_region", "guarantee", "includes", "excludes"],
        "pokraska-pomeshenij":  ["area_sqm", "duration_days", "work_type", "work_region", "guarantee", "includes"],
        "remont":               ["area_sqm", "duration_days", "work_type", "work_region", "guarantee", "includes", "excludes"],
        "cleaning":             ["area_sqm", "rooms_count", "frequency", "includes", "guarantee"],
        "cargo-transport":      ["weight_kg", "volume_m3", "cargo_type", "distance_km"],
        "cargo":                ["weight_kg", "volume_m3", "cargo_type", "distance_km"],
        "gruzoperevozki":       ["weight_kg", "volume_m3", "cargo_type", "distance_km"],
        "consultations":        ["duration_hours", "format", "language", "specialist"],
        "consultacii":          ["duration_hours", "format", "language", "specialist"],
        "diagnostics":          ["duration_hours", "format", "specialist"],
        "diagnostika":          ["duration_hours", "format", "specialist"],
    }

    # 1. Create keys and translations
    for slug, name_ru, name_en in attribute_key_choices:
        key_obj, _ = ServiceAttributeKey.objects.get_or_create(slug=slug)
        ServiceAttributeKeyTranslation.objects.get_or_create(key_obj=key_obj, locale='ru', defaults={'name': name_ru})
        ServiceAttributeKeyTranslation.objects.get_or_create(key_obj=key_obj, locale='en', defaults={'name': name_en})

    # 2. Link categories
    for cat_slug, keys in allowed_keys_by_subcategory.items():
        try:
            category = Category.objects.get(slug=cat_slug)
            for k_slug in keys:
                try:
                    key_obj = ServiceAttributeKey.objects.get(slug=k_slug)
                    key_obj.categories.add(category)
                except ServiceAttributeKey.DoesNotExist:
                    pass
        except Category.DoesNotExist:
            pass

    # 3. Update existing ServiceAttribute
    for attr in ServiceAttribute.objects.filter(attribute_key__isnull=True):
        try:
            key_obj = ServiceAttributeKey.objects.get(slug=attr.key)
            attr.attribute_key = key_obj
            attr.save()
        except ServiceAttributeKey.DoesNotExist:
            pass

class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0124_alter_serviceattribute_options_and_more"),
    ]

    operations = [
        migrations.RunPython(migrate_data),
    ]
