from django.db import migrations, models


def make_existing_profiles_private(apps, schema_editor):
    """Reset legacy opt-out defaults; users can explicitly opt in again."""
    User = apps.get_model("users", "User")
    User.objects.update(
        is_public_profile=False,
        show_email=False,
        show_phone=False,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0013_user_telegram_sync_token"),
    ]

    operations = [
        migrations.RunPython(make_existing_profiles_private, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="is_public_profile",
            field=models.BooleanField(default=False, verbose_name="публичный профиль"),
        ),
        migrations.AlterField(
            model_name="user",
            name="show_email",
            field=models.BooleanField(default=False, verbose_name="показывать email"),
        ),
        migrations.AlterField(
            model_name="user",
            name="show_phone",
            field=models.BooleanField(default=False, verbose_name="показывать телефон"),
        ),
    ]
