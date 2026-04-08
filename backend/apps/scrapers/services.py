"""Сервисы для интеграции парсеров с каталогом товаров."""

import logging
import re
import hashlib
import threading
from contextlib import contextmanager
from urllib.parse import urlparse
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Any, Tuple
from django.utils import timezone
from django.db import transaction

# Флаг потока — True во время активного парсинга.
# Используется ai/signals.py чтобы не запускать AI во время сохранения спарсенных товаров.
_scraping_thread_local = threading.local()


def is_scraping_in_progress() -> bool:
    """Возвращает True, если текущий поток находится в процессе парсинга."""
    return getattr(_scraping_thread_local, "in_progress", False)


@contextmanager
def scraping_in_progress_context():
    """Контекстный менеджер: устанавливает флаг парсинга на время блока."""
    _scraping_thread_local.in_progress = True
    try:
        yield
    finally:
        _scraping_thread_local.in_progress = False


from .models import ScraperConfig, ScrapingSession, ScrapedProductLog
from .parsers.registry import get_parser
from .base.scraper import ScrapedProduct, _json_safe_scraped_value
from apps.catalog.services import CatalogNormalizer
from apps.catalog.models import (
    Product,
    BookProduct,
    JewelryProduct,
    Author,
    ProductAuthor,
)
from apps.catalog.scraper_category_mapping import resolve_category_and_product_type
from apps.catalog.utils.parser_media_handler import download_and_optimize_parsed_media
import datetime


# Типы товаров, для которых при парсинге обнуляется бренд (например книги)
BRAND_CLEAR_PRODUCT_TYPES = {"books"}

# Реестр: product_type → метод получения/создания доменного объекта
_DOMAIN_GETTER_NAMES = {
    "books": "_get_book_product",
    "jewelry": "_get_jewelry_product",
    "medicines": "_get_medicine_product",
    "furniture": "_get_furniture_product",
}

# Реестр: product_type → метод обновления атрибутов доменной модели из attrs
_ATTRIBUTE_UPDATE_HANDLER_NAMES = {
    "books": "_update_book_attributes",
    "jewelry": "_update_jewelry_attributes",
    "medicines": "_update_medicine_attributes",
    "furniture": "_update_furniture_attributes",
}


