"""Management-команда для запуска Instagram-парсера.

Использование:
    # Парсинг профиля (через ScraperIntegrationService):
    python manage.py run_instagram_scraper --username ummaland_books --category books

    # Парсинг хештега:
    python manage.py run_instagram_scraper --hashtag islambooks --max-posts 30

    # Парсинг одного поста:
    python manage.py run_instagram_scraper --post-url https://www.instagram.com/p/ABC123/

    # Тестовый запуск без сохранения в БД:
    python manage.py run_instagram_scraper --username ummaland_books --dry-run

    # Запуск по конфигурации из БД (ScraperConfig.id):
    python manage.py run_instagram_scraper --config-id 5

Все пути сохранения (кроме --dry-run) проходят через ScraperIntegrationService —
единый сервис создания/обновления товаров, скачивания медиа в R2 и логирования.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Запускает Instagram-парсер для сбора постов с медиа и описаниями"

    def add_arguments(self, parser):
        # --- Источник данных ---
        parser.add_argument(
            "--username",
            type=str,
            help="Instagram username профиля для парсинга (без @)",
        )
        parser.add_argument(
            "--hashtag",
            type=str,
            help="Хештег для парсинга (без символа #)",
        )
        parser.add_argument(
            "--post-url",
            type=str,
            help="URL конкретного поста для парсинга одного поста",
        )
        # --- Параметры парсинга ---
        parser.add_argument(
            "--max-posts",
            type=int,
            default=50,
            help="Максимальное количество постов (по умолчанию: 50)",
        )
        parser.add_argument(
            "--category",
            type=str,
            default="books",
            help=(
                "Slug категории товаров (по умолчанию: books). "
                "Используется для поиска/создания Category в каталоге."
            ),
        )
        # --- Авторизация ---
        parser.add_argument(
            "--login",
            type=str,
            help="Instagram логин бот-аккаунта для авторизации (опционально)",
        )
        parser.add_argument(
            "--password",
            type=str,
            help="Instagram пароль бот-аккаунта (опционально)",
        )
        # --- Режим через конфигурацию из БД ---
        parser.add_argument(
            "--config-id",
            type=int,
            help="ID конфигурации парсера (ScraperConfig) из базы данных",
        )
        # --- Служебные опции ---
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только парсинг без сохранения в БД. Выводит список спарсенных постов.",
        )

    def handle(self, *args, **options):
        username = options.get("username")
        hashtag = options.get("hashtag")
        post_url = options.get("post_url")
        max_posts = options.get("max_posts")
        category_slug = options.get("category", "books")
        login = options.get("login")
        password = options.get("password")
        config_id = options.get("config_id")
        dry_run = options.get("dry_run")

        # Проверяем что указан хотя бы один источник данных
        if not any([username, hashtag, post_url, config_id]):
            raise CommandError(
                "Необходимо указать --username, --hashtag, --post-url или --config-id"
            )

        self.stdout.write(self.style.SUCCESS("بسم الله الرحمن الرحيم"))
        self.stdout.write(self.style.SUCCESS("Запуск Instagram-парсера..."))

        # --- Режим --dry-run: парсим без сохранения в БД ---
        if dry_run:
            self._handle_dry_run(username, hashtag, post_url, max_posts, login, password)
            return

        # --- Режим --config-id: используем конфигурацию из БД ---
        if config_id:
            self._run_with_config(config_id, max_posts, category_slug)
            return

        # --- Основной режим: через ScraperIntegrationService ---
        self._run_via_service(
            username=username,
            hashtag=hashtag,
            post_url=post_url,
            max_posts=max_posts,
            category_slug=category_slug,
            login=login,
            password=password,
        )

    # -----------------------------------------------------------------------
    # Основной режим: через ScraperIntegrationService
    # -----------------------------------------------------------------------

    def _run_via_service(
        self,
        username=None,
        hashtag=None,
        post_url=None,
        max_posts=50,
        category_slug="books",
        login=None,
        password=None,
    ):
        """Запускает парсинг через ScraperIntegrationService.

        Формирует start_url из переданных параметров, находит или создаёт
        ScraperConfig для Instagram, резолвит target_category из slug,
        затем вызывает единый сервис интеграции — как для сайтовых парсеров.
        """
        from apps.scrapers.services import ScraperIntegrationService
        from apps.scrapers.models import ScraperConfig

        # --- Формируем start_url ---
        if post_url:
            start_url = post_url
            self.stdout.write(f"Источник: пост {start_url}")
        elif username:
            start_url = f"https://www.instagram.com/{username}/"
            self.stdout.write(f"Источник: профиль @{username}")
        elif hashtag:
            start_url = f"https://www.instagram.com/explore/tags/{hashtag}/"
            self.stdout.write(f"Источник: хештег #{hashtag}")
        else:
            raise CommandError("Не задан источник (--username, --hashtag или --post-url)")

        # --- Находим или авто-создаём ScraperConfig для Instagram ---
        # ScraperConfig нужен ScraperIntegrationService для создания ScrapingSession.
        config = ScraperConfig.objects.filter(
            parser_class="instagram", is_enabled=True
        ).first()

        if not config:
            # Создаём временную конфигурацию если её нет в БД.
            # default_category — обязательное поле ScraperConfig (NOT NULL).
            # Используем target_category из задачи, иначе первую попавшуюся.
            self.stdout.write(
                self.style.WARNING(
                    "ScraperConfig для Instagram не найден — создаём временный."
                )
            )
            default_cat = target_category
            if default_cat is None:
                from apps.catalog.models import Category
                default_cat = Category.objects.first()
            if default_cat is None:
                raise CommandError(
                    "Невозможно создать ScraperConfig: в каталоге нет категорий. "
                    "Создайте ScraperConfig вручную в /admin/scrapers/scraperconfig/add/"
                )
            config = ScraperConfig.objects.create(
                name="instagram",
                parser_class="instagram",
                base_url="https://www.instagram.com",
                is_enabled=True,
                delay_min=5.0,
                delay_max=15.0,
                max_pages_per_run=max_posts,
                max_products_per_run=max_posts,
                max_images_per_product=10,
                default_category=default_cat,
            )

        # Если переданы учётные данные — временно сохраняем в конфиге
        if login and password:
            config.scraper_username = login
            config.scraper_password = password

        # --- Резолвим target_category из slug ---
        target_category = self._resolve_category(category_slug)
        if target_category:
            self.stdout.write(f"Категория: {target_category.name}")
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Категория '{category_slug}' не найдена в каталоге. "
                    "Товары будут без категории."
                )
            )

        # --- Запускаем через ScraperIntegrationService ---
        # Единый путь: создание товаров, скачивание медиа в R2, логирование.
        service = ScraperIntegrationService()
        try:
            session = service.run_scraper(
                scraper_config=config,
                start_url=start_url,
                max_pages=max_posts,
                max_products=max_posts,
                target_category=target_category,
            )
        except Exception as e:
            raise CommandError(f"Ошибка при выполнении парсинга: {e}")

        # --- Выводим итоговую статистику ---
        self._print_session_stats(session)

    # -----------------------------------------------------------------------
    # Режим --config-id
    # -----------------------------------------------------------------------

    def _run_with_config(self, config_id: int, max_posts: int, category_slug: str):
        """Запускает парсер используя ScraperConfig из БД по ID."""
        from apps.scrapers.models import ScraperConfig
        from apps.scrapers.services import ScraperIntegrationService

        try:
            config = ScraperConfig.objects.get(id=config_id, parser_class="instagram")
        except ScraperConfig.DoesNotExist:
            raise CommandError(
                f"ScraperConfig с ID={config_id} и parser_class='instagram' не найден"
            )

        if not config.is_enabled:
            raise CommandError(f"Конфигурация '{config.name}' отключена (is_enabled=False)")

        self.stdout.write(f"Конфигурация: {config.name} (ID={config.id})")
        self.stdout.write(f"Base URL: {config.base_url}")

        target_category = self._resolve_category(category_slug)

        service = ScraperIntegrationService()
        try:
            session = service.run_scraper(
                scraper_config=config,
                max_pages=max_posts,
                max_products=max_posts,
                target_category=target_category,
            )
        except Exception as e:
            raise CommandError(f"Ошибка при выполнении парсинга: {e}")

        self._print_session_stats(session)

    # -----------------------------------------------------------------------
    # Режим --dry-run
    # -----------------------------------------------------------------------

    def _handle_dry_run(
        self, username, hashtag, post_url, max_posts, login, password
    ):
        """Парсинг без сохранения в БД.

        Создаёт InstagramParser напрямую, парсит посты и выводит результаты.
        Используется для тестирования и отладки.
        """
        from apps.scrapers.parsers.instagram import InstagramParser

        self.stdout.write(self.style.WARNING("Режим DRY-RUN: товары не сохраняются в БД"))

        parser = InstagramParser(username=login, password=password)
            products = []

        try:
            if post_url:
                self.stdout.write(f"Парсинг поста: {post_url}")
                product = parser.parse_product_detail(post_url)
                if product:
                    products.append(product)
            elif username:
                url = f"https://www.instagram.com/{username}/"
                self.stdout.write(f"Парсинг профиля: @{username}")
                products = parser.parse_product_list(url, max_posts)
            elif hashtag:
                url = f"https://www.instagram.com/explore/tags/{hashtag}/"
                self.stdout.write(f"Парсинг хештега: #{hashtag}")
                products = parser.parse_product_list(url, max_posts)
        except Exception as e:
            raise CommandError(f"Ошибка при парсинге: {e}")

        self.stdout.write(
            self.style.SUCCESS(f"\nСпарсено постов: {len(products)}")
        )

        # Выводим краткую информацию по каждому посту
        for idx, product in enumerate(products, 1):
            self.stdout.write(f"\n{'─' * 60}")
            self.stdout.write(f"  [{idx}] {product.name}")
            self.stdout.write(f"       URL:         {product.url}")
            self.stdout.write(f"       Изображений: {len(product.images)}")
            price_str = f"{product.price} {product.currency}" if product.price else "не указана"
            self.stdout.write(f"       Цена:        {price_str}")

            # Показываем извлечённые атрибуты
            attrs = product.attributes or {}
            if attrs.get("author"):
                self.stdout.write(f"       Автор:       {attrs['author']}")
            if attrs.get("publisher"):
                self.stdout.write(f"       Издательство:{attrs['publisher']}")
            if attrs.get("isbn"):
                self.stdout.write(f"       ISBN:        {attrs['isbn']}")
            if attrs.get("pages"):
                self.stdout.write(f"       Страниц:     {attrs['pages']}")

            desc_preview = (product.description or "")[:100].replace("\n", " ")
            self.stdout.write(f"       Описание:    {desc_preview}...")

        self.stdout.write(self.style.SUCCESS("\n✓ DRY-RUN завершён"))

    # -----------------------------------------------------------------------
    # Вспомогательные методы
    # -----------------------------------------------------------------------

    def _resolve_category(self, category_slug: str):
        """Находит или создаёт объект Category по slug/name.

        Порядок поиска:
        1. Category.slug == category_slug
        2. Category.name (без учёта регистра)
        3. Создать новую Category по preset-словарю
        4. Вернуть None (парсер продолжит без категории)

        Args:
            category_slug: Slug или имя категории.

        Returns:
            Объект Category или None.
        """
        if not category_slug:
            return None

        from apps.catalog.models import Category

        # Поиск по slug
        cat = Category.objects.filter(slug=category_slug).first()
        if cat:
            return cat

        # Поиск по имени (без учёта регистра)
        cat = Category.objects.filter(name__iexact=category_slug).first()
        if cat:
            return cat

        # Известные категории с русскими именами — создаём если нет
        CATEGORY_PRESETS = {
            "books": ("books", "Книги"),
            "clothing": ("clothing", "Одежда"),
            "shoes": ("shoes", "Обувь"),
            "electronics": ("electronics", "Электроника"),
            "furniture": ("furniture", "Мебель"),
            "tableware": ("tableware", "Посуда"),
            "accessories": ("accessories", "Аксессуары"),
            "jewelry": ("jewelry", "Украшения"),
            "underwear": ("underwear", "Нижнее бельё"),
            "headwear": ("headwear", "Головные уборы"),
            "supplements": ("supplements", "БАДы"),
            "medicines": ("medicines", "Медицина"),
            "medical-equipment": ("medical-equipment", "Медтехника"),
        }

        preset = CATEGORY_PRESETS.get(category_slug.lower())
        if preset:
        slug, name = preset
            cat, created = Category.objects.get_or_create(
            slug=slug,
                defaults={"name": name, "description": name, "is_active": True},
        )
            if created:
                self.stdout.write(f"Создана новая категория: {name} (slug={slug})")
        return cat

        return None

    def _print_session_stats(self, session):
        """Выводит статистику выполненной сессии парсинга."""
            self.stdout.write(
            self.style.SUCCESS(f"\n✓ Парсинг завершён (сессия #{session.id})")
        )
        self.stdout.write(f"  Статус:    {session.get_status_display()}")
        self.stdout.write(f"  Найдено:   {session.products_found}")
        self.stdout.write(f"  Создано:   {session.products_created}")
        self.stdout.write(f"  Обновлено: {session.products_updated}")
        self.stdout.write(f"  Пропущено: {session.products_skipped}")

        if session.status == "failed" and session.error_message:
            self.stdout.write(
                self.style.ERROR(f"  Ошибка: {session.error_message}")
        )
