from django.db import migrations


def migrate_profile_to_user(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserProfile = apps.get_model("users", "UserProfile")

    for profile in UserProfile.objects.select_related("user").all():
        user = profile.user
        user.first_name = profile.first_name or user.first_name
        user.last_name = profile.last_name or user.last_name
        user.middle_name = profile.middle_name
        user.country = profile.country
        user.city = profile.city
        user.postal_code = profile.postal_code
        user.address = profile.address
        if profile.avatar:
            user.avatar = profile.avatar
        user.bio = profile.bio
        user.whatsapp_phone = profile.whatsapp_phone
        user.telegram_username = profile.telegram_username or user.telegram_username
        user.is_public_profile = profile.is_public_profile
        user.show_email = profile.show_email
        user.show_phone = profile.show_phone
        user.save()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_add_profile_fields_to_user"),
    ]

    operations = [
        migrations.RunPython(migrate_profile_to_user, reverse_code=migrations.RunPython.noop),
    ]

