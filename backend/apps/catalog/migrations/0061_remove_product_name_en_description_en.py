# Generated manually on 2025-12-16

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0060_delete_footersettings"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="product",
            name="name_en",
        ),
        migrations.RemoveField(
            model_name="product",
            name="description_en",
        ),
    ]

