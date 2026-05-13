from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('feedback', '0007_alter_testimonial_options_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TestimonialSectionSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('show_on_homepage', models.BooleanField(default=False, verbose_name='Показывать блок отзывов на главной')),
            ],
            options={
                'verbose_name': '💬 Настройки блока отзывов',
                'verbose_name_plural': '💬 Отзывы — Настройки блока',
            },
        ),
    ]
