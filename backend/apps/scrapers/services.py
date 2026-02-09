"""Сервисы для интеграции парсеров с каталогом товаров."""

import logging
import re
import hashlib
from urllib.parse import urlparse
from typing import Dict, List, Optional, Any, Tuple
from django.utils import timezone
from django.db import transaction

from .models import ScraperConfig, ScrapingSession, CategoryMapping, BrandMapping, ScrapedProductLog
from .parsers.registry import get_parser
from .base.scraper import ScrapedProduct
from apps.catalog.services import CatalogNormalizer
from apps.catalog.seo_defaults import build_book_seo_defaults
from apps.catalog.models import Product, Category, Brand, Author, ProductAuthor
from apps.catalog.utils.parser_media_handler import download_and_optimize_parsed_media
from apps.catalog.utils.storage_paths import detect_media_type
import datetime


class ScraperIntegrationService:
    """Сервис интеграции парсеров с каталогом."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.catalog_normalizer = CatalogNormalizer()

    def run_scraper(
        self,
        scraper_config: ScraperConfig,
        start_url: Optional[str] = None,
        max_pages: int = None,
        max_products: int = None,
        max_images_per_product: int = None,
    ) -> ScrapingSession:
        """Запускает парсер и создает сессию.

        Args:
            scraper_config: Конфигурация парсера
            start_url: Начальный URL (если не указан, берется из конфигурации)
            max_pages: Максимальное количество страниц
            max_products: Максимальное количество товаров

        Returns:
            Сессия парсинга
        """
        # Создаем сессию
        session = ScrapingSession.objects.create(
            scraper_config=scraper_config,
            start_url=start_url or scraper_config.base_url,
            max_pages=max_pages or scraper_config.max_pages_per_run,
            max_products=max_products or scraper_config.max_products_per_run,
            max_images_per_product=max_images_per_product or scraper_config.max_images_per_product,
            status="running",
            started_at=timezone.now(),
        )

        try:
            # Получаем класс парсера
            parser_class = get_parser(scraper_config.parser_class)
            if not parser_class:
                raise ValueError(f"Парсер {scraper_config.parser_class} не найден")

            # Создаем экземпляр парсера
            with parser_class(
                base_url=scraper_config.base_url,
                timeout=scraper_config.timeout,
                max_retries=scraper_config.max_retries,
                use_proxy=scraper_config.use_proxy,
                username=scraper_config.scraper_username,
                password=scraper_config.scraper_password,
            ) as parser:

                # Устанавливаем задержки после создания
                parser.delay_range = (scraper_config.delay_min, scraper_config.delay_max)

                # Устанавливаем дополнительные настройки
                if scraper_config.user_agent:
                    parser.user_agent = scraper_config.user_agent

                # Запускаем парсинг
                # Передаем лимит товаров в парсер
                if session.max_products:
                    parser.max_products = session.max_products

                scraped_products = self._run_parser_scraping(
                    parser, session, start_url or scraper_config.base_url
                )

                # Обрабатываем результаты
                results = self._process_scraped_products(session, scraped_products)

                # Обновляем сессию
                session.status = "completed"
                session.finished_at = timezone.now()
                session.products_found = results["found"]
                session.products_created = results["created"]
                session.products_updated = results["updated"]
                session.products_skipped = results["skipped"]
                session.save()

                # Обновляем статистику конфигурации
                self._update_scraper_stats(scraper_config, session, success=True)

        except Exception as e:
            self.logger.error(f"Ошибка при запуске парсера {scraper_config.name}: {e}")

            # Обновляем сессию с ошибкой
            session.status = "failed"
            session.finished_at = timezone.now()
            session.error_message = str(e)
            session.save()

            # Обновляем статистику конфигурации
            self._update_scraper_stats(scraper_config, session, success=False)

            raise

        return session

    def _run_parser_scraping(
        self, parser, session: ScrapingSession, start_url: str
    ) -> List[ScrapedProduct]:
        """Выполняет парсинг с помощью парсера."""
        scraped_products = []

        try:
            # Определяем тип парсинга по URL
            if "/category/" in start_url or "/kategori/" in start_url:
                # Парсинг категории
                products = parser.parse_product_list(start_url, max_pages=session.max_pages)
                scraped_products.extend(products)
                session.pages_processed += len(products) // 20 + 1  # Примерная оценка

            elif "/search" in start_url or "/arama" in start_url:
                # Поиск товаров
                query = self._extract_search_query(start_url)
                if query:
                    products = parser.search_products(query, session.max_products)
                    scraped_products.extend(products)
                    session.pages_processed += 1

            elif "/product/" in start_url or "/p/" in start_url:
                # Парсинг отдельного товара
                product = parser.parse_product_detail(start_url)
                if product:
                    scraped_products.append(product)
                session.pages_processed += 1

            else:
                # Парсинг всех категорий
                categories = parser.parse_categories()
                for category in categories[
                    : session.max_pages
                ]:  # Ограничиваем количество категорий
                    try:
                        products = parser.parse_product_list(
                            category["url"], max_pages=max(1, session.max_pages // len(categories))
                        )
                        scraped_products.extend(products)
                        session.pages_processed += 1

                        # Проверяем лимиты
                        if len(scraped_products) >= session.max_products:
                            break

                    except Exception as e:
                        self.logger.warning(f"Ошибка парсинга категории {category['url']}: {e}")
                        session.errors_count += 1

            # Обновляем сессию
            session.save()

        except Exception as e:
            self.logger.error(f"Ошибка при парсинге: {e}")
            session.errors_count += 1
            session.save()
            raise

        return scraped_products

    def _process_scraped_products(
        self, session: ScrapingSession, products: List[ScrapedProduct]
    ) -> Dict[str, int]:
        """Обрабатывает спарсенные товары и сохраняет в каталог."""
        results = {"found": len(products), "created": 0, "updated": 0, "skipped": 0, "errors": 0}

        for scraped_product in products:
            try:
                self._apply_category_mapping(session, scraped_product)
                self._normalize_scraped_media(session, scraped_product)
                # Проверяем дубликаты с API данными
                action, product = self._process_single_product(session, scraped_product)

                # Обновляем счетчики
                if action == "created":
                    results["created"] += 1
                elif action == "updated":
                    results["updated"] += 1
                elif action == "skipped":
                    results["skipped"] += 1

                # Логируем результат
                ScrapedProductLog.objects.create(
                    session=session,
                    product=product,
                    external_id=scraped_product.external_id,
                    external_url=scraped_product.url,
                    product_name=scraped_product.name,
                    action=action,
                    message=f"Товар {action}",
                    scraped_data=scraped_product.to_dict(),
                )

            except Exception as e:
                self.logger.error(f"Ошибка обработки товара {scraped_product.name}: {e}")
                results["errors"] += 1

                # Логируем ошибку
                ScrapedProductLog.objects.create(
                    session=session,
                    external_id=scraped_product.external_id,
                    external_url=scraped_product.url,
                    product_name=scraped_product.name,
                    action="error",
                    message=str(e),
                    scraped_data=scraped_product.to_dict(),
                )

        return results

    def _apply_category_mapping(
        self, session: ScrapingSession, scraped_product: ScrapedProduct
    ) -> None:
        mappings = (
            CategoryMapping.objects.filter(scraper_config=session.scraper_config, is_active=True)
            .select_related("internal_category")
            .order_by("priority", "id")
        )
        if not mappings.exists():
            return

        category_value = (scraped_product.category or "").strip()
        mapping = None

        if category_value:
            normalized = category_value.lower()
            for item in mappings:
                if item.external_category_name.lower() == normalized:
                    mapping = item
                    break
                if item.external_category_id and item.external_category_id == category_value:
                    mapping = item
                    break
                if item.external_category_url and item.external_category_url == category_value:
                    mapping = item
                    break
        elif mappings.count() == 1:
            mapping = mappings.first()

        if not mapping:
            return

        internal_category = mapping.internal_category
        if internal_category:
            scraped_product.category = internal_category.slug or internal_category.name

    def _get_first_image_url(self, media_urls: List[str]) -> Optional[str]:
        for media_url in media_urls or []:
            if self.catalog_normalizer._resolve_media_type(media_url) == "image":
                return media_url
        return media_urls[0] if media_urls else None

    def _normalize_scraped_media(
        self, session: ScrapingSession, scraped_product: ScrapedProduct
    ) -> None:
        media_urls = list(scraped_product.images or [])
        attributes = scraped_product.attributes or {}
        video_url = attributes.get("video_url")
        if isinstance(video_url, str) and video_url:
            media_urls.append(video_url)
        video_urls = attributes.get("video_urls")
        if isinstance(video_urls, list):
            media_urls.extend([url for url in video_urls if isinstance(url, str) and url])
        video_posters = attributes.get("video_posters") or attributes.get("video_poster")
        poster_urls = []
        if isinstance(video_posters, list):
            poster_urls.extend([url for url in video_posters if isinstance(url, str) and url])
        elif isinstance(video_posters, str) and video_posters:
            poster_urls.append(video_posters)

        if poster_urls and (video_url or video_urls):
            media_urls = [url for url in media_urls if url not in set(poster_urls)]

        unique_media_urls = []
        seen_urls = set()
        for url in media_urls:
            if not isinstance(url, str) or not url:
                continue
            if url in seen_urls:
                continue
            unique_media_urls.append(url)
            seen_urls.add(url)
        media_urls = unique_media_urls

        if not media_urls:
            return

        scraper_config = session.scraper_config
        parser_name = scraped_product.source or scraper_config.parser_class
        max_images = session.max_images_per_product or scraper_config.max_images_per_product or 0
        images = media_urls[:max_images] if max_images else media_urls

        headers = dict(scraper_config.headers or {})
        if scraper_config.user_agent:
            headers.setdefault("User-Agent", scraper_config.user_agent)

        product_id = scraped_product.external_id or ""
        if not product_id:
            parsed_url = urlparse(scraped_product.url or "")
            last_segment = parsed_url.path.rstrip("/").split("/")[-1]
            product_id = (
                last_segment
                or hashlib.md5(
                    (scraped_product.url or scraped_product.name or "").encode("utf-8")
                ).hexdigest()[:12]
            )

        normalized_images = []
        for index, url in enumerate(images):
            parsed = urlparse(url or "")
            if "/products/parsed/" in parsed.path:
                normalized_images.append(url)
                continue
            r2_url = download_and_optimize_parsed_media(
                url=url,
                parser_name=parser_name,
                product_id=product_id,
                index=index,
                headers=headers or None,
            )
            if r2_url:
                normalized_images.append(r2_url)

        if normalized_images:
            scraped_product.images = normalized_images

    def _process_single_product(
        self, session: ScrapingSession, scraped_product: ScrapedProduct
    ) -> Tuple[str, Optional[Product]]:
        """Обрабатывает один товар."""
        # Проверяем, есть ли товар с таким external_id из API
        api_product = Product.objects.filter(
            external_id=scraped_product.external_id, external_data__source="api"  # Только из API
        ).first()

        if api_product:
            # Товар уже есть из API - пропускаем или обновляем дополнительные данные
            return self._handle_api_conflict(scraped_product, api_product)

        # Проверяем дубликаты по названию и бренду
        similar_products = Product.objects.filter(
            name__iexact=scraped_product.name, brand__name__iexact=scraped_product.brand
        )[
            :5
        ]  # Ограничиваем поиск

        for similar_product in similar_products:
            similarity = self._calculate_product_similarity(scraped_product, similar_product)
            if similarity > 0.8:  # 80% похожести
                # Обновляем существующий товар
                return self._update_existing_product(
                    session,
                    scraped_product,
                    similar_product,
                )

        # Создаем новый товар
        return self._create_new_product(session, scraped_product)

    def _handle_api_conflict(
        self, scraped_product: ScrapedProduct, api_product: Product
    ) -> Tuple[str, Product]:
        """Обрабатывает конфликт с товаром из API."""
        # API данные имеют приоритет, но можем обновить дополнительную информацию
        updated = False

        # Обновляем изображения, если их нет
        if not api_product.main_image and scraped_product.images:
            main_image_url = self._get_first_image_url(scraped_product.images)
            if main_image_url:
                api_product.main_image = main_image_url
                updated = True

        # Обновляем описание, если его нет
        if not api_product.description and scraped_product.description:
            api_product.description = scraped_product.description
            updated = True

        # Добавляем информацию о парсере в external_data
        if "scraped_sources" not in api_product.external_data:
            api_product.external_data["scraped_sources"] = []

        source_info = {
            "source": scraped_product.source,
            "url": scraped_product.url,
            "last_seen": timezone.now().isoformat(),
        }

        if source_info not in api_product.external_data["scraped_sources"]:
            api_product.external_data["scraped_sources"].append(source_info)
            updated = True

        if updated:
            api_product.save()
            return "updated", api_product
        else:
            return "skipped", api_product

    def _calculate_product_similarity(
        self, scraped_product: ScrapedProduct, existing_product: Product
    ) -> float:
        """Вычисляет похожесть товаров."""
        score = 0.0

        # Сравниваем названия
        if scraped_product.name.lower() == existing_product.name.lower():
            score += 0.4
        elif scraped_product.name.lower() in existing_product.name.lower():
            score += 0.2

        # Сравниваем бренды
        if (
            scraped_product.brand
            and existing_product.brand
            and scraped_product.brand.lower() == existing_product.brand.name.lower()
        ):
            score += 0.3

        # Сравниваем цены (если есть)
        if (
            scraped_product.price
            and existing_product.price
            and abs(float(scraped_product.price) - float(existing_product.price)) < 100
        ):
            score += 0.2

        # Сравниваем категории
        if (
            scraped_product.category
            and existing_product.category
            and scraped_product.category.lower() in existing_product.category.name.lower()
        ):
            score += 0.1

        return score

    def _contains_cyrillic(self, value: str) -> bool:
        return bool(re.search("[а-яА-Я]", value or ""))

    def _is_ai_content_ready(self, product: Product) -> bool:
        has_description = bool((product.description or "").strip())
        meta_title = (product.meta_title or "").strip()
        meta_description = (product.meta_description or "").strip()
        meta_keywords = (product.meta_keywords or "").strip()
        if not meta_title or not meta_description or not meta_keywords:
            return False
        if self._contains_cyrillic(meta_title) or self._contains_cyrillic(meta_description):
            return False
        return has_description

    def _is_ai_enabled_for_session(
        self,
        session: ScrapingSession,
        action: str,
    ) -> bool:
        config = session.scraper_config
        if action == "created":
            return bool(getattr(config, "ai_on_create_enabled", True))
        if action == "updated":
            return bool(getattr(config, "ai_on_update_enabled", True))
        return True

    def _update_existing_product(
        self,
        session: ScrapingSession,
        scraped_product: ScrapedProduct,
        existing_product: Product,
    ) -> Tuple[str, Product]:
        """Обновляет существующий товар."""
        updated = False

        # Обновляем цену, если она изменилась
        if scraped_product.price and scraped_product.price != existing_product.price:
            existing_product.old_price = existing_product.price
            existing_product.price = scraped_product.price
            existing_product.currency = scraped_product.currency
            updated = True

        # Обновляем наличие
        if scraped_product.is_available != existing_product.is_available:
            existing_product.is_available = scraped_product.is_available
            updated = True

        # Обновляем изображения, если их нет
        if not existing_product.main_image and scraped_product.images:
            main_image_url = self._get_first_image_url(scraped_product.images)
            if main_image_url:
                existing_product.main_image = main_image_url
                updated = True

        if scraped_product.category:
            normalized_name = scraped_product.category.strip().lower()
            if normalized_name in {"книги", "книга", "books"}:
                books_category = Category.objects.filter(slug="books").first()
                if books_category and existing_product.category_id != books_category.id:
                    existing_product.category = books_category
                    updated = True
                if existing_product.product_type != "books":
                    existing_product.product_type = "books"
                    updated = True

        # Обновляем external_data
        if not isinstance(existing_product.external_data, dict):
            existing_product.external_data = {}
        if "scraped_sources" not in existing_product.external_data:
            existing_product.external_data["scraped_sources"] = []

        if scraped_product.source:
            existing_product.external_data.setdefault("source", scraped_product.source)
        if scraped_product.scraped_at:
            existing_product.external_data["scraped_at"] = scraped_product.scraped_at
        if isinstance(scraped_product.attributes, dict):
            existing_product.external_data["attributes"] = scraped_product.attributes

        source_info = {
            "source": scraped_product.source,
            "url": scraped_product.url,
            "price": scraped_product.price,
            "last_updated": timezone.now().isoformat(),
        }

        existing_product.external_data["scraped_sources"].append(source_info)
        existing_product.last_synced_at = timezone.now()
        updated = True

        # Обновляем атрибуты книги (ISBN, издательство, страницы и т.д.)
        if scraped_product.attributes:
            if self._update_product_attributes(existing_product, scraped_product.attributes):
                updated = True

        if updated:
            existing_product.save()

            if scraped_product.images:
                self.catalog_normalizer._normalize_product_images(
                    existing_product, scraped_product.images
                )

            # Обновляем авторов, если они есть в атрибутах
            if scraped_product.attributes and "author" in scraped_product.attributes:
                try:
                    author_str = scraped_product.attributes["author"]
                    if author_str:
                        # Очищаем текущих авторов
                        existing_product.book_authors.all().delete()

                        author_names = [a.strip() for a in author_str.split(",") if a.strip()]
                        for idx, name in enumerate(author_names):
                            lowered = name.lower().strip()
                            if lowered in [
                                "не указано",
                                "нет",
                                "unknown",
                                "not specified",
                                "неизвестен",
                                "нет автора",
                            ]:
                                continue
                            # Разбиваем имя на имя и фамилию
                            parts = name.split()
                            if len(parts) >= 2:
                                first_name = parts[0]
                                last_name = " ".join(parts[1:])
                            else:
                                first_name = name
                                last_name = ""

                            # Создаем или находим автора
                            author, _ = Author.objects.get_or_create(
                                first_name=first_name, last_name=last_name, defaults={"bio": ""}
                            )

                            # Связываем с товаром
                            ProductAuthor.objects.create(
                                product=existing_product, author=author, sort_order=idx
                            )
                except Exception as e:
                    self.logger.error(
                        f"Ошибка при обновлении авторов для товара {existing_product.id}: {e}"
                    )

            try:
                from apps.ai.tasks import process_product_ai_task
                from apps.ai.models import AIProcessingLog, AIProcessingStatus
                from datetime import timedelta

                if not self._is_ai_enabled_for_session(session, "updated"):
                    self.logger.info(
                        f"AI обработка пропущена для товара {existing_product.id} (отключено в настройках парсера)"
                    )
                elif self._is_ai_content_ready(existing_product):
                    self.logger.info(
                        f"AI обработка пропущена для товара {existing_product.id} (описание и SEO уже заполнены)"
                    )
                else:
                    cooldown_until = timezone.now() - timedelta(days=7)
                    recent_ai = (
                        AIProcessingLog.objects.filter(
                            product=existing_product,
                            status=AIProcessingStatus.COMPLETED,
                        )
                        .order_by("-created_at")
                        .first()
                    )
                    if (
                        recent_ai
                        and recent_ai.created_at
                        and recent_ai.created_at >= cooldown_until
                    ):
                        self.logger.info(
                            f"AI обработка пропущена для товара {existing_product.id} (cooldown 7d)"
                        )
                    else:
                        process_product_ai_task.delay(
                            product_id=existing_product.id,
                            processing_type="full",
                            auto_apply=True,
                        )
                        self.logger.info(
                            f"Запущена AI обработка для товара {existing_product.id} (не заполнены описание/SEO)"
                        )
            except Exception as e:
                self.logger.error(
                    f"Не удалось запустить AI обработку для товара {existing_product.id}: {e}"
                )

        return "updated", existing_product

    def _update_product_attributes(self, product: Product, attrs: Dict[str, Any]) -> bool:
        """Обновляет атрибуты товара из словаря."""
        updated = False

        if "isbn" in attrs and attrs["isbn"]:
            new_isbn = str(attrs["isbn"]).strip()
            digits = re.sub(r"\D", "", new_isbn)
            is_valid_length = len(digits) in [10, 13]
            is_placeholder = "00000" in new_isbn or "..." in new_isbn
            if is_valid_length and not is_placeholder and new_isbn != product.isbn:
                product.isbn = new_isbn
                updated = True

        # Publisher
        if "publisher" in attrs and attrs["publisher"] != product.publisher:
            product.publisher = attrs["publisher"]
            updated = True

        # Pages
        if "pages" in attrs:
            try:
                pages_val = int(attrs["pages"])
                if 0 < pages_val < 10000 and pages_val != product.pages:
                    product.pages = pages_val
                    updated = True
            except (ValueError, TypeError):
                pass

        # Cover Type
        if "cover_type" in attrs and attrs["cover_type"] != product.cover_type:
            product.cover_type = attrs["cover_type"]
            updated = True

        # Language
        if "language" in attrs and attrs["language"] != product.language:
            product.language = attrs["language"]
            updated = True

        # Publication Date (from Year)
        if "publication_year" in attrs and attrs["publication_year"]:
            try:
                year = int(attrs["publication_year"])
                # Ставим 1 января указанного года
                new_date = datetime.date(year, 1, 1)
                if product.publication_date != new_date:
                    product.publication_date = new_date
                    updated = True
            except (ValueError, TypeError):
                pass

        # SEO Fields
        # Внимание: Спарсенные SEO данные обычно на языке источника (Русский для Ummaland).
        # Поля meta_title, meta_description в модели предназначены для АНГЛИЙСКОГО (EN).
        # Поэтому спарсенные данные сохраняем в русские поля (seo_title, seo_description)
        # или игнорируем, если они дублируют название/описание.

        # Meta Title -> seo_title (RU)
        if (
            "meta_title" in attrs
            and attrs["meta_title"]
            and attrs["meta_title"] != product.seo_title
        ):
            product.seo_title = attrs["meta_title"][:70]
            updated = True

        # Meta Description -> seo_description (RU)
        if (
            "meta_description" in attrs
            and attrs["meta_description"]
            and attrs["meta_description"] != product.seo_description
        ):
            product.seo_description = attrs["meta_description"][:160]
            updated = True

        # Keywords -> keywords (RU) - JSON field
        if "meta_keywords" in attrs and attrs["meta_keywords"]:
            keywords_list = [k.strip() for k in attrs["meta_keywords"].split(",") if k.strip()]
            if keywords_list != product.keywords:
                product.keywords = keywords_list
                updated = True

        # OG Image URL (Universal)
        if (
            "og_image_url" in attrs
            and attrs["og_image_url"]
            and attrs["og_image_url"] != product.og_image_url
        ):
            product.og_image_url = attrs["og_image_url"]
            updated = True

        # OG Title/Description (RU) - не сохраняем в английские поля og_title/og_description
        # Можно сохранить в external_data для справки
        if "og_title" in attrs or "og_description" in attrs:
            if "seo_data" not in product.external_data:
                product.external_data["seo_data"] = {}

            if "og_title" in attrs:
                product.external_data["seo_data"]["source_og_title"] = attrs["og_title"]
            if "og_description" in attrs:
                product.external_data["seo_data"]["source_og_description"] = attrs["og_description"]
            updated = True

        if product.product_type == "books":
            defaults = build_book_seo_defaults(product)
            meta_title = product.meta_title or ""
            meta_description = product.meta_description or ""
            meta_keywords = product.meta_keywords or ""
            og_title = product.og_title or ""
            og_description = product.og_description or ""
            has_cyrillic = bool(
                re.search(
                    r"[а-яА-Я]",
                    "".join(
                        [
                            meta_title,
                            meta_description,
                            meta_keywords,
                            og_title,
                            og_description,
                        ]
                    ),
                )
            )
            if not meta_title or has_cyrillic:
                product.meta_title = defaults.get("meta_title") or ""
                updated = True
            if not meta_description or has_cyrillic:
                product.meta_description = defaults.get("meta_description") or ""
                updated = True
            if not meta_keywords or has_cyrillic:
                product.meta_keywords = defaults.get("meta_keywords") or ""
                updated = True
            if not og_title or has_cyrillic:
                product.og_title = defaults.get("og_title") or ""
                updated = True
            if not og_description or has_cyrillic:
                product.og_description = defaults.get("og_description") or ""
                updated = True
            if not product.og_image_url:
                product.og_image_url = defaults.get("og_image_url") or ""
                updated = True

        return updated

    def _create_new_product(
        self, session: ScrapingSession, scraped_product: ScrapedProduct
    ) -> Tuple[str, Product]:
        """Создает новый товар."""
        # Преобразуем в формат ProductData для CatalogNormalizer
        from apps.vapi.client import ProductData

        product_data = ProductData(
            id=scraped_product.external_id,
            name=scraped_product.name,
            description=scraped_product.description,
            price=float(scraped_product.price) if scraped_product.price else None,
            currency=scraped_product.currency,
            category=scraped_product.category,
            brand=scraped_product.brand,
            images=scraped_product.images,
            url=scraped_product.url,
            availability=scraped_product.is_available,
            metadata={
                "source": scraped_product.source,
                "scraped_at": scraped_product.scraped_at,
                "attributes": scraped_product.attributes,
                "stock_quantity": scraped_product.stock_quantity,
            },
            barcode=scraped_product.barcode,
        )

        # Создаем товар через CatalogNormalizer
        product = self.catalog_normalizer.normalize_product(product_data)

        # Обновляем дополнительные атрибуты (ISBN, SEO и т.д.)
        updated = False
        if scraped_product.attributes:
            if self._update_product_attributes(product, scraped_product.attributes):
                updated = True

        if updated:
            product.save()

            # Обновляем авторов для нового товара
            if "author" in scraped_product.attributes:
                try:
                    author_str = scraped_product.attributes["author"]
                    if author_str:
                        # Очищаем текущих (на всякий случай)
                        product.book_authors.all().delete()

                        author_names = [a.strip() for a in author_str.split(",") if a.strip()]
                        for idx, name in enumerate(author_names):
                            lowered = name.lower().strip()
                            if lowered in [
                                "не указано",
                                "нет",
                                "unknown",
                                "not specified",
                                "неизвестен",
                                "нет автора",
                            ]:
                                continue
                            parts = name.split()
                            if len(parts) >= 2:
                                first_name = parts[0]
                                last_name = " ".join(parts[1:])
                            else:
                                first_name = name
                                last_name = ""

                            author, _ = Author.objects.get_or_create(
                                first_name=first_name, last_name=last_name, defaults={"bio": ""}
                            )

                            ProductAuthor.objects.create(
                                product=product, author=author, sort_order=idx
                            )
                except Exception as e:
                    self.logger.error(
                        f"Ошибка при добавлении авторов для нового товара {product.id}: {e}"
                    )

        try:
            from apps.ai.tasks import process_product_ai_task

            if not self._is_ai_enabled_for_session(session, "created"):
                self.logger.info(
                    f"AI обработка пропущена для товара {product.id} (отключено в настройках парсера)"
                )
            elif self._is_ai_content_ready(product):
                self.logger.info(
                    f"AI обработка пропущена для товара {product.id} (описание и SEO уже заполнены)"
                )
            else:
                process_product_ai_task.delay(
                    product_id=product.id,
                    processing_type="full",
                    auto_apply=True,
                )
                self.logger.info(
                    f"Запущена AI обработка для товара {product.name} (ID: {product.id})"
                )
        except Exception as e:
            self.logger.error(f"Не удалось запустить AI обработку для товара {product.id}: {e}")

        return "created", product

    def _update_scraper_stats(self, config: ScraperConfig, session: ScrapingSession, success: bool):
        """Обновляет статистику парсера."""
        config.total_runs += 1
        config.last_run_at = timezone.now()

        if success:
            config.successful_runs += 1
            config.last_success_at = timezone.now()
            config.total_products_scraped += session.products_found
            config.status = "active"
        else:
            config.last_error_at = timezone.now()
            config.last_error_message = session.error_message
            config.status = "error"

        config.save()

    def _extract_search_query(self, url: str) -> Optional[str]:
        """Извлекает поисковый запрос из URL."""
        from urllib.parse import urlparse, parse_qs

        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)

            # Пробуем разные параметры поиска
            for param in ["q", "query", "search", "searchTerm", "arama"]:
                if param in query_params:
                    return query_params[param][0]
        except:
            pass

        return None


class DeduplicationService:
    """Сервис дедупликации товаров между API и парсерами."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def find_duplicates(self) -> List[Dict[str, Any]]:
        """Находит потенциальные дубликаты товаров."""
        duplicates = []

        # Ищем товары с одинаковыми названиями
        products_by_name = {}
        for product in Product.objects.all():
            name_key = product.name.lower().strip()
            if name_key not in products_by_name:
                products_by_name[name_key] = []
            products_by_name[name_key].append(product)

        for name, products in products_by_name.items():
            if len(products) > 1:
                # Группируем по источникам
                api_products = [p for p in products if p.external_data.get("source") == "api"]
                scraped_products = [p for p in products if p.external_data.get("source") != "api"]

                if api_products and scraped_products:
                    duplicates.append(
                        {
                            "name": name,
                            "api_products": [{"id": p.id, "name": p.name} for p in api_products],
                            "scraped_products": [
                                {
                                    "id": p.id,
                                    "name": p.name,
                                    "source": p.external_data.get("source"),
                                }
                                for p in scraped_products
                            ],
                        }
                    )

        return duplicates

    def merge_duplicates(self, api_product_id: int, scraped_product_ids: List[int]) -> bool:
        """Объединяет дубликаты, оставляя API товар."""
        try:
            with transaction.atomic():
                api_product = Product.objects.get(id=api_product_id)
                scraped_products = Product.objects.filter(id__in=scraped_product_ids)

                # Собираем дополнительную информацию из спарсенных товаров
                additional_images = []
                additional_sources = []

                for scraped_product in scraped_products:
                    # Собираем изображения
                    if (
                        scraped_product.main_image
                        and scraped_product.main_image != api_product.main_image
                    ):
                        additional_images.append(scraped_product.main_image)

                    # Собираем информацию об источниках
                    additional_sources.append(
                        {
                            "source": scraped_product.external_data.get("source"),
                            "url": scraped_product.external_url,
                            "last_seen": scraped_product.updated_at.isoformat(),
                        }
                    )

                    # Удаляем спарсенный товар
                    scraped_product.delete()

                # Обновляем API товар дополнительной информацией
                if "additional_images" not in api_product.external_data:
                    api_product.external_data["additional_images"] = []
                api_product.external_data["additional_images"].extend(additional_images)

                if "scraped_sources" not in api_product.external_data:
                    api_product.external_data["scraped_sources"] = []
                api_product.external_data["scraped_sources"].extend(additional_sources)

                api_product.save()

                self.logger.info(f"Объединены дубликаты для товара {api_product.name}")
                return True

        except Exception as e:
            self.logger.error(f"Ошибка при объединении дубликатов: {e}")
            return False
