"""Конфигурация периодических задач Celery для системы ценообразования."""

from celery.schedules import crontab
from celery import Celery
import os

# Указываем настройки Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Периодические задачи
app.conf.beat_schedule = {
    # Обновление курсов валют каждые 4 часа
    'currency.update_rates': {
        'task': 'currency.update_rates',
        'schedule': crontab(minute=0, hour='*/4'),  # Каждые 4 часа в 00 минут
        'options': {
            'queue': 'currency',
            'priority': 9,
        }
    },
    
    # Обновление цен товаров каждый день в 2:00
    'currency.update_product_prices': {
        'task': 'currency.update_product_prices',
        'schedule': crontab(minute=0, hour=2),  # Ежедневно в 2:00
        'kwargs': {
            'batch_size': 200,
        },
        'options': {
            'queue': 'currency',
            'priority': 8,
        }
    },
    
    # Очистка старых логов раз в неделю в воскресенье в 3:00
    'currency.cleanup_old_logs': {
        'task': 'currency.cleanup_old_logs',
        'schedule': crontab(minute=0, hour=3, day_of_week=0),  # Воскресенье в 3:00
        'kwargs': {
            'days_to_keep': 30,
        },
        'options': {
            'queue': 'currency',
            'priority': 5,
        }
    },
    
    # Проверка здоровья системы каждый день в 6:00
    'currency.health_check': {
        'task': 'currency.health_check',
        'schedule': crontab(minute=0, hour=6),  # Ежедневно в 6:00
        'options': {
            'queue': 'currency',
            'priority': 7,
        }
    },
    
    # Резервное копирование курсов валют каждый день в 1:00
    'currency.backup_rates': {
        'task': 'currency.backup_rates',
        'schedule': crontab(minute=0, hour=1),  # Ежедневно в 1:00
        'options': {
            'queue': 'currency',
            'priority': 6,
        }
    },
    
    # Обновление цен для медицинских товаров отдельно (если нужно)
    'currency.update_medicine_prices': {
        'task': 'currency.update_product_prices',
        'schedule': crontab(minute=30, hour=3),  # Ежедневно в 3:30
        'kwargs': {
            'product_type': 'medicines',
            'batch_size': 100,
        },
        'options': {
            'queue': 'currency',
            'priority': 8,
        }
    },
    
    # Обновление цен для книг отдельно (если нужно)
    'currency.update_book_prices': {
        'task': 'currency.update_product_prices',
        'schedule': crontab(minute=0, hour=4),  # Ежедневно в 4:00
        'kwargs': {
            'product_type': 'books',
            'batch_size': 50,
        },
        'options': {
            'queue': 'currency',
            'priority': 8,
        }
    },
}

# Настройки очередей
app.conf.task_routes = {
    'currency.update_rates': {'queue': 'currency'},
    'currency.update_product_prices': {'queue': 'currency'},
    'currency.cleanup_old_logs': {'queue': 'currency'},
    'currency.health_check': {'queue': 'currency'},
    'currency.backup_rates': {'queue': 'currency'},
}

# Настройки приоритетов
app.conf.task_default_priority = 5
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True

# Таймауты
app.conf.task_soft_time_limit = 300  # 5 минут
app.conf.task_time_limit = 600      # 10 минут
