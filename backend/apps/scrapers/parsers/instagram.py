"""Парсер для Instagram — сбор постов с медиа и описаниями для карточек товаров."""

import logging
import random
import re
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

import instaloader

from ..base.scraper import BaseScraper, ScrapedProduct, ScraperAccessBlockedError
from ..base.utils import clean_text


class InstagramSourceError(RuntimeError):
    """Instagram ответил ошибкой, которую нельзя считать пустым результатом."""


class InstagramParser(BaseScraper):
    """Парсер для постов Instagram.

    Парсит публичные профили (@username), хештеги и отдельные посты.
    Каждый пост превращается в ScrapedProduct: извлекаются медиа (все фото
    и видео из карусели), цена, автор, ISBN и другие атрибуты из caption.

    Категория товара НЕ задаётся внутри парсера — она определяется через
    target_category в настройках задачи парсинга (InstagramScraperTask) или
    SiteScraperTask. Парсер возвращает category="" и позволяет сервису
    интеграции (ScraperIntegrationService) проставить нужную категорию.
    """

    # -----------------------------------------------------------------------
    # Инициализация
    # -----------------------------------------------------------------------

    MOBILE_FEED_APP_ID = "936619743392459"
    MOBILE_FEED_ASBD_ID = "198387"

    @staticmethod
    def _status_code_from_exception(exc: Exception) -> int:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", 0) or 0
        if status_code:
            return int(status_code)

        match = re.search(r"(?:HTTP\s+)?(400|401|403|404|407|429|5\d\d)\b", str(exc))
        return int(match.group(1)) if match else 0

    def _raise_source_error(
        self,
        exc: Exception,
        *,
        operation: str,
        url: Optional[str] = None,
    ) -> None:
        """Не позволяет ошибкам Instaloader превращаться в успешный пустой результат."""
        if isinstance(exc, ScraperAccessBlockedError):
            raise exc

        status_code = self._status_code_from_exception(exc)
        source_url = url or self.base_url
        if isinstance(exc, instaloader.exceptions.QueryReturnedForbiddenException):
            status_code = status_code or 403
        if status_code in (401, 403, 407):
            raise ScraperAccessBlockedError(
                message=(
                    f"Instagram отклонил запрос при операции «{operation}» "
                    f"(HTTP {status_code}, {source_url})"
                ),
                source="Instagram",
                status_code=status_code,
                url=source_url,
            ) from exc

        if isinstance(exc, instaloader.exceptions.ProfileNotExistsException):
            message = f"Instagram-профиль недоступен или не существует: {source_url}"
        else:
            status_suffix = f" (HTTP {status_code})" if status_code else ""
            message = f"Ошибка Instagram при операции «{operation}»{status_suffix}: {exc}"
        raise InstagramSourceError(message) from exc

    def __init__(
        self,
        base_url: str = "https://www.instagram.com",
        username: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs,
    ):
        """Инициализирует Instagram-парсер.

        Args:
            base_url: Базовый URL Instagram (для BaseScraper).
            username: Логин для авторизации в Instagram (опционально).
            password: Пароль для авторизации в Instagram (опционально).
            **kwargs: Дополнительные параметры для BaseScraper.
        """
        super().__init__(
            base_url=base_url,
            # Большие задержки обязательны: Instagram агрессивно блокирует
            # аккаунты и IP при частых запросах без паузы.
            delay_range=(5, 10),
            **kwargs,
        )

        # Инициализируем Instaloader — библиотеку для работы с Instagram API.
        # Отключаем скачивание файлов на диск: нам нужны только URL,
        # скачивание в R2 выполняет ScraperIntegrationService.
        self.loader = instaloader.Instaloader(
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern="",
            max_connection_attempts=max(1, self.max_retries),
            request_timeout=float(self.timeout),
        )

        # Instaloader использует собственную requests.Session, поэтому настройки
        # BaseScraper нужно применить к ней отдельно. Прокси доступен уже здесь;
        # headers/cookies придут позднее через configure_request_identity().
        self._configure_loader_transport()

        # Учётные данные для авторизации (опционально)
        self.username = username
        self.password = password
        self._authenticated = False
        self._authentication_attempted = False
        # Необязательные callbacks используются только Celery-задачей Instagram.
        # Обычный вызов парсера и все остальные источники работают как раньше.
        self._task_control_callback: Optional[Callable[[], None]] = None
        self._task_product_callback: Optional[Callable[[ScrapedProduct], bool]] = None
        self._task_progress_callback: Optional[
            Callable[[int, int, str, bool, str], None]
        ] = None

    def configure_task_callbacks(
        self,
        *,
        control_callback: Optional[Callable[[], None]] = None,
        product_callback: Optional[Callable[[ScrapedProduct], bool]] = None,
        progress_callback: Optional[Callable[[int, int, str, bool, str], None]] = None,
    ) -> None:
        """Подключает управление и live-progress для фоновой Instagram-задачи."""
        self._task_control_callback = control_callback
        self._task_product_callback = product_callback
        self._task_progress_callback = progress_callback

    def _check_task_control(self) -> None:
        if self._task_control_callback:
            self._task_control_callback()

    def _publish_task_product(self, product: ScrapedProduct) -> bool:
        if not self._task_product_callback:
            return True
        return self._task_product_callback(product) is not False

    def _publish_task_progress(
        self,
        processed: int,
        total: int,
        shortcode: str,
        valid: bool,
        error_message: str = "",
    ) -> None:
        if self._task_progress_callback:
            self._task_progress_callback(
                processed,
                total,
                shortcode,
                valid,
                error_message,
            )

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Закрывает обе HTTP-сессии парсера."""
        try:
            self.loader.context.close()
        finally:
            super().__exit__(exc_type, exc_val, exc_tb)

    def _configure_loader_transport(
        self,
        *,
        user_agent: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
    ) -> None:
        """Применяет ScraperConfig к внутренней requests.Session Instaloader."""
        session = self.loader.context._session
        if self.proxies:
            session.proxies.update(self.proxies)

        clean_headers = {
            str(key): str(value)
            for key, value in (headers or {}).items()
            if key and value is not None
        }
        clean_cookies = {
            str(key): str(value)
            for key, value in (cookies or {}).items()
            if key and value is not None
        }
        if user_agent:
            clean_headers["User-Agent"] = str(user_agent)
        if clean_headers:
            session.headers.update(clean_headers)
        if clean_cookies:
            session.cookies.update(clean_cookies)

    def configure_request_identity(
        self,
        *,
        user_agent: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
    ) -> None:
        """Настраивает как общий HTTP-клиент, так и транспорт Instaloader."""
        super().configure_request_identity(
            user_agent=user_agent,
            headers=headers,
            cookies=cookies,
        )
        self._configure_loader_transport(
            user_agent=user_agent,
            headers=headers,
            cookies=cookies,
        )
        self._ensure_authenticated()

    def _ensure_authenticated(self) -> None:
        """Авторизуется один раз и только после применения proxy/headers/cookies."""
        if self._authentication_attempted or not (self.username and self.password):
            return
        self._authentication_attempted = True
        self._authenticate()

    # -----------------------------------------------------------------------
    # Обязательные методы BaseScraper
    # -----------------------------------------------------------------------

    def get_name(self) -> str:
        """Уникальное имя парсера (ключ в реестре и в ScraperConfig)."""
        return "instagram"

    def get_supported_domains(self) -> List[str]:
        """Домены, которые обслуживает этот парсер."""
        return ["instagram.com", "www.instagram.com"]

    def parse_product_list(
        self,
        category_url: str,
        max_pages: int = 10,
    ) -> List[ScrapedProduct]:
        """Парсит список товаров из профиля Instagram или по хештегу.

        Args:
            category_url: URL профиля (instagram.com/username/) или хештега
                          (instagram.com/explore/tags/books/).
            max_pages: Максимальное количество постов для парсинга.
                       (Здесь «страница» = один пост, чтобы соответствовать
                       интерфейсу BaseScraper.)

        Returns:
            Список спарсенных товаров.
        """
        try:
            self._ensure_authenticated()
            # Определяем тип URL: хештег или профиль
            if "/explore/tags/" in category_url or category_url.lstrip().startswith("#"):
                hashtag = self._extract_hashtag(category_url)
                return self._parse_hashtag(hashtag, max_pages)
            username = self._extract_username(category_url)
            return self._parse_profile(username, max_pages)
        except ScraperAccessBlockedError:
            raise
        except Exception as e:
            self.logger.error("Ошибка при парсинге списка товаров: %s", e)
            raise

    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        """Парсит один конкретный пост Instagram по URL.

        Args:
            product_url: URL вида instagram.com/p/SHORTCODE/ или
                         instagram.com/reel/SHORTCODE/

        Returns:
            Спарсенный товар или None при ошибке.
        """
        try:
            self._ensure_authenticated()
            shortcode = self._extract_shortcode(product_url)
            if not shortcode:
                self.logger.error("Не удалось извлечь shortcode из URL: %s", product_url)
                return None

            post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
            return self._parse_post(post)

        except ScraperAccessBlockedError:
            raise
        except instaloader.exceptions.InstaloaderException as e:
            self._raise_source_error(
                e,
                operation="получение поста",
                url=product_url,
            )
        except Exception as e:
            self.logger.error("Ошибка при парсинге поста %s: %s", product_url, e)
            raise

    def validate_product(self, product: ScrapedProduct) -> bool:
        """Проверяет минимальную валидность товара перед добавлением в список.

        Требования:
        - Хотя бы одно изображение (обложка или превью).
        - Описание не менее 10 символов (пустые посты не интересны).
        """
        if not super().validate_product(product):
            return False

        if not product.images:
            self.logger.warning("Товар '%s' без изображений — пропускаем", product.name)
            return False

        if not product.description or len(product.description.strip()) < 10:
            self.logger.warning(
                "Товар '%s' с пустым или слишком коротким описанием — пропускаем",
                product.name,
            )
            return False

        return True

    # -----------------------------------------------------------------------
    # Авторизация
    # -----------------------------------------------------------------------

    def _authenticate(self) -> None:
        """Выполняет вход в Instagram.

        ВАЖНО: Используйте только бот-аккаунты. Авторизация личного аккаунта
        ведёт к блокировке.
        """
        try:
            self.loader.login(self.username, self.password)
            self._authenticated = True
            self.logger.info("Успешная авторизация для @%s", self.username)
        except instaloader.exceptions.QueryReturnedForbiddenException as e:
            self._raise_source_error(
                e,
                operation=f"авторизация @{self.username}",
                url=self.base_url,
            )
        except instaloader.exceptions.InstaloaderException as e:
            self.logger.warning(
                "Ошибка авторизации для @%s: %s. Продолжаем без авторизации.",
                self.username,
                e,
            )

    # -----------------------------------------------------------------------
    # Парсинг профиля и хештега
    # -----------------------------------------------------------------------

    def _parse_profile(self, username: str, max_posts: int = 50) -> List[ScrapedProduct]:
        """Парсит последние посты из публичного профиля.

        Args:
            username: Имя пользователя без @.
            max_posts: Лимит постов.

        Returns:
            Список спарсенных товаров.
        """
        products: List[ScrapedProduct] = []
        seen_shortcodes = set()
        try:
            self.logger.info("Начинаем парсинг профиля @%s (макс. %d постов)", username, max_posts)
            profile = instaloader.Profile.from_username(self.loader.context, username)

            self._consume_profile_posts(
                profile.get_posts(),
                products=products,
                seen_shortcodes=seen_shortcodes,
                max_posts=max_posts,
            )
            return products
        except ScraperAccessBlockedError:
            raise
        except instaloader.exceptions.InstaloaderException as primary_error:
            self.logger.warning(
                "Основной Instagram API недоступен для @%s: %s. "
                "Пробуем совместимый mobile-feed fallback.",
                username,
                primary_error,
            )
            try:
                self._consume_profile_posts(
                    self._iter_mobile_feed_posts(username, max_posts=max_posts),
                    products=products,
                    seen_shortcodes=seen_shortcodes,
                    max_posts=max_posts,
                )
                return products
            except ScraperAccessBlockedError:
                raise
            except Exception as fallback_error:
                self.logger.error(
                    "Mobile-feed fallback Instagram не сработал для @%s: %s",
                    username,
                    fallback_error,
                )
                self._raise_source_error(
                    fallback_error,
                    operation=f"получение профиля @{username} через fallback",
                    url=f"https://www.instagram.com/{username}/",
                )
        except Exception as e:
            self.logger.error("Ошибка при парсинге профиля @%s: %s", username, e)
            raise

    def _consume_profile_posts(
        self,
        posts,
        *,
        products: List[ScrapedProduct],
        seen_shortcodes: set,
        max_posts: int,
    ) -> None:
        """Обрабатывает посты, сохраняя лимит и дедупликацию между API/fallback."""
        for post in posts:
            if len(seen_shortcodes) >= max_posts:
                break
            shortcode = post.shortcode
            if shortcode in seen_shortcodes:
                continue
            self._check_task_control()
            product = None
            error_message = ""
            try:
                product = self._parse_post(post)
                seen_shortcodes.add(shortcode)
            except instaloader.exceptions.InstaloaderException:
                raise
            except ScraperAccessBlockedError:
                raise
            except Exception as e:
                seen_shortcodes.add(shortcode)
                error_message = str(e)
                self.logger.warning("  Ошибка при парсинге поста %s: %s", shortcode, e)

            valid = bool(product and self.validate_product(product))
            should_continue = True
            if valid:
                if self._task_product_callback:
                    should_continue = self._publish_task_product(product)
                else:
                    products.append(product)
                self.logger.info(
                    "  [%d/%d] Спарсен пост %s: %s",
                    len(seen_shortcodes),
                    max_posts,
                    shortcode,
                    product.name[:60],
                )
            self._publish_task_progress(
                len(seen_shortcodes),
                max_posts,
                shortcode,
                valid,
                error_message,
            )
            if not should_continue:
                break

    def _iter_mobile_feed_posts(self, username: str, *, max_posts: int):
        """Fallback для business-профилей и сломанной GraphQL-пагинации Instagram."""
        if max_posts <= 0:
            return

        encoded_username = quote(username, safe="")
        url = f"https://www.instagram.com/api/v1/feed/user/{encoded_username}/username/"
        headers = {
            "X-IG-App-ID": self.MOBILE_FEED_APP_ID,
            "X-ASBD-ID": self.MOBILE_FEED_ASBD_ID,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://www.instagram.com/{encoded_username}/",
        }
        params = {"count": min(12, max_posts)}
        yielded = 0

        while yielded < max_posts:
            response = self.loader.context._session.get(
                url,
                headers=headers,
                params=params,
                timeout=float(self.timeout),
            )
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code in (401, 403, 407):
                raise ScraperAccessBlockedError(
                    message=(
                        "Instagram отклонил mobile-feed fallback "
                        f"(HTTP {status_code}, профиль @{username})"
                    ),
                    source="Instagram",
                    status_code=status_code,
                    url=url,
                )
            response.raise_for_status()

            try:
                payload = response.json()
            except ValueError as exc:
                raise InstagramSourceError(
                    f"Instagram вернул невалидный JSON для профиля @{username}"
                ) from exc

            if payload.get("status") == "fail":
                raise InstagramSourceError(
                    f"Instagram mobile feed отклонил профиль @{username}: "
                    f"{payload.get('message') or 'неизвестная ошибка'}"
                )

            items = payload.get("items") or []
            for item in items:
                if yielded >= max_posts:
                    break
                yield instaloader.Post.from_iphone_struct(self.loader.context, item)
                yielded += 1

            if not payload.get("more_available"):
                break
            next_max_id = payload.get("next_max_id")
            if not next_max_id:
                break
            params["max_id"] = next_max_id
            params["count"] = min(12, max_posts - yielded)
            self._wait_between_mobile_feed_pages()

    def _wait_between_mobile_feed_pages(self) -> None:
        """Соблюдает настроенную паузу только между fallback-страницами."""
        low, high = self.delay_range
        time.sleep(random.uniform(min(low, high), max(low, high)))

    def _parse_hashtag(self, hashtag: str, max_posts: int = 50) -> List[ScrapedProduct]:
        """Парсит последние посты по хештегу.

        Args:
            hashtag: Хештег без символа #.
            max_posts: Лимит постов.

        Returns:
            Список спарсенных товаров.
        """
        products = []

        try:
            self.logger.info("Начинаем парсинг хештега #%s (макс. %d постов)", hashtag, max_posts)
            hashtag_obj = instaloader.Hashtag.from_name(self.loader.context, hashtag)

            for idx, post in enumerate(hashtag_obj.get_posts()):
                if idx >= max_posts:
                    break
                self._check_task_control()
                product = None
                error_message = ""
                try:
                    product = self._parse_post(post)
                except instaloader.exceptions.InstaloaderException:
                    raise
                except ScraperAccessBlockedError:
                    raise
                except Exception as e:
                    error_message = str(e)
                    self.logger.warning("  Ошибка при парсинге поста %s: %s", post.shortcode, e)

                valid = bool(product and self.validate_product(product))
                should_continue = True
                if valid:
                    if self._task_product_callback:
                        should_continue = self._publish_task_product(product)
                    else:
                        products.append(product)
                    self.logger.info(
                        "  [%d/%d] Спарсен пост %s: %s",
                        idx + 1,
                        max_posts,
                        post.shortcode,
                        product.name[:60],
                    )
                self._publish_task_progress(
                    idx + 1,
                    max_posts,
                    post.shortcode,
                    valid,
                    error_message,
                )
                if not should_continue:
                    break

        except ScraperAccessBlockedError:
            raise
        except instaloader.exceptions.InstaloaderException as e:
            self._raise_source_error(
                e,
                operation=f"получение хештега #{hashtag}",
                url=f"https://www.instagram.com/explore/tags/{hashtag}/",
            )
        except Exception as e:
            self.logger.error("Ошибка при парсинге хештега #%s: %s", hashtag, e)
            raise

        return products

    # -----------------------------------------------------------------------
    # Парсинг одного поста
    # -----------------------------------------------------------------------

    def _post_metric(self, post: instaloader.Post, property_name: str, iphone_key: str):
        """Читает необязательный счётчик без дополнительного GraphQL-запроса."""
        iphone_struct = getattr(post, "_iphone_struct_", None) or {}
        if iphone_key in iphone_struct:
            return iphone_struct.get(iphone_key)
        try:
            return getattr(post, property_name)
        except (
            instaloader.exceptions.InstaloaderException,
            AttributeError,
            KeyError,
            TypeError,
        ) as exc:
            self.logger.warning(
                "Не удалось получить необязательный Instagram-счётчик %s: %s",
                property_name,
                exc,
            )
            return None

    def _parse_post(self, post: instaloader.Post) -> Optional[ScrapedProduct]:
        """Преобразует объект поста Instaloader в ScrapedProduct.

        Основной метод: извлекает все данные из поста и возвращает
        унифицированную структуру ScrapedProduct для дальнейшей обработки
        сервисом интеграции.

        Args:
            post: Объект поста из библиотеки instaloader.

        Returns:
            ScrapedProduct или None при критической ошибке.
        """
        try:
            # --- Текст поста ---
            # raw_caption сохраняем как есть — AI будет использовать его
            # для извлечения данных и генерации описаний.
            raw_caption = post.caption or ""
            caption_clean = clean_text(raw_caption)

            # --- Структурированные данные из caption ---
            # Пытаемся извлечь цену, автора, ISBN и другие поля.
            # Чего нет в caption — останется None; AI дополнит позже.
            extracted = self._extract_caption_data(caption_clean)

            # --- Название товара ---
            # Умное извлечение: кавычки → первая содержательная строка → fallback.
            product_name = self._extract_product_name(caption_clean)

            # --- Медиа: ВСЕ фото и видео из поста ---
            images, video_urls = self._extract_all_media(post)

            # --- Хештеги ---
            hashtags = self._extract_hashtags(raw_caption)

            # --- Цена и доступность ---
            # Instagram is a manual catalogue source, not a live stock API.
            # Missing price text must not be interpreted as "out of stock";
            # a manager may set/freeze the storefront price separately.
            price = extracted.get("price")
            currency = extracted.get("currency", "RUB")
            is_available = True

            # --- Атрибуты: метаданные поста + извлечённые данные ---
            # raw_caption обязательно сохраняем: ContentGenerator его читает
            # для генерации описания и SEO-данных.
            attributes: Dict[str, Any] = {
                # Метаданные поста
                "likes_count": self._post_metric(post, "likes", "like_count"),
                "comments_count": self._post_metric(
                    post,
                    "comments",
                    "comment_count",
                ),
                "hashtags": hashtags,
                "post_date": post.date_utc.isoformat() if post.date_utc else None,
                "username": post.owner_username,
                "is_video": post.is_video,
                # Сырое описание для AI-обработки
                "raw_caption": raw_caption,
            }

            # Добавляем видео-URL (если есть)
            if video_urls:
                # Первый видео-URL — основной
                attributes["video_url"] = video_urls[0]
                if len(video_urls) > 1:
                    # Остальные — дополнительные
                    attributes["video_urls"] = video_urls[1:]

            # Добавляем данные извлечённые из caption
            # (автор, ISBN, издательство, страницы и т.д.)
            for key, value in extracted.items():
                # Цену уже обработали отдельно выше
                if key not in ("price", "currency") and value is not None:
                    attributes[key] = value

            # Fallback для publication_year: если год издания не нашли в подписи —
            # используем год публикации поста в Instagram.
            # services.py читает attributes["publication_year"] для BookProduct.publication_date.
            if "publication_year" not in attributes and post.date_utc:
                attributes["publication_year"] = post.date_utc.year

            # Собираем итоговый ScrapedProduct.
            # ВАЖНО: category намеренно оставляем пустой — категория
            # определяется через target_category в задаче парсинга,
            # а не хардкодится в парсере.
            product = ScrapedProduct(
                name=product_name,
                description=caption_clean,
                price=price,
                currency=currency,
                url=f"https://www.instagram.com/p/{post.shortcode}/",
                images=images,
                external_id=post.shortcode,
                category="",          # Определяется через target_category в Admin
                is_available=is_available,
                stock_quantity=None,   # Система подставит 3 по умолчанию
                attributes=attributes,
                source=self.get_name(),
                scraped_at=datetime.now().isoformat(),
            )

            return product

        except instaloader.exceptions.InstaloaderException:
            raise
        except ScraperAccessBlockedError:
            raise
        except Exception as e:
            self.logger.error("Ошибка при парсинге поста: %s", e)
            return None

    # -----------------------------------------------------------------------
    # Извлечение данных из caption
    # -----------------------------------------------------------------------

    def _extract_caption_data(self, caption: str) -> Dict[str, Any]:
        """Извлекает структурированные данные из текста поста.

        Парсит caption построчно и по паттернам ищет:
        - цену и валюту
        - автора
        - издательство
        - ISBN
        - количество страниц
        - тип обложки/переплёта
        - язык издания
        - год публикации

        Принцип «по возможности»: если данных нет в тексте — поле не
        включается в результат. AI дополнит недостающее из изображений.

        Args:
            caption: Очищенный текст поста (без лишних пробелов).

        Returns:
            Словарь с найденными полями. Только те ключи, для которых
            удалось что-то найти.
        """
        result: Dict[str, Any] = {}
        if not caption:
            return result

        # ---- Цена ----
        # Паттерны: «Цена: 1200₽», «1 200 руб», «стоимость 500 р», «Price: $15»
        price_patterns = [
            # Русскоязычные паттерны с ключевыми словами
            r"(?:цена|стоимость|price|цена:)\s*[:\s]?\s*([\d\s\u00A0]+(?:[.,]\d{1,2})?)\s*(?:₽|руб(?:лей)?\.?|р\.?\b|rub\b)",
            # Доллары и евро
            r"(?:цена|стоимость|price)\s*[:\s]?\s*\$\s*([\d\s\u00A0]+(?:[.,]\d{1,2})?)",
            r"(?:цена|стоимость|price)\s*[:\s]?\s*([\d\s\u00A0]+(?:[.,]\d{1,2})?)\s*(?:\$|usd\b)",
            r"(?:цена|стоимость|price)\s*[:\s]?\s*([\d\s\u00A0]+(?:[.,]\d{1,2})?)\s*(?:€|eur\b)",
            r"(?:цена|стоимость|price)\s*[:\s]?\s*([\d\s\u00A0]+(?:[.,]\d{1,2})?)\s*(?:₺|tl\b|try\b)",
            # Цифра сразу перед символом ₽ (без ключевого слова)
            r"([\d\s\u00A0]{2,})\s*₽",
        ]

        # Определяем валюту по символу/слову рядом с ценой
        currency_map = [
            (r"[$]|usd\b", "USD"),
            (r"[€]|eur\b", "EUR"),
            (r"[₺]|tl\b|try\b", "TRY"),
            (r"₽|руб|rub\b|р\.\b", "RUB"),
        ]

        caption_lower = caption.lower()
        for pattern in price_patterns:
            price_match = re.search(pattern, caption_lower, re.IGNORECASE)
            if price_match:
                raw_price = price_match.group(1)
                # Убираем пробелы-разделители тысяч
                raw_price = re.sub(r"[\s\u00A0]", "", raw_price)
                raw_price = raw_price.replace(",", ".")
                try:
                    price_val = float(raw_price)
                    if price_val > 0:
                        result["price"] = price_val
                        # Определяем валюту по контексту вокруг паттерна
                        context = caption[
                            max(0, price_match.start() - 10) : price_match.end() + 10
                        ].lower()
                        result["currency"] = "RUB"  # По умолчанию рубли
                        for curr_pattern, curr_code in currency_map:
                            if re.search(curr_pattern, context, re.IGNORECASE):
                                result["currency"] = curr_code
                                break
                        break
                except ValueError:
                    continue

        # ---- Автор ----
        # Паттерны: «Автор: Иванов», «Автор — Иванов И.И.», «Author: Name»,
        #           «✍️ Иванов» (с эмодзи)
        author_patterns = [
            r"(?:автор[ы]?|author)[:\s–—-]+([^\n#@]{3,60})",
            r"✍\uFE0F?\s+([^\n#@]{3,60})",
            r"📖\s*(?:автор[ы]?)[:\s–—-]+([^\n#@]{3,60})",
        ]
        for pattern in author_patterns:
            m = re.search(pattern, caption, re.IGNORECASE)
            if m:
                author_val = clean_text(m.group(1))
                # Отсекаем мусор: если после имени идёт ключевое слово
                author_val = re.split(
                    r"\s*(?:издательство|isbn|страниц|переплет|язык|цена|#)", author_val, flags=re.IGNORECASE
                )[0].strip()
                if author_val and len(author_val) > 2:
                    result["author"] = author_val
                    break

        # ---- Издательство ----
        # Паттерны: «Издательство: УММА», «Изд-во: Эксмо», «Publisher: ...»
        publisher_patterns = [
            r"(?:издательство|изд-во|изд\.)\s*[:\s–—-]+([^\n#@]{2,60})",
            r"publisher\s*[:\s–—-]+([^\n#@]{2,60})",
        ]
        for pattern in publisher_patterns:
            m = re.search(pattern, caption, re.IGNORECASE)
            if m:
                pub_val = clean_text(m.group(1)).strip()
                pub_val = re.split(
                    r"\s*(?:isbn|страниц|переплет|язык|цена|#)", pub_val, flags=re.IGNORECASE
                )[0].strip()
                if pub_val and len(pub_val) > 1:
                    result["publisher"] = pub_val
                    break

        # ---- ISBN ----
        # ISBN-13 (978-...) и ISBN-10 — ищем характерный формат
        isbn_match = re.search(
            r"isbn\s*[-:–—]?\s*((?:978|979)?[\s-]?\d[\d\s-]{8,})",
            caption,
            re.IGNORECASE,
        )
        if isbn_match:
            isbn_raw = isbn_match.group(1).strip()
            # Нормализуем: только цифры и дефисы
            isbn_clean = re.sub(r"[^\d-]", "", isbn_raw)
            digits_only = re.sub(r"\D", "", isbn_clean)
            if len(digits_only) in (10, 13):
                result["isbn"] = isbn_clean

        # ---- Количество страниц ----
        # Паттерны: «208 стр», «страниц: 350», «Pages: 208»
        pages_patterns = [
            r"(\d{2,4})\s*(?:стр\.|страниц|с\.)",
            r"(?:страниц|стр\.|pages?)\s*[:\s–—-]+(\d{2,4})",
        ]
        for pattern in pages_patterns:
            m = re.search(pattern, caption, re.IGNORECASE)
            if m:
                try:
                    pages_val = int(m.group(1))
                    if 10 <= pages_val <= 9999:
                        result["pages"] = pages_val
                        break
                except ValueError:
                    continue

        # ---- Тип обложки/переплёта ----
        # Паттерны: «Переплет: твердый», «Обложка: мягкая», «Cover: hardcover»
        cover_patterns = [
            r"(?:переплет[её]?|обложка|cover)\s*[:\s–—-]+([^\n#@,]{3,30})",
        ]
        cover_map = {
            "тверд": "твердый",
            "мягк": "мягкий",
            "суперобл": "суперобложка",
            "hard": "твердый",
            "soft": "мягкий",
        }
        for pattern in cover_patterns:
            m = re.search(pattern, caption, re.IGNORECASE)
            if m:
                cover_raw = clean_text(m.group(1)).lower()
                # Приводим к стандартным значениям
                for key, std_val in cover_map.items():
                    if key in cover_raw:
                        result["cover_type"] = std_val
                        break
                else:
                    result["cover_type"] = clean_text(m.group(1))[:30]
                break

        # ---- Язык издания ----
        # Паттерны: «Язык: русский», «Language: Arabic», «🇷🇺 Язык: рус»
        lang_patterns = [
            r"(?:язык|language)\s*[:\s–—-]+([^\n#@,]{2,20})",
        ]
        # Карта нормализации языков
        lang_map = {
            "рус": "rus",
            "русск": "rus",
            "russian": "rus",
            "англ": "eng",
            "английск": "eng",
            "english": "eng",
            "arab": "ara",
            "арабск": "ara",
            "türk": "tur",
            "турецк": "tur",
        }
        for pattern in lang_patterns:
            m = re.search(pattern, caption, re.IGNORECASE)
            if m:
                lang_raw = clean_text(m.group(1)).lower().strip()
                lang_normalized = lang_raw
                for key, code in lang_map.items():
                    if key in lang_raw:
                        lang_normalized = code
                        break
                if lang_normalized and len(lang_normalized) >= 2:
                    result["language"] = lang_normalized
                break

        # ---- Год публикации ----
        # Паттерны: «Год: 2023», «2023 г.», «Год издания: 2023»
        year_patterns = [
            r"(?:год\s*(?:издания)?|publication\s*year)\s*[:\s–—-]+(\b(19|20)\d{2}\b)",
            r"\b((?:19|20)\d{2})\s*г(?:од)?\.?\b",
        ]
        for pattern in year_patterns:
            m = re.search(pattern, caption, re.IGNORECASE)
            if m:
                year_val = int(m.group(1))
                if 1900 <= year_val <= datetime.now().year + 1:
                    result["publication_year"] = year_val
                    break

        return result

    # -----------------------------------------------------------------------
    # Извлечение названия товара
    # -----------------------------------------------------------------------

    def _extract_product_name(self, caption: str, max_length: int = 200) -> str:
        """Извлекает название товара из caption с умной логикой приоритетов.

        Алгоритм:
        1. Приоритет 1: текст в кавычках «...» или "..." (часто это название книги)
        2. Приоритет 2: первая строка, не содержащая служебных слов
        3. Fallback: первые слова caption до точки
        4. Последний fallback: «Instagram Post»

        Args:
            caption: Очищенный текст поста.
            max_length: Максимальная длина названия (по умолчанию 200 символов).

        Returns:
            Название товара.
        """
        if not caption:
            return "Instagram Post"

        # Убираем хештеги и упоминания из рабочей копии текста
        text = re.sub(r"#\w+", "", caption)
        text = re.sub(r"@\w+", "", text)
        text = text.strip()

        # --- Приоритет 1: текст в кавычках ---
        # Ищем «Название» или "Название" — это обычно название книги/товара
        quote_match = re.search(r"[«\u201C](.{5,150})[»\u201D]", text)
        if quote_match:
            name = clean_text(quote_match.group(1))
            if name:
                return name[:max_length]

        # --- Приоритет 2: первая содержательная строка ---
        # «Содержательная» — не начинается со служебных слов (Цена:, Автор:, ...)
        SERVICE_PREFIXES = re.compile(
            r"^(?:цена|стоимость|автор[ы]?|издательство|isbn|страниц|переплет|"
            r"язык|год|обложка|скидк|заказ|доставк|price|author|publisher|"
            r"страниц|pages?|discount|delivery)",
            re.IGNORECASE,
        )
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if len(line) < 3:
                continue
            if SERVICE_PREFIXES.match(line):
                continue
            # Строка не должна состоять только из хештегов/цифр/эмодзи
            clean_line = re.sub(r"[^\w\s\-.,!?а-яА-ЯёЁa-zA-Z]", "", line)
            if len(clean_line.strip()) < 3:
                continue
            name = clean_text(line)
            if name:
                return name[:max_length]

        # --- Fallback: первое предложение ---
        sentences = re.split(r"[.!?]", text)
        if sentences and sentences[0].strip():
            name = clean_text(sentences[0].strip())
            if name:
                return name[:max_length]

        return "Instagram Post"

    # -----------------------------------------------------------------------
    # Извлечение медиа (ВСЕ фото и видео)
    # -----------------------------------------------------------------------

    def _extract_all_media(
        self, post: instaloader.Post
    ) -> Tuple[List[str], List[str]]:
        """Собирает ВСЕ медиафайлы из поста.

        Возвращает два отдельных списка:
        - images: URL изображений (фото + превью видео для скачивания обложек)
        - video_urls: URL видео-файлов (для поля video_url в ScrapedProduct)

        Обработка по типам постов:
        - GraphSidecar (карусель): собираем каждый слайд отдельно
        - Видео-пост: берём превью как изображение + URL видео
        - Фото-пост: одно изображение

        Args:
            post: Объект поста Instaloader.

        Returns:
            Tuple (image_urls, video_urls) — оба списка без дублей.
        """
        images: List[str] = []
        video_urls: List[str] = []

        try:
            if post.typename == "GraphSidecar":
                # --- Карусель: несколько слайдов ---
                # Каждый слайд может быть фото или видео
                for node in post.get_sidecar_nodes():
                    # display_url — это фото или превью-кадр видео.
                    # Добавляем всегда: для видео это обложка в карточке товара.
                    if hasattr(node, "display_url") and node.display_url:
                        if node.display_url not in images:
                            images.append(node.display_url)

                    # Для видео-слайдов собираем также URL видеофайла
                    if hasattr(node, "is_video") and node.is_video:
                        if hasattr(node, "video_url") and node.video_url:
                            if node.video_url not in video_urls:
                                video_urls.append(node.video_url)

            elif post.is_video:
                # --- Обычный видео-пост (Reels или обычное видео) ---
                # post.url для видео — это превью-изображение (thumbnail)
                if post.url:
                    images.append(post.url)
                # Сам видеофайл
                if post.video_url:
                    video_urls.append(post.video_url)

            else:
                # --- Обычный фото-пост ---
                if post.url:
                    images.append(post.url)

        except instaloader.exceptions.InstaloaderException:
            raise
        except ScraperAccessBlockedError:
            raise
        except Exception as e:
            self.logger.warning("Ошибка при извлечении медиа из поста: %s", e)
            # Fallback: берём хотя бы основной URL поста
            if hasattr(post, "url") and post.url:
                if post.url not in images:
                    images.append(post.url)

        return images, video_urls

    # -----------------------------------------------------------------------
    # Вспомогательные методы
    # -----------------------------------------------------------------------

    def _extract_hashtags(self, caption: str) -> List[str]:
        """Извлекает хештеги из текста поста (без символа #)."""
        if not caption:
            return []
        return re.findall(r"#(\w+)", caption)

    def _extract_username(self, url: str) -> str:
        """Извлекает username из URL профиля Instagram.

        Например: https://www.instagram.com/ummaland_books/ → ummaland_books
        """
        candidate = (url or "").strip()
        if "://" in candidate:
            parsed = urlparse(candidate)
            host = (parsed.hostname or "").lower()
            if host not in self.get_supported_domains():
                raise ValueError(f"Неподдерживаемый Instagram URL: {url}")
            path_parts = [part for part in parsed.path.split("/") if part]
            if not path_parts:
                raise ValueError("В Instagram URL не указан username профиля")
            candidate = path_parts[0]

        candidate = candidate.lstrip("@").strip("/")
        if candidate in {"p", "reel", "reels", "explore", "stories"}:
            raise ValueError(f"URL не является ссылкой на Instagram-профиль: {url}")
        if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", candidate):
            raise ValueError(f"Некорректный Instagram username: {candidate}")
        return candidate

    def _extract_hashtag(self, url: str) -> str:
        """Извлекает название хештега из URL или строки.

        Например:
            https://www.instagram.com/explore/tags/books/ → books
            #books → books
        """
        if url.startswith("#"):
            return url[1:]
        match = re.search(r"explore/tags/([^/?#]+)", url)
        if match:
            return match.group(1).rstrip("/")
        return url

    def _extract_shortcode(self, url: str) -> Optional[str]:
        """Извлекает shortcode поста из URL.

        Поддерживаемые форматы:
            https://www.instagram.com/p/ABC123xyz/
            https://www.instagram.com/reel/ABC123xyz/
            ABC123xyz (просто shortcode)
        """
        # URL поста /p/ или /reel/
        match = re.search(r"/(?:p|reel)/([A-Za-z0-9_-]+)", url)
        if match:
            return match.group(1)

        # Если передан просто shortcode (без URL)
        if re.match(r"^[A-Za-z0-9_-]+$", url):
            return url

        return None
