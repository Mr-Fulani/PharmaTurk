from django.db import migrations


def seed_benefits_block(apps, schema_editor):
    HomeBlock = apps.get_model("settings", "HomeBlock")
    # Сразу под главным баннером (10), перед брендами (20) в порядке по умолчанию.
    HomeBlock.objects.get_or_create(key="benefits", defaults={"sort_order": 15, "is_enabled": True})


class Migration(migrations.Migration):

    dependencies = [
        ("settings", "0006_home_block_benefits"),
    ]

    operations = [
        migrations.RunPython(seed_benefits_block, migrations.RunPython.noop),
    ]
