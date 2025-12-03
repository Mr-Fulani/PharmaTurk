from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0006_migrate_userprofile_to_user"),
    ]

    operations = [
        migrations.DeleteModel(name="UserProfile"),
    ]

