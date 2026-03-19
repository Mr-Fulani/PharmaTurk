# Generated manually for CategoryIncense proxy model

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0114_accessoryproduct_meta_description_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CategoryIncense",
            fields=[],
            options={
                "verbose_name": "Категория — Благовония",
                "verbose_name_plural": "Категории — Благовония",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("catalog.category",),
        ),
    ]
