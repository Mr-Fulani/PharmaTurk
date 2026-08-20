from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0008_cart_identity_uniqueness"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="cart",
            constraint=models.UniqueConstraint(
                fields=("user",),
                condition=models.Q(user__isnull=False),
                name="unique_cart_per_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="cart",
            constraint=models.UniqueConstraint(
                fields=("session_key",),
                condition=models.Q(user__isnull=True),
                name="unique_anonymous_cart_session",
            ),
        ),
    ]
