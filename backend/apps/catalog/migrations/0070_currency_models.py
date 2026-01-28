# Generated migration for currency models

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0069_product_video_url'),
    ]

    operations = [
        migrations.CreateModel(
            name='CurrencyRate',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('from_currency', models.CharField(choices=[('TRY', 'Turkish Lira'), ('RUB', 'Russian Ruble'), ('KZT', 'Kazakhstan Tenge'), ('USD', 'US Dollar'), ('EUR', 'Euro')], max_length=3)),
                ('to_currency', models.CharField(choices=[('TRY', 'Turkish Lira'), ('RUB', 'Russian Ruble'), ('KZT', 'Kazakhstan Tenge'), ('USD', 'US Dollar'), ('EUR', 'Euro')], max_length=3)),
                ('rate', models.DecimalField(decimal_places=6, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ('source', models.CharField(choices=[('centralbank_rf', 'Central Bank of Russia'), ('nationalbank_kz', 'National Bank of Kazakhstan'), ('centralbank_tr', 'Central Bank of Turkey'), ('openexchangerates', 'OpenExchangeRates API'), ('manual', 'Manual Entry')], max_length=50)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Currency Rate',
                'verbose_name_plural': 'Currency Rates',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='MarginSettings',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('currency_pair', models.CharField(help_text='Format: FROM-TO (e.g., TRY-RUB)', max_length=10)),
                ('margin_percentage', models.DecimalField(decimal_places=2, help_text='Margin percentage (e.g., 15 for 15%)', max_digits=5, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ('is_active', models.BooleanField(default=True)),
                ('description', models.TextField(blank=True, help_text='Description of this margin setting')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Margin Setting',
                'verbose_name_plural': 'Margin Settings',
                'ordering': ['currency_pair'],
            },
        ),
        migrations.CreateModel(
            name='ProductPrice',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('currency', models.CharField(choices=[('TRY', 'Turkish Lira'), ('RUB', 'Russian Ruble'), ('KZT', 'Kazakhstan Tenge'), ('USD', 'US Dollar'), ('EUR', 'Euro')], max_length=3)),
                ('original_price', models.DecimalField(decimal_places=2, help_text='Original price in source currency', max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ('converted_price', models.DecimalField(decimal_places=2, help_text='Price after currency conversion', max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ('price_with_margin', models.DecimalField(decimal_places=2, help_text='Final price with margin applied', max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ('is_base_price', models.BooleanField(default=False, help_text='Is this the base price from the source?')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prices', to='catalog.product')),
            ],
            options={
                'verbose_name': 'Product Price',
                'verbose_name_plural': 'Product Prices',
                'ordering': ['currency'],
            },
        ),
        migrations.CreateModel(
            name='CurrencyUpdateLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('source', models.CharField(max_length=50)),
                ('success', models.BooleanField(default=True)),
                ('rates_updated', models.PositiveIntegerField(default=0)),
                ('error_message', models.TextField(blank=True)),
                ('execution_time_seconds', models.FloatField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Currency Update Log',
                'verbose_name_plural': 'Currency Update Logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='currencyrate',
            unique_together={('from_currency', 'to_currency')},
        ),
        migrations.AlterUniqueTogether(
            name='marginsettings',
            unique_together={('currency_pair',)},
        ),
        migrations.AlterUniqueTogether(
            name='productprice',
            unique_together={('product', 'currency')},
        ),
    ]
