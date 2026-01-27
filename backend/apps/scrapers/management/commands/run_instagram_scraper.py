"""Management команда для запуска Instagram парсера."""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.scrapers.parsers.instagram import InstagramParser
from apps.scrapers.models import ScraperConfig, ScrapingSession
from apps.scrapers.services import ScraperIntegrationService


class Command(BaseCommand):
    help = 'Запускает парсер Instagram для сбора постов с медиа и описаниями'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Instagram username профиля для парсинга',
        )
        parser.add_argument(
            '--hashtag',
            type=str,
            help='Хештег для парсинга (без #)',
        )
        parser.add_argument(
            '--post-url',
            type=str,
            help='URL конкретного поста для парсинга',
        )
        parser.add_argument(
            '--max-posts',
            type=int,
            default=50,
            help='Максимальное количество постов для парсинга (по умолчанию: 50)',
        )
        parser.add_argument(
            '--category',
            type=str,
            default='books',
            help='Категория товаров (по умолчанию: books)',
        )
        parser.add_argument(
            '--login',
            type=str,
            help='Instagram логин для аутентификации (опционально)',
        )
        parser.add_argument(
            '--password',
            type=str,
            help='Instagram пароль для аутентификации (опционально)',
        )
        parser.add_argument(
            '--config-id',
            type=int,
            help='ID конфигурации парсера из базы данных',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только парсинг без сохранения в базу данных',
        )

    def handle(self, *args, **options):
        username = options.get('username')
        hashtag = options.get('hashtag')
        post_url = options.get('post_url')
        max_posts = options.get('max_posts')
        category = options.get('category')
        login = options.get('login')
        password = options.get('password')
        config_id = options.get('config_id')
        dry_run = options.get('dry_run')

        # Проверяем, что указан хотя бы один источник
        if not any([username, hashtag, post_url, config_id]):
            raise CommandError(
                'Необходимо указать --username, --hashtag, --post-url или --config-id'
            )

        self.stdout.write(self.style.SUCCESS('بسم الله الرحمن الرحيم'))
        self.stdout.write(self.style.SUCCESS('Запуск Instagram парсера...'))

        try:
            # Если указан config_id, используем конфигурацию из БД
            if config_id:
                self._run_with_config(config_id, max_posts)
                return

            # Создаем экземпляр парсера
            parser = InstagramParser(
                username=login,
                password=password,
            )

            products = []

            # Парсим в зависимости от источника
            if post_url:
                self.stdout.write(f'Парсинг поста: {post_url}')
                product = parser.parse_product_detail(post_url)
                if product:
                    products.append(product)
            elif username:
                self.stdout.write(f'Парсинг профиля: @{username}')
                url = f'https://www.instagram.com/{username}/'
                products = parser.parse_product_list(url, max_posts)
            elif hashtag:
                self.stdout.write(f'Парсинг хештега: #{hashtag}')
                url = f'https://www.instagram.com/explore/tags/{hashtag}/'
                products = parser.parse_product_list(url, max_posts)

            # Выводим результаты
            self.stdout.write(
                self.style.SUCCESS(f'\nСпарсено товаров: {len(products)}')
            )

            if dry_run:
                self.stdout.write(
                    self.style.WARNING('\nРежим dry-run: товары не сохранены в БД')
                )
                for idx, product in enumerate(products, 1):
                    self.stdout.write(f'\n{idx}. {product.name}')
                    self.stdout.write(f'   URL: {product.url}')
                    self.stdout.write(f'   Изображений: {len(product.images)}')
                    self.stdout.write(f'   Описание: {product.description[:100]}...')
            else:
                # Сохраняем в базу данных
                self._save_products(products, category)

            self.stdout.write(self.style.SUCCESS('\n✓ Парсинг завершен успешно'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n✗ Ошибка: {str(e)}'))
            raise CommandError(f'Ошибка при парсинге: {str(e)}')

    def _run_with_config(self, config_id: int, max_posts: int):
        """Запускает парсер с использованием конфигурации из БД."""
        try:
            config = ScraperConfig.objects.get(id=config_id, parser_class='instagram')
        except ScraperConfig.DoesNotExist:
            raise CommandError(f'Конфигурация с ID {config_id} не найдена')

        if not config.is_enabled:
            raise CommandError(f'Конфигурация {config.name} отключена')

        self.stdout.write(f'Использование конфигурации: {config.name}')

        # Используем сервис интеграции
        service = ScraperIntegrationService()
        session = service.run_scraper(
            scraper_config=config,
            max_pages=max_posts,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nСессия #{session.id}: {session.get_status_display()}'
            )
        )
        self.stdout.write(f'Найдено товаров: {session.products_found}')
        self.stdout.write(f'Создано: {session.products_created}')
        self.stdout.write(f'Обновлено: {session.products_updated}')
        self.stdout.write(f'Пропущено: {session.products_skipped}')

    def _save_products(self, products, category: str):
        """Сохраняет спарсенные товары в базу данных."""
        from apps.catalog.models import Product, ProductImage, Category
        from django.utils.text import slugify

        # Получаем категорию
        try:
            cat = Category.objects.get(slug=category)
        except Category.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(f'Категория {category} не найдена, товары будут без категории')
            )
            cat = None

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for product_data in products:
            try:
                # Проверяем, существует ли товар с таким external_id
                product, created = Product.objects.update_or_create(
                    external_id=product_data.external_id,
                    defaults={
                        'name': product_data.name,
                        'slug': slugify(product_data.name)[:200],
                        'description': product_data.description,
                        'product_type': category,
                        'category': cat,
                        'external_url': product_data.url,
                        'external_data': product_data.attributes,
                        'is_available': False,  # Недоступен пока не установлена цена
                        'main_image': product_data.images[0] if product_data.images else '',
                        'last_synced_at': timezone.now(),
                    }
                )

                # Сохраняем изображения
                if created and product_data.images:
                    for idx, image_url in enumerate(product_data.images):
                        ProductImage.objects.create(
                            product=product,
                            image_url=image_url,
                            sort_order=idx,
                            is_main=(idx == 0),
                        )

                if created:
                    created_count += 1
                    self.stdout.write(f'✓ Создан: {product.name}')
                else:
                    updated_count += 1
                    self.stdout.write(f'↻ Обновлен: {product.name}')

            except Exception as e:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(f'✗ Пропущен {product_data.name}: {str(e)}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nИтого: создано {created_count}, обновлено {updated_count}, пропущено {skipped_count}'
            )
        )
