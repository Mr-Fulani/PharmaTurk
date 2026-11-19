"""
Решение владельца 19.11.2026: лекарства не стоят в «Хитах продаж», для них — справочный блок
главной; подпись об оплате в подвале относится к товарам, кроме лекарств.

1. Блок главной «Часто ищут в справочнике лекарств» — сразу после «Хитов продаж», где бы они
   ни стояли в админке.
2. Текст про оплату в подвале: меняется только дословно прежний текст по умолчанию; свой текст,
   введённый в админке, миграция не трогает.

Без сети и R2.
"""
from django.db import migrations

OLD_PAYMENT_TEXT = "Возможна оплата криптовалютой"
NEW_PAYMENT_TEXT = (
    "Оплата — по согласованию с менеджером, возможна криптовалютой. "
    "Относится к товарам, кроме лекарств: сведения о лекарствах — справочные."
)


def forwards(apps, schema_editor):
    HomeBlock = apps.get_model("settings", "HomeBlock")
    FooterSettings = apps.get_model("settings", "FooterSettings")
    bestsellers = HomeBlock.objects.filter(key="bestsellers").first()
    HomeBlock.objects.get_or_create(
        key="medicine_reference",
        defaults={
            # По умолчанию хиты — 60, «Найдём любой товар» — 70.
            "sort_order": (bestsellers.sort_order if bestsellers else 60) + 1,
            "is_enabled": True,
        },
    )
    FooterSettings.objects.filter(crypto_payment_text=OLD_PAYMENT_TEXT).update(crypto_payment_text=NEW_PAYMENT_TEXT)


def backwards(apps, schema_editor):
    FooterSettings = apps.get_model("settings", "FooterSettings")
    FooterSettings.objects.filter(crypto_payment_text=NEW_PAYMENT_TEXT).update(crypto_payment_text=OLD_PAYMENT_TEXT)


class Migration(migrations.Migration):

    dependencies = [
        ("settings", "0008_medicine_reference_block_footer_text"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
