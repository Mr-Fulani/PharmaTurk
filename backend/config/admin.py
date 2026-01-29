"""Кастомная конфигурация админ-панели Django для логической группировки моделей."""

from django.contrib import admin
from django.contrib.admin import AdminSite


class PharmaTurkAdminSite(AdminSite):
    """Кастомная админ-панель с улучшенной организацией."""
    
    site_header = 'PharmaTurk - Панель управления'
    site_title = 'PharmaTurk Admin'
    index_title = 'Добро пожаловать в панель управления'
    
    def get_app_list(self, request, app_label=None):
        """
        Переопределяем порядок и группировку приложений в админке.
        """
        app_list = super().get_app_list(request, app_label)
        
        # Определяем желаемый порядок разделов
        ordering = {
            'Каталог товаров': 1,
            'Цены и валюты': 2,
            'Заказы и корзины': 3,
            'Маркетинг': 4,
            'Пользователи': 5,
            'Парсеры': 6,
            'Отзывы': 7,
            'Контент': 8,
            'Избранное': 9,
            'Аутентификация': 10,
        }
        
        # Переименовываем и группируем приложения
        app_dict = {}
        
        for app in app_list:
            app_label = app.get('app_label', '')
            app_name = app.get('name', '')
            
            # Определяем новое имя группы
            if app_label == 'catalog':
                # Разделяем catalog на несколько логических групп
                for model in app['models']:
                    model_name = model.get('object_name', '')
                    
                    # Цены и валюты
                    if model_name in ['ProductPrice', 'CurrencyRate', 'MarginSettings', 'CurrencyUpdateLog', 'PriceHistory']:
                        group_name = 'Цены и валюты'
                    # Избранное
                    elif model_name == 'Favorite':
                        group_name = 'Избранное'
                    # Остальное - каталог
                    else:
                        group_name = 'Каталог товаров'
                    
                    if group_name not in app_dict:
                        app_dict[group_name] = {
                            'name': group_name,
                            'app_label': group_name.lower().replace(' ', '_'),
                            'models': []
                        }
                    app_dict[group_name]['models'].append(model)
            
            elif app_label == 'orders':
                group_name = 'Заказы и корзины'
                if group_name not in app_dict:
                    app_dict[group_name] = {
                        'name': group_name,
                        'app_label': app_label,
                        'models': []
                    }
                app_dict[group_name]['models'].extend(app['models'])
            
            elif app_label == 'marketing':
                group_name = 'Маркетинг'
                if group_name not in app_dict:
                    app_dict[group_name] = {
                        'name': group_name,
                        'app_label': app_label,
                        'models': []
                    }
                app_dict[group_name]['models'].extend(app['models'])
            
            elif app_label == 'users':
                group_name = 'Пользователи'
                if group_name not in app_dict:
                    app_dict[group_name] = {
                        'name': group_name,
                        'app_label': app_label,
                        'models': []
                    }
                app_dict[group_name]['models'].extend(app['models'])
            
            elif app_label == 'scrapers':
                group_name = 'Парсеры'
                if group_name not in app_dict:
                    app_dict[group_name] = {
                        'name': group_name,
                        'app_label': app_label,
                        'models': []
                    }
                app_dict[group_name]['models'].extend(app['models'])
            
            elif app_label == 'feedback':
                group_name = 'Отзывы'
                if group_name not in app_dict:
                    app_dict[group_name] = {
                        'name': group_name,
                        'app_label': app_label,
                        'models': []
                    }
                app_dict[group_name]['models'].extend(app['models'])
            
            elif app_label in ['pages', 'settings']:
                group_name = 'Контент'
                if group_name not in app_dict:
                    app_dict[group_name] = {
                        'name': group_name,
                        'app_label': 'content',
                        'models': []
                    }
                app_dict[group_name]['models'].extend(app['models'])
            
            elif app_label == 'auth':
                group_name = 'Аутентификация'
                if group_name not in app_dict:
                    app_dict[group_name] = {
                        'name': group_name,
                        'app_label': app_label,
                        'models': []
                    }
                app_dict[group_name]['models'].extend(app['models'])
            
            else:
                # Остальные приложения оставляем как есть
                app_dict[app_name] = app
        
        # Преобразуем обратно в список и сортируем
        result = list(app_dict.values())
        result.sort(key=lambda x: ordering.get(x['name'], 999))
        
        return result


# Создаем экземпляр кастомной админки
admin_site = PharmaTurkAdminSite(name='pharmaturk_admin')
