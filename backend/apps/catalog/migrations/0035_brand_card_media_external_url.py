from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0034_category_card_media_external_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='brand',
            name='card_media_external_url',
            field=models.URLField(
                verbose_name=_('Внешний URL медиа'),
                max_length=500,
                blank=True,
                default='',
                help_text=_('Ссылка на медиа (например, CDN или AWS S3). Если заполнено, приоритетнее файла.'),
            ),
        ),
    ]

