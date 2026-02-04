"""Management команда для запуска Instagram парсера."""

import os
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

    def _normalize_product_type(self, category: str) -> str:
        value = (category or "").strip().lower()
        replacements = {
            "medical-equipment": "medical_equipment",
            "medical equipment": "medical_equipment",
        }
        return replacements.get(value, value or "books")

    def _resolve_category(self, category: str, product_type: str | None = None):
        from apps.catalog.models import Category, CategoryType

        value = (category or "").strip()
        if not value:
            return None

        cat = Category.objects.filter(slug=value).first()
        if cat:
            return cat

        category_type = CategoryType.objects.filter(slug=value).first()
        if category_type:
            cat = (
                Category.objects.filter(category_type=category_type, parent__isnull=True)
                .order_by("sort_order", "name")
                .first()
            )
            if cat:
                return cat
            return Category.objects.filter(category_type=category_type).order_by("sort_order", "name").first()

        cat = Category.objects.filter(name__iexact=value).first()
        if cat:
            return cat

        presets = {
            "clothing": ("clothing", "Одежда"),
            "shoes": ("shoes", "Обувь"),
            "electronics": ("electronics", "Электроника"),
            "furniture": ("furniture", "Мебель"),
            "tableware": ("tableware", "Посуда"),
            "accessories": ("accessories", "Аксессуары"),
            "jewelry": ("jewelry", "Украшения"),
            "underwear": ("underwear", "Нижнее бельё"),
            "headwear": ("headwear", "Головные уборы"),
            "books": ("books", "Книги"),
            "supplements": ("supplements", "БАДы"),
            "medical_equipment": ("medical-equipment", "Медтехника"),
            "medicines": ("medicines", "Медицина"),
        }
        preset = presets.get(product_type or "")
        if not preset:
            return None
        slug, name = preset
        cat, _ = Category.objects.get_or_create(
            slug=slug,
            defaults={'name': name, 'description': name, 'is_active': True}
        )
        return cat

    def _make_unique_product_slug(
        self,
        base_slug: str,
        fallback: str,
        category_slug: str | None = None,
        product_model=None,
    ):
        from apps.catalog.models import Product
        from django.utils.text import slugify
        import uuid
        model = product_model or Product

        category_part = (slugify(category_slug) if category_slug else "").strip("-")
        raw = "-".join(part for part in [category_part, base_slug or fallback] if part)
        base = (slugify(raw)[:200] if raw else "").strip("-")
        if not base:
            base = f"product-{uuid.uuid4().hex[:12]}"
        slug = base
        i = 2
        while model.objects.filter(slug=slug).exists():
            suffix = f"-{i}"
            slug = f"{base[:200 - len(suffix)]}{suffix}"
            i += 1
        return slug

    def _get_instagram_headers(self):
        """Заголовки для запросов к Instagram CDN."""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.instagram.com/",
        }

    def _download_media(self, url: str, product_id: str, index: int = 0) -> str:
        """Скачивает медиа (фото/видео/гиф) и сохраняет в R2/локальное хранилище.

        Использует универсальную функцию для парсеров: автоматически определяет тип
        медиа, оптимизирует фото, сохраняет в products/parsed/instagram/{images,videos,gifs}/.

        Returns:
            URL сохраненного файла или пустая строка при ошибке.
        """
        from apps.catalog.utils.parser_media_handler import download_and_optimize_parsed_media

        result = download_and_optimize_parsed_media(
            url=url,
            parser_name="instagram",
            product_id=product_id,
            index=index,
            headers=self._get_instagram_headers(),
        )
        if not result:
            self.stdout.write(
                self.style.WARNING(f"Не удалось скачать медиа: {url[:80]}...")
            )
        return result

    def _save_products(self, products, category: str):
        """Сохраняет спарсенные товары в базу данных."""
        from apps.catalog.models import (
            Product,
            ProductImage,
            ClothingProduct,
            ClothingProductImage,
            ShoeProduct,
            ShoeProductImage,
            ElectronicsProduct,
            ElectronicsProductImage,
            FurnitureProduct,
        )
        from django.utils import timezone
        from transliterate import translit

        normalized_product_type = self._normalize_product_type(category)
        cat = self._resolve_category(category, normalized_product_type)
        if not cat:
            self.stdout.write(
                self.style.WARNING(f'Категория {category} не найдена, товары будут без категории')
            )

        created_count = 0
        updated_count = 0
        skipped_count = 0

        product_model_map = {
            "clothing": ClothingProduct,
            "shoes": ShoeProduct,
            "electronics": ElectronicsProduct,
            "furniture": FurnitureProduct,
        }
        image_model_map = {
            "clothing": ClothingProductImage,
            "shoes": ShoeProductImage,
            "electronics": ElectronicsProductImage,
        }
        product_model = product_model_map.get(normalized_product_type, Product)
        if product_model is Product:
            image_model = ProductImage
        else:
            image_model = image_model_map.get(normalized_product_type)

        for product_data in products:
            try:
                # Проверяем, существует ли товар с таким external_id
                # Генерируем slug только из названия для SEO
                # Транслитерируем кириллицу для slug
                try:
                    transliterated_name = translit(product_data.name, 'ru', reversed=True)
                    base_slug = transliterated_name
                except:
                    base_slug = product_data.name
                unique_slug = self._make_unique_product_slug(
                    base_slug,
                    product_data.external_id,
                    cat.slug if cat else None,
                    product_model=product_model,
                )
                
                from apps.catalog.utils.storage_paths import detect_media_type

                main_image_path = ""
                main_video_url = ""
                if product_data.images:
                    main_media_url = self._download_media(
                        product_data.images[0],
                        product_data.external_id,
                        0,
                    )
                    if main_media_url:
                        main_media_type = detect_media_type(product_data.images[0] or main_media_url)
                        if product_model is Product and main_media_type == "video":
                            main_video_url = main_media_url
                        else:
                            main_image_path = main_media_url

                video_url = product_data.attributes.get('video_url', '') if product_data.attributes.get('is_video') else ''
                if main_video_url:
                    video_url = main_video_url

                defaults = {
                    'name': product_data.name,
                    'slug': unique_slug,
                    'description': product_data.description,
                    'category': cat,
                    'external_url': product_data.url,
                    'external_data': product_data.attributes,
                    'is_available': False,
                    'main_image': main_image_path,
                }
                if product_model is Product:
                    defaults.update(
                        {
                            'product_type': normalized_product_type,
                            'video_url': video_url,
                            'last_synced_at': timezone.now(),
                        }
                    )

                product, created = product_model.objects.get_or_create(
                    external_id=product_data.external_id,
                    defaults=defaults,
                )

                if not created:
                    for field, value in defaults.items():
                        if field == "slug":
                            continue
                        setattr(product, field, value)
                    if not product.slug:
                        product.slug = unique_slug
                    product.save()

                # Сохраняем дополнительные изображения (всегда, не только при создании)
                if image_model and product_data.images and len(product_data.images) > 1:
                    # Удаляем старые изображения при обновлении
                    if not created:
                        product.images.all().delete()
                    
                    # Скачиваем и сохраняем изображения со второго
                    # Сохраняем максимум 5 дополнительных изображений
                    for idx, image_url in enumerate(product_data.images[1:6], start=1):
                        media_url = self._download_media(
                            image_url, product_data.external_id, idx
                        )
                        if media_url:
                            media_type = detect_media_type(image_url or media_url)
                            if image_model is ProductImage and media_type == "video":
                                image_model.objects.create(
                                    product=product,
                                    image_url="",
                                    video_url=media_url,
                                    sort_order=idx - 1,
                                    is_main=False,
                                )
                            else:
                                image_model.objects.create(
                                    product=product,
                                    image_url=media_url,
                                    sort_order=idx - 1,
                                    is_main=False,
                                )

                if created:
                    created_count += 1
                    self.stdout.write(f'✓ Создан: {product.name}')
                else:
                    updated_count += 1
                    self.stdout.write(f'↻ Обновлен: {product.name}')

            except Exception as e:
                skipped_count += 1
                # Выводим полную ошибку для отладки
                import traceback
                error_details = traceback.format_exc()
                self.stdout.write(
                    self.style.WARNING(f'✗ Пропущен {product_data.name}: {str(e)}')
                )
                # Выводим детали только для первой ошибки
                if skipped_count == 1:
                    self.stdout.write(self.style.ERROR(f'Детали ошибки:\n{error_details}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'\nИтого: создано {created_count}, обновлено {updated_count}, пропущено {skipped_count}'
            )
        )