class ScraperIntegrationService:
    """Сервис интеграции парсеров с каталогом."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.catalog_normalizer = CatalogNormalizer()

    def _normalize_and_get_author(self, name: str) -> Optional[Author]:
        lowered = name.lower().strip()
        if lowered in [
            "не указано", "нет", "unknown", "not specified", "неизвестен", "нет автора",
        ]:
            return None
        
        # Очищаем от лишних пробелов и кавычек
        clean_name = re.sub(r'[\"\'«»]', '', name)
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        if not clean_name:
            return None
            
        parts = clean_name.split()
        if len(parts) >= 2:
            first_name = parts[0].title()
            last_name = " ".join(parts[1:]).title()
        else:
            first_name = clean_name.title()
            last_name = ""
            
        # Поиск независимый от регистра для предотвращения дублей
        author = Author.objects.filter(
            first_name__iexact=first_name, 
            last_name__iexact=last_name
        ).first()
        
        if not author:
            author = Author.objects.create(
                first_name=first_name, 
                last_name=last_name, 
                bio=""
            )
        return author

    def run_scraper(
        self,
        scraper_config: ScraperConfig,
        start_url: Optional[str] = None,
        max_pages: int = None,
        max_products: int = None,
        max_images_per_product: int = None,
        target_category=None,
    ) -> ScrapingSession:
        """Запускает парсер и создает сессию.

        Args:
            scraper_config: Конфигурация парсера
            start_url: Начальный URL (если не указан, берется из конфигурации)
            max_pages: Максимальное количество страниц
            max_products: Максимальное количество товаров
            target_category: Категория для сохранения товаров (переопределяет default_category)

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
            target_category=target_category,
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

    @staticmethod
    def _extend_from_product_detail(scraped_products: List[ScrapedProduct], detail_result) -> None:
        """Результат parse_product_detail: один товар, список вариантов (IKEA) или None."""
        if detail_result is None:
            return
        if isinstance(detail_result, list):
            scraped_products.extend(p for p in detail_result if p is not None)
        else:
            scraped_products.append(detail_result)

    def _run_parser_scraping(
        self, parser, session: ScrapingSession, start_url: str
    ) -> List[ScrapedProduct]:
        """Выполняет парсинг с помощью парсера."""
        scraped_products = []

        try:
            # Анализируем URL
            parsed_url = urlparse(start_url)
            path_parts = [p for p in parsed_url.path.strip('/').split('/') if p]
            
            host = (parsed_url.netloc or "").lower()
            is_ikea_host = host == "ikea.com.tr" or host.endswith(".ikea.com.tr")

            is_category = (
                "/category/" in start_url or "/kategori/" in start_url or 
                (len(path_parts) == 1 and path_parts[0] in ('ilaclar', 'takviye-edici-gida'))
            )
            is_search = "/search" in start_url or "/arama" in start_url
            # IKEA TR/COM: карточка товара — /urun/, /product/ или /p/
            is_ikea_product = (
                is_ikea_host
                and any(p in path_parts for p in ("urun", "product", "p"))
            )
            is_product = (
                "/product/" in start_url or 
                ("/p/" in start_url and "instagram.com" not in start_url) or
                (len(path_parts) >= 2 and path_parts[0] in ('ilaclar', 'takviye-edici-gida')) or
                is_ikea_product
            )

            # Определяем тип парсинга по URL
            if is_category:
                # Парсинг категории
                products = parser.parse_product_list(start_url, max_pages=session.max_pages)
                scraped_products.extend(products)
                session.pages_processed += len(products) // 20 + 1  # Примерная оценка

            elif is_search:
                # Поиск товаров
                query = self._extract_search_query(start_url)
                if query:
                    products = parser.search_products(query, session.max_products)
                    scraped_products.extend(products)
                    session.pages_processed += 1

            elif is_product:
                # Парсинг отдельного товара (не Instagram); IKEA может вернуть список цветов
                detail_result = parser.parse_product_detail(start_url)
                self._extend_from_product_detail(scraped_products, detail_result)
                session.pages_processed += 1

            elif "instagram.com" in start_url:
                # --- Instagram: три варианта URL ---
                # 1. Конкретный пост:  instagram.com/p/SHORTCODE/
                # 2. Reels:            instagram.com/reel/SHORTCODE/
                # 3. Профиль:          instagram.com/username/
                # 4. Хештег:           instagram.com/explore/tags/tag/
                if "/p/" in start_url or "/reel/" in start_url:
                    # Парсим один пост
                    self.logger.info("Instagram: парсинг отдельного поста %s", start_url)
                    detail_result = parser.parse_product_detail(start_url)
                    self._extend_from_product_detail(scraped_products, detail_result)
                else:
                    # Парсим профиль или хештег — возвращает список постов
                    self.logger.info(
                        "Instagram: парсинг профиля/хештега %s (макс. %d постов)",
                        start_url,
                        session.max_pages,
                    )
                    products = parser.parse_product_list(start_url, max_pages=session.max_pages)
                    scraped_products.extend(products)
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
                self._apply_brand_mapping(session, scraped_product)
                self._normalize_scraped_media(session, scraped_product)
                # Блокируем авто-запуск AI во время сохранения — используем потоковый контекст
                with scraping_in_progress_context():
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
        """
        Устанавливает категорию товара по выбору администратора.
        Приоритет:
        1. session.target_category — категория из конкретной задачи
        2. scraper_config.default_category — категория по умолчанию из конфигурации парсера
        Авто-определение категории по атрибутам товара отключено.
        """
        # Приоритет 1: категория из задачи (task.target_category сохраняется в session)
        category = session.target_category
        # Приоритет 2: категория по умолчанию из конфигурации парсера
        if not category:
            category = session.scraper_config.default_category

        if category:
            scraped_product.category = category.slug or category.name

    def _apply_brand_mapping(
        self, session: ScrapingSession, scraped_product: ScrapedProduct
    ) -> None:
        """
        Устанавливает бренд товара.
        Приоритет:
        1. scraper_config.default_brand — бренд по умолчанию из конфигурации (самый надежный)
        2. scraped_product.brand — бренд, найденный парсером на странице
        """
        # Приоритет 1: бренд из конфигурации парсера
        default_brand = session.scraper_config.default_brand
        
        if default_brand:
            scraped_product.brand = default_brand.name
        # Если в конфигурации пусто, используем то что нашел парсер (уже в scraped_product.brand)

    def _get_first_image_url(self, media_urls: List[str]) -> Optional[str]:
        for media_url in media_urls or []:
            if self.catalog_normalizer._resolve_media_type(media_url) == "image":
                return media_url
        return media_urls[0] if media_urls else None

    def _download_parsed_media_urls(
        self,
        session: ScrapingSession,
        *,
        source_urls: List[str],
        parser_name: str,
        product_id: str,
        sub_folder: Optional[str],
        reuse_map: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[str], Dict[str, str]]:
        """Скачивает внешние URL в хранилище parsed-медиа (как у основной карточки).

        Возвращает (список URL в порядке обработки, карта исходный_URL → итоговый_URL),
        чтобы синхронизировать attributes (video_url и т.д.) с R2 и не дублировать файлы в main/.

        reuse_map — уже скачанные в этом же проходе нормализации пары исходный→R2: те же URL
        не качаются повторно с другим product_id (иначе дублируется первая картинка у вариантов).
        """
        scraper_config = session.scraper_config
        max_images = session.max_images_per_product or scraper_config.max_images_per_product or 0
        urls = source_urls[:max_images] if max_images else list(source_urls)
        headers = dict(scraper_config.headers or {})
        if scraper_config.user_agent:
            headers.setdefault("User-Agent", scraper_config.user_agent)
        out: List[str] = []
        url_map: Dict[str, str] = {}
        reuse_map = reuse_map or {}
        for index, url in enumerate(urls):
            if not isinstance(url, str) or not url:
                continue
            if url in url_map:
                out.append(url_map[url])
                continue
            if url in reuse_map:
                resolved = reuse_map[url]
                out.append(resolved)
                url_map[url] = resolved
                continue
            parsed = urlparse(url)
            if "/products/parsed/" in parsed.path:
                out.append(url)
                url_map[url] = url
                continue
            r2_url = download_and_optimize_parsed_media(
                url=url,
                parser_name=parser_name,
                product_id=product_id,
                index=index,
                headers=headers or None,
                sub_folder=sub_folder,
            )
            if r2_url:
                out.append(r2_url)
                url_map[url] = r2_url
        return out, url_map

    @staticmethod
    def _remap_attribute_urls(attributes: dict, url_map: Dict[str, str]) -> None:
        """Подменяет в attributes известные медиа-URL на версии из R2 (после парсерной загрузки)."""
        if not url_map:
            return
        vu = attributes.get("video_url")
        if isinstance(vu, str) and vu in url_map:
            attributes["video_url"] = url_map[vu]
        vus = attributes.get("video_urls")
        if isinstance(vus, list):
            attributes["video_urls"] = [
                url_map.get(x, x) for x in vus if isinstance(x, str)
            ]
        for key in ("main_video_url", "main_media_url"):
            val = attributes.get(key)
            if isinstance(val, str) and val in url_map:
                attributes[key] = url_map[val]

    def _normalize_scraped_media(
        self, session: ScrapingSession, scraped_product: ScrapedProduct
    ) -> None:
        if not isinstance(scraped_product.attributes, dict):
            scraped_product.attributes = dict(scraped_product.attributes or {})
        attributes = scraped_product.attributes

        media_urls = list(scraped_product.images or [])
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

        # Определяем sub_folder для группировки медиа (Instagram: username)
        sub_folder = attributes.get("username")

        if not sub_folder and scraped_product.category:
            sub_folder = scraped_product.category

        scraper_config = session.scraper_config
        parser_name = scraped_product.source or scraper_config.parser_class

        product_id = scraped_product.external_id or ""
        if not product_id:
            parsed_url = urlparse(scraped_product.url or "")
            last_segment = parsed_url.path.rstrip("/").split("/")[-1]
            if last_segment:
                product_id = last_segment
            else:
                raw_hash = hashlib.md5(
                    (scraped_product.url or scraped_product.name or "").encode("utf-8")
                ).hexdigest()
                product_id = raw_hash[:12]

        # Общая карта исходный_URL→R2: корень карточки и все варианты делят одни файлы при совпадении URL.
        shared_source_to_r2: Dict[str, str] = {}

        if media_urls:
            new_images, url_map = self._download_parsed_media_urls(
                session,
                source_urls=media_urls,
                parser_name=parser_name,
                product_id=product_id,
                sub_folder=sub_folder,
            )
            scraped_product.images = new_images
            shared_source_to_r2.update(url_map)
            self._remap_attribute_urls(attributes, url_map)

        # Медиа цветовых вариантов IKEA (отдельные sprCode, одна карточка FurnitureProduct)
        fv = attributes.get("furniture_variants")
        if isinstance(fv, list):
            for spec in fv:
                if not isinstance(spec, dict):
                    continue
                vid = str(spec.get("external_id") or product_id).strip() or product_id
                raw_imgs = spec.get("images") or []
                if not raw_imgs:
                    continue
                variant_images, variant_map = self._download_parsed_media_urls(
                    session,
                    source_urls=list(raw_imgs),
                    parser_name=parser_name,
                    product_id=vid,
                    sub_folder=sub_folder,
                    reuse_map=shared_source_to_r2,
                )
                spec["images"] = variant_images
                shared_source_to_r2.update(variant_map)

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

        # Для парсеров (не API) тоже привязываемся по external_id, если он уже есть
        if scraped_product.external_id:
            existing_by_external_id = Product.objects.filter(
                external_id=scraped_product.external_id
            ).first()
            if existing_by_external_id:
                return self._update_existing_product(
                    session,
                    scraped_product,
                    existing_by_external_id,
                )

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

    def _get_furniture_product(self, product: Product) -> "FurnitureProduct":
        """Находит или создаёт FurnitureProduct для Product с product_type='furniture'."""
        from apps.catalog.models import FurnitureProduct
        item = getattr(product, "furniture_item", None)
        if item:
            return item
            
        # Создаём FurnitureProduct, привязанный к shadow Product
        from django.utils.text import slugify
        import uuid

        base_slug = product.slug or slugify(product.name)
        slug = f"furn-{base_slug}"
        if len(slug) > 490:
            slug = slug[:490]
        
        i = 2
        while FurnitureProduct.objects.filter(slug=slug).exists():
            suffix = f"-{i}"
            slug = f"{slug[:500-len(suffix)]}{suffix}"
            i += 1
            
        # Базовые поля от Product
        item = FurnitureProduct(
            base_product=product,
            name=product.name,
            slug=slug,
            description=product.description or "",
            category=product.category,
            brand=product.brand,
            price=product.price,
            currency=product.currency or "RUB",
            old_price=product.old_price,
            external_id=product.external_id or "",
            external_url=product.external_url or "",
            external_data=product.external_data or {},
            is_active=product.is_active,
            is_available=product.is_available,
            main_image=product.main_image or "",
            video_url=product.video_url or "",
        )
        item.save()
        # Обновляем кеш
        product.furniture_item = item
        return item

    def _safe_decimal(self, val: Any) -> Optional[Decimal]:
        if val is None:
            return None
        try:
            return Decimal(str(val))
        except (InvalidOperation, TypeError, ValueError):
            return None

    def _sync_furniture_color_variants(
        self, furniture_product: "FurnitureProduct", product: Product, variants: List[Dict[str, Any]]
    ) -> bool:
        """Создаёт/обновляет FurnitureVariant (цвета) под одной карточкой мебели — как при ручном вводе."""
        from apps.catalog.models import FurnitureProductImage, FurnitureVariant, FurnitureVariantImage

        changed = False
        for spec in variants:
            if not isinstance(spec, dict):
                continue
            ext = str(spec.get("external_id") or "").strip()
            if not ext:
                continue
            avail = bool(spec.get("is_available", True))
            raw_sq = spec.get("stock_quantity")
            if raw_sq is not None:
                try:
                    v_stock = int(raw_sq)
                except (TypeError, ValueError):
                    v_stock = 3 if avail else 0
            else:
                v_stock = 3 if avail else 0

            price_dec = self._safe_decimal(spec.get("price"))
            raw_color = (spec.get("color") or "").strip()
            if not raw_color:
                from apps.catalog.services.ikea_service import extract_ikea_color_from_variant_info

                raw_color = extract_ikea_color_from_variant_info(spec.get("variant_info"))
            defaults = {
                "name": (spec.get("display_name") or furniture_product.name or "")[:500],
                "color": raw_color[:50],
                "sku": ext[:100],
                "price": price_dec,
                "currency": (spec.get("currency") or furniture_product.currency or "TRY")[:5],
                "external_url": (spec.get("external_url") or "")[:2000],
                "sort_order": int(spec.get("sort_order") or 0),
                "stock_quantity": v_stock,
                "is_available": bool(avail and v_stock > 0),
                "is_active": True,
            }

            variant, created = FurnitureVariant.objects.get_or_create(
                product=furniture_product,
                external_id=ext,
                defaults=defaults,
            )
            if not created:
                for field in (
                    "name",
                    "color",
                    "sku",
                    "price",
                    "currency",
                    "external_url",
                    "sort_order",
                    "is_available",
                    "stock_quantity",
                    "is_active",
                ):
                    nv = defaults.get(field)
                    if nv is not None and getattr(variant, field) != nv:
                        setattr(variant, field, nv)
                        changed = True
                variant.save()

            imgs = [u for u in (spec.get("images") or []) if isinstance(u, str) and u]
            if imgs:
                variant.images.all().delete()
                bulk = [
                    FurnitureVariantImage(
                        variant=variant,
                        image_url=u,
                        sort_order=i,
                        is_main=(i == 0),
                    )
                    for i, u in enumerate(imgs)
                ]
                FurnitureVariantImage.objects.bulk_create(bulk)
                if variant.main_image != imgs[0]:
                    variant.main_image = imgs[0]
                    variant.save(update_fields=["main_image"])
                changed = True

            vinfo = spec.get("variant_info")
            if vinfo is not None:
                ed = dict(variant.external_data) if isinstance(variant.external_data, dict) else {}
                if ed.get("ikea_variant_info") != vinfo:
                    ed["ikea_variant_info"] = vinfo
                    variant.external_data = ed
                    variant.save(update_fields=["external_data"])
                    changed = True

            changed = changed or created

        # Дубликат галереи на товаре: убираем строки с теми же URL, что уже на вариантах (в т.ч. без /products/parsed/).
        qs = furniture_product.variants.filter(is_active=True)
        variant_urls = set()
        for v in qs:
            for u in v.images.values_list("image_url", flat=True):
                s = (u or "").strip()
                if s:
                    variant_urls.add(s)
        n_rm = 0
        if variant_urls:
            n_rm, _ = FurnitureProductImage.objects.filter(
                product=furniture_product,
                image_url__in=list(variant_urls),
            ).delete()
        elif any(v.images.exists() for v in qs):
            n_rm, _ = FurnitureProductImage.objects.filter(
                product=furniture_product,
                image_url__contains="/products/parsed/",
            ).delete()
        if n_rm:
            changed = True

        default_v = qs.order_by("sort_order", "id").first()
        if default_v:
            if furniture_product.price != default_v.price:
                furniture_product.price = default_v.price
                changed = True
            if (default_v.currency or "") and furniture_product.currency != default_v.currency:
                furniture_product.currency = default_v.currency
                changed = True
            if default_v.main_image and furniture_product.main_image != default_v.main_image:
                furniture_product.main_image = default_v.main_image
                changed = True

        any_avail = qs.filter(is_available=True).exists()
        total_stock = sum((v.stock_quantity or 0) for v in qs if v.stock_quantity)
        if furniture_product.is_available != any_avail:
            furniture_product.is_available = any_avail
            changed = True
        new_sq = total_stock if total_stock > 0 else None
        if default_v and new_sq is None and default_v.stock_quantity:
            new_sq = default_v.stock_quantity
        if furniture_product.stock_quantity != new_sq:
            furniture_product.stock_quantity = new_sq
            changed = True

        if changed:
            furniture_product.save()
        product_dirty = False
        if product.price != furniture_product.price:
            product.price = furniture_product.price
            product_dirty = True
        if product.currency != furniture_product.currency:
            product.currency = furniture_product.currency
            product_dirty = True
        if product.is_available != furniture_product.is_available:
            product.is_available = furniture_product.is_available
            product_dirty = True
        if product.stock_quantity != furniture_product.stock_quantity:
            product.stock_quantity = furniture_product.stock_quantity
            product_dirty = True
        if furniture_product.main_image and product.main_image != furniture_product.main_image:
            product.main_image = furniture_product.main_image
            product_dirty = True
        if product_dirty:
            product.save()
        return changed or product_dirty

    def _update_furniture_attributes(
        self,
        product: Product,
        attrs: Dict[str, Any],
        *,
        session: Optional[ScrapingSession] = None,  # зарезервировано для единообразия вызова
    ) -> bool:
        """Обновляет специфичные поля FurnitureProduct из атрибутов парсера."""
        item = self._get_furniture_product(product)
        updated = False
        has_color_variants = bool(
            isinstance(attrs.get("furniture_variants"), list) and attrs.get("furniture_variants")
        )

        # Синхронизация базовых полей, которые могли измениться в Product (через default_brand или парсер)
        if product.brand != item.brand:
            item.brand = product.brand
            updated = True
        if product.category != item.category:
            item.category = product.category
            updated = True

        if "dimensions" in attrs and attrs["dimensions"] and attrs["dimensions"] != item.dimensions:
            item.dimensions = attrs["dimensions"]
            updated = True
        if "material" in attrs and attrs["material"] and attrs["material"] != item.material:
            item.material = attrs["material"]
            updated = True
        if "furniture_type" in attrs and attrs["furniture_type"] and attrs["furniture_type"] != item.furniture_type:
            item.furniture_type = attrs["furniture_type"]
            updated = True

        # Остаток с shadow Product — только если нет цветовых вариантов (иначе считаем из вариантов)
        if not has_color_variants:
            if product.is_available != item.is_available:
                item.is_available = product.is_available
                updated = True
            if product.stock_quantity != item.stock_quantity:
                item.stock_quantity = product.stock_quantity
                item.is_available = (item.stock_quantity or 0) > 0
                updated = True

        # Если есть видео
        if "video_url" in attrs and attrs["video_url"]:
            # Сохраняем в external_data или если есть поле video_url в модели
            if hasattr(item, "video_url") and item.video_url != attrs["video_url"]:
                item.video_url = attrs["video_url"]
                updated = True

        # Если есть информация о вариантах от IKEA, сохраняем в external_data
        if "variant_info" in attrs and attrs["variant_info"]:
            if not isinstance(item.external_data, dict):
                item.external_data = {}
            if "variants" not in item.external_data:
                item.external_data["variants"] = attrs["variant_info"]
                updated = True

        if updated:
            item.save()

        if has_color_variants:
            if self._sync_furniture_color_variants(item, product, attrs["furniture_variants"]):
                updated = True

        return updated

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
            
        # Обновляем количество на складе
        if scraped_product.stock_quantity is not None and scraped_product.stock_quantity != existing_product.stock_quantity:
            existing_product.stock_quantity = scraped_product.stock_quantity
            existing_product.is_available = (existing_product.stock_quantity or 0) > 0
            updated = True

        # Обновляем бренд, если его нет или он изменился
        if scraped_product.brand:
            from apps.catalog.models import Brand
            brand_name = scraped_product.brand.strip()
            if not existing_product.brand or existing_product.brand.name.lower() != brand_name.lower():
                brand, _ = Brand.objects.get_or_create(name=brand_name)
                existing_product.brand = brand
                updated = True

        # Обновляем изображения, если их нет
        if not existing_product.main_image and scraped_product.images:
            main_image_url = self._get_first_image_url(scraped_product.images)
            if main_image_url:
                existing_product.main_image = main_image_url
                updated = True

        # Обновляем video_url: приоритет R2 из images, иначе attributes (после _normalize_scraped_media — тоже R2)
        if not existing_product.video_url:
            first_vid = None
            if scraped_product.images:
                first_vid = self.catalog_normalizer._first_video_url_from_images(scraped_product.images)
            if first_vid:
                existing_product.video_url = first_vid
                updated = True
                self.logger.info(
                    "Updated video_url for existing product %s from gallery images",
                    existing_product.id,
                )
            elif scraped_product.attributes and scraped_product.attributes.get("video_url"):
                existing_product.video_url = scraped_product.attributes["video_url"]
                updated = True
                self.logger.info(
                    f"Updated video_url for existing product {existing_product.id} to {existing_product.video_url}"
                )

        if scraped_product.category and not existing_product.category:
            category, product_type = resolve_category_and_product_type(scraped_product.category)
            if category is not None:
                if existing_product.category_id != category.id:
                    existing_product.category = category
                    updated = True
                if product_type is not None and existing_product.product_type != product_type:
                    existing_product.product_type = product_type
                    updated = True
            if (
                existing_product.product_type in BRAND_CLEAR_PRODUCT_TYPES
                and existing_product.brand
            ):
                existing_product.brand = None
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
            existing_product.external_data["attributes"] = _json_safe_scraped_value(
                scraped_product.attributes
            )

        source_info = {
            "source": scraped_product.source,
            "url": scraped_product.url,
            # Цена из normalize_price() может быть Decimal — JSONField не сериализует её.
            "price": float(scraped_product.price)
            if scraped_product.price is not None
            else None,
            "last_updated": timezone.now().isoformat(),
        }

        existing_product.external_data["scraped_sources"].append(source_info)
        existing_product.last_synced_at = timezone.now()
        updated = True

        # Обновляем атрибуты книги (ISBN, издательство, страницы и т.д.)
        if scraped_product.attributes:
            if self._update_product_attributes(
                existing_product, scraped_product.attributes, session=session
            ):
                updated = True

        if updated:
            existing_product.save()

        # Всегда нормализуем медиа (обновляем галереи) независимо от того,
        # поменялись ли текстовые атрибуты, так как могли измениться лимиты или тип продукта
        if scraped_product.images:
            try:
                self.catalog_normalizer._normalize_product_images(
                    existing_product, scraped_product.images
                )
            except Exception as e:
                self.logger.warning(
                    f"Ошибка при нормализации изображений для товара {existing_product.id}: {e}"
                )

            # Обновляем авторов, только если их сейчас нет (или перенесли на проверку)
            if (
                scraped_product.attributes
                and "author" in scraped_product.attributes
                and existing_product.product_type == "books"
            ):
                try:
                    book_product = self._get_book_product(existing_product)
                    if not book_product.book_authors.exists():
                        author_str = scraped_product.attributes["author"]
                        if author_str:
                            author_names = [a.strip() for a in author_str.split(",") if a.strip()]
                            for idx, name in enumerate(author_names):
                                author = self._normalize_and_get_author(name)
                                if author:
                                    # Связываем с BookProduct
                                    ProductAuthor.objects.create(
                                        product=book_product, author=author, sort_order=idx
                                    )
                except Exception as e:
                    self.logger.error(
                        f"Ошибка при обновлении авторов для товара {existing_product.id}: {e}"
                    )

        return "updated", existing_product

    def _get_book_product(self, product: Product) -> "BookProduct":
        """Находит или создаёт BookProduct для Product с product_type='books'."""
        book = getattr(product, "book_item", None)
        if book:
            return book
        # Создаём BookProduct, привязанный к shadow Product
        from django.utils.text import slugify

        base_slug = product.slug or slugify(product.name)
        slug = f"book-{base_slug}"
        i = 2
        while BookProduct.objects.filter(slug=slug).exists():
            slug = f"book-{base_slug}-{i}"
            i += 1
        book = BookProduct(
            base_product=product,
            name=product.name,
            slug=slug,
            description=product.description or "",
            category=product.category,
            brand=product.brand,
            price=product.price,
            currency=product.currency or "RUB",
            old_price=product.old_price,
            external_id=product.external_id or "",
            external_url=product.external_url or "",
            external_data=product.external_data or {},
            is_active=product.is_active,
            is_available=product.is_available,
            main_image=product.main_image or "",
            video_url=product.video_url or "",
        )
        book.save()
        # Обновляем кеш, чтобы product.book_item возвращал созданный объект
        product.book_item = book
        return book

    def _get_jewelry_product(self, product: Product) -> JewelryProduct:
        """Находит или создаёт JewelryProduct для Product с product_type='jewelry'."""
        jewelry = getattr(product, "jewelry_item", None)
        if jewelry:
            return jewelry
        from django.utils.text import slugify

        base_slug = product.slug or slugify(product.name)
        slug = f"jewelry-{base_slug}"
        i = 2
        while JewelryProduct.objects.filter(slug=slug).exists():
            slug = f"jewelry-{base_slug}-{i}"
            i += 1
        jewelry = JewelryProduct(
            base_product=product,
            name=product.name,
            slug=slug,
            description=product.description or "",
            category=product.category,
            brand=product.brand,
            price=product.price,
            currency=product.currency or "RUB",
            old_price=product.old_price,
            external_id=product.external_id or "",
            external_url=product.external_url or "",
            external_data=product.external_data or {},
            is_active=product.is_active,
            is_available=product.is_available,
            main_image=product.main_image or "",
            video_url=product.video_url or "",
        )
        jewelry.save()
        product.jewelry_item = jewelry
        return jewelry

    def _get_medicine_product(self, product: Product) -> "MedicineProduct":
        """Находит или создаёт MedicineProduct для Product с product_type='medicines'."""
        from apps.catalog.models import MedicineProduct
        from django.utils.text import slugify

        medicine = getattr(product, "medicine_item", None)
        if medicine:
            return medicine

        base_slug = product.slug or slugify(product.name)
        slug = f"medicine-{base_slug}"
        i = 2
        while MedicineProduct.objects.filter(slug=slug).exists():
            slug = f"medicine-{base_slug}-{i}"
            i += 1
            
        medicine = MedicineProduct(
            base_product=product,
            name=product.name,
            slug=slug,
            description=product.description or "",
            category=product.category,
            brand=product.brand,
            price=product.price,
            currency=product.currency or "RUB",
            old_price=product.old_price,
            external_id=product.external_id or "",
            external_url=product.external_url or "",
            external_data=product.external_data or {},
            is_active=product.is_active,
            is_available=product.is_available,
            main_image=product.main_image or "",
            video_url=product.video_url or "",
        )
        medicine.save()
        product.medicine_item = medicine
        return medicine

    def _update_book_attributes(
        self, product: Product, attrs: Dict[str, Any], *, session: Optional[ScrapingSession] = None
    ) -> bool:
        """Обновляет книжные атрибуты в BookProduct."""
        if not any(
            k in attrs
            for k in ("isbn", "publisher", "pages", "cover_type", "language", "publication_year")
        ):
            return False
        book_product = self._get_book_product(product)
        updated = False
        if "isbn" in attrs and attrs["isbn"]:
            new_isbn = str(attrs["isbn"]).strip()
            digits = re.sub(r"\D", "", new_isbn)
            if (
                len(digits) in (10, 13)
                and "00000" not in new_isbn
                and "..." not in new_isbn
                and not book_product.isbn
            ):
                book_product.isbn = new_isbn
                updated = True
        if "publisher" in attrs and attrs["publisher"] and not book_product.publisher:
            book_product.publisher = attrs["publisher"]
            updated = True
        if "pages" in attrs and not book_product.pages:
            try:
                pages_val = int(attrs["pages"])
                if 0 < pages_val < 10000:
                    book_product.pages = pages_val
                    updated = True
            except (ValueError, TypeError):
                pass
        if "cover_type" in attrs and attrs["cover_type"] and not book_product.cover_type:
            book_product.cover_type = attrs["cover_type"]
            updated = True
        if "language" in attrs and attrs["language"] and not book_product.language:
            book_product.language = attrs["language"]
            updated = True
        if "publication_year" in attrs and attrs["publication_year"] and not book_product.publication_date:
            try:
                year = int(attrs["publication_year"])
                new_date = datetime.date(year, 1, 1)
                book_product.publication_date = new_date
                updated = True
            except (ValueError, TypeError):
                pass
        if updated:
            book_product.save()
        return updated

    def _update_jewelry_attributes(
        self, product: Product, attrs: Dict[str, Any], *, session: Optional[ScrapingSession] = None
    ) -> bool:
        """Обновляет атрибуты украшений в JewelryProduct."""
        if not any(
            k in attrs
            for k in (
                "jewelry_type",
                "material",
                "metal_purity",
                "stone_type",
                "carat_weight",
                "gender",
            )
        ):
            return False
        jewelry_product = self._get_jewelry_product(product)
        updated = False
        from decimal import Decimal

        valid_types = {"ring", "bracelet", "necklace", "earrings", "pendant"}
        if "jewelry_type" in attrs and attrs["jewelry_type"] and not jewelry_product.jewelry_type:
            v = str(attrs["jewelry_type"]).strip().lower()
            if v in valid_types:
                jewelry_product.jewelry_type = v
                updated = True
        if (
            "material" in attrs
            and attrs["material"]
            and not jewelry_product.material
        ):
            jewelry_product.material = str(attrs["material"]).strip()[:100]
            updated = True
        if (
            "metal_purity" in attrs
            and attrs["metal_purity"]
            and not jewelry_product.metal_purity
        ):
            jewelry_product.metal_purity = str(attrs["metal_purity"]).strip()[:50]
            updated = True
        if (
            "stone_type" in attrs
            and attrs["stone_type"]
            and not jewelry_product.stone_type
        ):
            jewelry_product.stone_type = str(attrs["stone_type"]).strip()[:100]
            updated = True
        if "carat_weight" in attrs and attrs["carat_weight"] is not None and jewelry_product.carat_weight is None:
            try:
                v = Decimal(str(attrs["carat_weight"]).strip().replace(",", "."))
                if v >= 0:
                    jewelry_product.carat_weight = v
                    updated = True
            except (ValueError, TypeError):
                pass
        if (
            "gender" in attrs
            and attrs["gender"]
            and not jewelry_product.gender
        ):
            jewelry_product.gender = str(attrs["gender"]).strip()[:10]
            updated = True
        if updated:
            jewelry_product.save()
        return updated

    def _update_medicine_attributes(
        self, product: Product, attrs: Dict[str, Any], *, session: Optional[ScrapingSession] = None
    ) -> bool:
        """Обновляет медицинские атрибуты в MedicineProduct."""
        medicine_keys = (
            "dosage_form", "active_ingredient", "prescription_required", "volume", 
            "origin_country", "sgk_status", "administration_route"
        )
        if not any(k in attrs for k in medicine_keys):
            return False
            
        medicine_product = self._get_medicine_product(product)
        updated = False
        
        if "dosage_form" in attrs and attrs["dosage_form"]:
            v = str(attrs["dosage_form"]).strip()[:100]
            if v and not medicine_product.dosage_form:
                medicine_product.dosage_form = v
                updated = True
                
        if "active_ingredient" in attrs and attrs["active_ingredient"]:
            v = str(attrs["active_ingredient"]).strip()[:300]
            if v and not medicine_product.active_ingredient:
                medicine_product.active_ingredient = v
                updated = True
                
        if "volume" in attrs and attrs["volume"]:
            v = str(attrs["volume"]).strip()[:100]
            if v and not medicine_product.volume:
                medicine_product.volume = v
                updated = True
                
        if "origin_country" in attrs and attrs["origin_country"]:
            v = str(attrs["origin_country"]).strip()[:200]
            if v and not medicine_product.origin_country:
                medicine_product.origin_country = v
                updated = True
                
        if "prescription_required" in attrs:
            val = bool(attrs["prescription_required"])
            if val != medicine_product.prescription_required:
                medicine_product.prescription_required = val
                updated = True
                
        if updated:
            medicine_product.save()
        return updated

    def _update_product_attributes(
        self,
        product: Product,
        attrs: Dict[str, Any],
        *,
        session: Optional[ScrapingSession] = None,
    ) -> bool:
        """Обновляет атрибуты товара из словаря.

        Специфичные поля типа (книги, украшения) — через реестр _ATTRIBUTE_UPDATE_HANDLER_NAMES.
        Общие поля (weight, SEO, OG) записываются в Product.
        """
        updated = False
        handler_name = _ATTRIBUTE_UPDATE_HANDLER_NAMES.get(product.product_type)
        if handler_name:
            handler = getattr(self, handler_name, None)
            if handler:
                updated = handler(product, attrs, session=session)

        # --- Общие поля → Product ---

        # Weight (e.g. "0,441" kg from ummaland)
        if "weight" in attrs and attrs["weight"] and product.weight_value is None:
            try:
                weight_str = str(attrs["weight"]).strip().replace(",", ".")
                weight_val = float(weight_str)
                if weight_val >= 0:
                    product.weight_value = weight_val
                    product.weight_unit = "kg"
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
            and not product.seo_title
        ):
            product.seo_title = attrs["meta_title"][:70]
            updated = True

        # Meta Description -> seo_description (RU)
        if (
            "meta_description" in attrs
            and attrs["meta_description"]
            and not product.seo_description
        ):
            product.seo_description = attrs["meta_description"][:160]
            updated = True

        # Keywords -> keywords (RU) - JSON field
        if "meta_keywords" in attrs and attrs["meta_keywords"] and not product.keywords:
            keywords_list = [k.strip() for k in attrs["meta_keywords"].split(",") if k.strip()]
            product.keywords = keywords_list
            updated = True

        # OG-данные от источника (на языке источника) — сохраняем в external_data для справки AI,
        # но НЕ устанавливаем в EN SEO поля модели (og_image_url, og_title, og_description).
        # Эти поля заполняет AI при ручной обработке.
        og_keys = {
            "og_image_url": "source_og_image_url",
            "og_title": "source_og_title",
            "og_description": "source_og_description",
        }
        og_has_data = any(k in attrs and attrs[k] for k in og_keys)
        if og_has_data:
            if "seo_data" not in product.external_data:
                product.external_data["seo_data"] = {}
            for attr_key, data_key in og_keys.items():
                if attr_key in attrs and attrs[attr_key] and data_key not in product.external_data["seo_data"]:
                    product.external_data["seo_data"][data_key] = attrs[attr_key]
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

        # Свежеспарсенный товар — отмечаем как новинку
        if not product.is_new:
            product.is_new = True
            product.save(update_fields=["is_new"])

        # Количество по умолчанию = 3 только для доступных товаров, если парсер не передал остаток
        if product.is_available and not product.stock_quantity:
            product.stock_quantity = 3
            product.save(update_fields=["stock_quantity"])

        # Для типов из BRAND_CLEAR_PRODUCT_TYPES убираем бренд, если проставился
        if product.product_type in BRAND_CLEAR_PRODUCT_TYPES and product.brand:
            product.brand = None
            product.save(update_fields=["brand"])

        # Обновляем дополнительные атрибуты (ISBN, SEO, вес и т.д.)
        # normalize_product уже вызвал _sync_product_fields_from_metadata, но
        # _update_product_attributes дополнительно заполняет SEO поля и вес,
        # а также создаёт доменные объекты (BookProduct, JewelryProduct и т.д.).
        if scraped_product.attributes:
            if self._update_product_attributes(product, scraped_product.attributes, session=session):
                product.save()

        # После создания доменной модели нужно переназначить галерею на неё, а не на Product.
        # normalize_product вызывал _normalize_product_images до появления domain_item,
        # поэтому изображения могли сохраниться как ProductImage и быть невидимыми для BookProduct и др.
        # Здесь повторно вызываем нормализацию медиа: теперь product.domain_item указывает
        # на конкретную доменную модель, и все изображения попадут в её gallery (BookProductImage и т.п.).
        if scraped_product.images:
            try:
                self.catalog_normalizer._normalize_product_images(product, scraped_product.images)
            except Exception as e:
                self.logger.warning(
                    "Failed to re-normalize media for new product %s (external_id=%s): %s",
                    product.pk,
                    scraped_product.external_id,
                    e,
                )

        # Авторы привязаны к BookProduct — сохраняем всегда, не зависит от updated
        if (
            scraped_product.attributes
            and "author" in scraped_product.attributes
            and product.product_type == "books"
        ):
            try:
                author_str = scraped_product.attributes["author"]
                if author_str:
                    book_product = self._get_book_product(product)
                    book_product.book_authors.all().delete()

                    author_names = [a.strip() for a in author_str.split(",") if a.strip()]
                    for idx, name in enumerate(author_names):
                        author = self._normalize_and_get_author(name)
                        if author:
                            ProductAuthor.objects.create(
                                product=book_product, author=author, sort_order=idx
                            )
            except Exception as e:
                self.logger.error(
                    f"Ошибка при добавлении авторов для нового товара {product.id}: {e}"
                )

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
        except Exception:
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
