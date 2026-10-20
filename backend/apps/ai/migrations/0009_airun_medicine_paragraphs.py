from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai', '0008_airun'),
    ]

    operations = [
        migrations.AlterField(
            model_name='airun',
            name='kind',
            field=models.CharField(choices=[('products', 'Обработка товаров'), ('retry_titles', 'Перегенерация отклонённых названий БАДов'), ('close_moderation', 'Закрытие решённых записей модерации'), ('medicine_paragraphs', 'Перевод абзацев инструкций (Batch API)')], default='products', max_length=20, verbose_name='Что делаем'),
        ),
    ]
