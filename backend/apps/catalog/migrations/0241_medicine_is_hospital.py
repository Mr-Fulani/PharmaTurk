"""Признак «Больничный препарат» у лекарства (решение владельца 13.11.2026, docs/HOSPITAL_MEDICINES.md).

Только новое поле, данные не трогает: отметка 1 234 + 3 больничных — отдельной записью на проде по «да» владельца.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0240_skateboarding_roller_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='medicineproduct',
            name='is_hospital',
            field=models.BooleanField(db_index=True, default=False, help_text='Цена на сайте не показывается: «цена по запросу», в заявке без суммы, не попадает в фиды и хиты.', verbose_name='Больничный препарат'),
        ),
    ]
