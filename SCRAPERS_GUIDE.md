# PharmaTurk — Полное руководство по парсерам

> Цель этого документа: дать AI-агенту или разработчику достаточно контекста,
> чтобы создать, настроить и запустить парсер для любого нового сайта или
> соцсети без дополнительных вопросов.

---

## Содержание

1. [Архитектура системы](#1-архитектура-системы)
2. [Полный путь данных](#2-полный-путь-данных)
3. [ScrapedProduct — единая структура данных](#3-scrapedproduct--единая-структура-данных)
4. [BaseScraper — базовый класс парсера](#4-basescraper--базовый-класс-парсера)
5. [Создание нового парсера — пошаговый чеклист](#5-создание-нового-парсера--пошаговый-чеклист)
6. [Регистрация парсера](#6-регистрация-парсера)
7. [Модели данных (ScraperConfig, SiteScraperTask)](#7-модели-данных)
8. [Настройка через Django Admin](#8-настройка-через-django-admin)
9. [Категории: как правильно назначить](#9-категории-как-правильно-назначить)
10. [AI-обработка после парсинга](#10-ai-обработка-после-парсинга)
11. [Медиа: загрузка в R2](#11-медиа-загрузка-в-r2)
12. [Полный пример нового парсера](#12-полный-пример-нового-парсера)
13. [Справочник: Ummaland парсер](#13-справочник-ummaland-парсер)
14. [Справочник: Instagram парсер](#14-справочник-instagram-парсер)
15. [Важные ограничения и антипаттерны](#15-важные-ограничения-и-антипаттерны)
16. [Устранение неполадок](#16-устранение-неполадок)

---

## 1. Архитектура системы

```
Сайт / Instagram
       │
       ▼
  [ParserClass]           ← наследует BaseScraper
  parse_product_list()    ← возвращает List[ScrapedProduct]
  parse_product_detail()  ← возвращает ScrapedProduct
       │
       ▼
  ScraperIntegrationService   (backend/apps/scrapers/services.py)
  ├── _create_new_product()   ← новый товар
  └── _update_existing_product() ← обновить существующий
       │
       ▼
  CatalogNormalizer            (backend/apps/catalog/services.py)
  normalize_product()
       │
       ├─ создаёт/обновляет  Product  (базовая модель)
       └─ domain_sync сигнал → BookProduct / ClothingProduct / ...
       │
       ▼
  Медиа: download_and_optimize_parsed_media()  → Cloudflare R2
       │
       ▼
  [Ручная AI-обработка через Admin]
  ├── "Полная AI обработка" → лог COMPLETED → вручную "Применить"
  └── "Полная AI обработка + авто-применение" → лог APPROVED → товар уже обновлён
```

**Ключевые принципы:**
- Парсер ТОЛЬКО собирает данные и возвращает `ScrapedProduct`. Он НЕ сохраняет в БД.
- Сохранение в БД — задача `ScraperIntegrationService`.
- AI-обработка запускается ТОЛЬКО вручную из админки (не автоматически при парсинге).
- Медиа хранятся в Cloudflare R2; в БД только URL.

---

## 2. Полный путь данных

### 2.1. Скрапинг → Product + BookProduct

```
ScrapedProduct
  │
  │ ScraperIntegrationService._create_new_product()
  │
  ▼
ProductData (dataclass-посредник)
  │
  │ CatalogNormalizer.normalize_product()
  │
  ▼
Product (базовая запись)   ←  table: catalog_product
  │ post_save signal
  │ ensure_domain_product_for_base()
  ▼
BookProduct / ClothingProduct / ...  ←  table: catalog_bookproduct / ...
  │ _sync_to_base_product() при каждом save BookProduct
  │ (синхронизирует name, price, slug и т.д. обратно в Product)
  ▼
BookProductImage / ProductImage (изображения)
```

### 2.2. Поля: кто что заполняет

| Поле | Заполняет | Примечание |
|------|-----------|------------|
| `name` | Парсер | оригинальное название |
| `description` | Парсер | исходный текст, AI потом его переводит/очищает |
| `price`, `currency` | Парсер | |
| `isbn`, `publisher`, `pages`, `cover_type`, `language` | Парсер (attributes) | для книг |
| `publication_date` | Парсер (attributes.publication_year) | AI тоже может заполнить |
| `stock_quantity` | Парсер (default=3), AI | 3 по умолчанию если не указано |
| `is_new` | ScraperIntegrationService | `True` для только что спарсенных |
| `meta_title`, `meta_description`, `meta_keywords` | AI (EN) | ПУСТЫЕ после парсинга |
| `og_title`, `og_description`, `og_image_url` | AI (EN) | ПУСТЫЕ после парсинга |
| Переводы (ru/en) | AI | текст на двух языках |
| SEO slug | Автоматически из name | |

> **Важно:** SEO/OG поля НИКОГДА не заполняются при парсинге — только AI.
> Если они заполнены не по-английски — это баг.

### 2.3. Разделение ответственности: парсеры, каталог, AI

Парсеры отдают **сырые и разнородные** данные (разные типы товаров — разные поля в `attributes`). Важно понимать, кто что делает:

| Этап | Кто | Что делает |
|------|-----|------------|
| **Сбор** | Парсер | Возвращает `ScrapedProduct`: название, описание, цена, картинки, `attributes` (словарь; у книг — isbn, publisher, у одежды — color, sizes и т.д.). Данные «как есть» с сайта/соцсети. |
| **Структурирование и сохранение** | CatalogNormalizer + ScraperIntegrationService | Преобразуют сырые данные в модели БД: создают/обновляют `Product`, по `product_type` — доменную модель (BookProduct, JewelryProduct и т.д.), **маппят** `attributes` в поля (isbn → BookProduct.isbn, publisher → BookProduct.publisher). То есть «порядок» — какой ключ куда класть — задаёт код каталога и скраперов, не AI. |
| **Обогащение контента и SEO** | AI (вручную из админки) | Работает с **уже сохранённым** товаром. Генерирует/нормализует EN-название и описание, SEO (meta_title, meta_description), переводы, OG-теги. Не решает «это книга, сохрани isbn» и не участвует в первичном маппинге атрибутов в структуру каталога. |

Итого: парсеры дают сырое и разнообразное; **приведение в структуру и первое сохранение** делают каталог и ScraperIntegrationService; AI потом наводит порядок в **текстах и SEO**, а не в маппинге атрибутов.

---

## 3. ScrapedProduct — единая структура данных

Файл: `backend/apps/scrapers/base/scraper.py`

```python
@dataclass
class ScrapedProduct:
    # Обязательно
    name: str                           # Название товара
    
    # Описание и контент
    description: str = ""              # HTML или plain text описание
    
    # Цена
    price: Optional[float] = None      # Числовое значение
    currency: str = "RUB"              # "RUB", "USD", "EUR", "TRY", "KZT"
    
    # Идентификация
    url: str = ""                      # URL страницы товара
    external_id: str = ""              # Уникальный ID товара на сайте-источнике
    sku: str = ""                      # Артикул (если есть)
    barcode: str = ""                  # Штрих-код (если есть)
    
    # Медиа
    images: List[str] = []             # Список URL изображений (главное — первое)
    
    # Категоризация (НЕ ИСПОЛЬЗУЕТСЯ для определения категории в системе)
    category: str = ""                 # Название категории на сайте-источнике
    brand: str = ""                    # Бренд
    
    # Наличие
    is_available: bool = True
    stock_quantity: Optional[int] = None  # None → система подставит 3
    
    # Дополнительные атрибуты (зависят от типа товара)
    attributes: Dict[str, Any] = {}    # Смотри раздел 3.1
    
    # Метаданные парсера
    source: str = ""                   # Имя парсера (заполняется автоматически)
    scraped_at: Optional[str] = None   # ISO datetime (заполняется автоматически)
```

### 3.1. attributes для разных типов товаров

#### Книги (product_type = "books")
```python
attributes = {
    "author": "Мансур Ладанов",         # str — один автор или несколько через запятую
    "publisher": "UMMA LAND",           # str — издательство
    "pages": 208,                       # int — количество страниц
    "isbn": "978-5-6052179-0-9",        # str — ISBN
    "cover_type": "твердый",            # str — твердый/мягкий/суперобложка
    "publication_year": 2023,           # int — год издания
    "language": "rus",                  # str — язык книги
    "age_limit": "12+",                 # str — возрастное ограничение
    "circulation": "3000",              # str — тираж
    # Медиа-атрибуты
    "video_url": "https://...",         # str — URL видео (если есть)
    "og_image": "https://...",          # str — OG изображение (сохраняется в external_data)
    "og_title": "...",                  # str — OG title (сохраняется в external_data)
}
```

#### Одежда (product_type = "clothing")
```python
attributes = {
    "color": "красный",
    "sizes": ["S", "M", "L", "XL"],
    "material": "100% хлопок",
    "gender": "женский",                # мужской / женский / унисекс
    "brand": "Zara",
}
```

#### Украшения (product_type = "jewelry")
```python
attributes = {
    "jewelry_type": "ring",             # str — ring, bracelet, necklace, earrings, pendant
    "material": "золото 585",           # str — материал
    "metal_purity": "585",              # str — проба металла
    "stone_type": "фианит",             # str — тип камня (если есть)
    "carat_weight": 0.5,                # float/Decimal — вес камней в каратах
    "gender": "женский",                # str — мужская, женская, унисекс, детская
}
```

#### Instagram-посты
```python
attributes = {
    "video_url": "https://...",         # URL видео из поста (если есть)
    "is_video": True,                   # флаг — это видео
    "likes_count": 1250,
    "comments_count": 43,
    "hashtags": ["#books", "#islam"],
    "username": "ummaland_books",
    "post_date": "2024-01-15T10:30:00",
}
```

> **Медиа в attributes:** Если есть `video_url` или `og_image` — сервис интеграции
> загружает их в R2 и сохраняет в `product.external_data["seo_data"]`.
> OG-поля (`og_title`, `og_description`) НЕ копируются напрямую на модель товара —
> только в `external_data` для последующего использования AI.

---

## 4. BaseScraper — базовый класс парсера

Файл: `backend/apps/scrapers/base/scraper.py`

### 4.1. Обязательные методы

```python
class MyParser(BaseScraper):

    def get_name(self) -> str:
        """
        Уникальное имя парсера — используется как ключ в реестре и в ScraperConfig.
        Должно быть в нижнем регистре, без пробелов.
        Примеры: "ummaland", "instagram", "zara", "myshop"
        """
        return "myshop"

    def get_supported_domains(self) -> List[str]:
        """
        Список доменов сайта (без протокола, с www и без).
        Используется для автоматического определения парсера по URL.
        """
        return ["myshop.com", "www.myshop.com"]

    def parse_product_list(
        self,
        category_url: str,
        max_pages: int = 10
    ) -> List[ScrapedProduct]:
        """
        Парсит список товаров из категории.
        
        - category_url: URL категории (из SiteScraperTask.url)
        - max_pages: лимит страниц пагинации
        - Должен возвращать пустой список [] при ошибке, не поднимать исключение
        """
        ...

    def parse_product_detail(
        self,
        product_url: str
    ) -> Optional[ScrapedProduct]:
        """
        Парсит страницу одного товара.
        
        - Вызывается для каждого URL из parse_product_list()
        - Возвращает None если страница недоступна или невалидна
        - Должен подробно заполнять все доступные attributes
        """
        ...
```

### 4.2. Вспомогательные методы BaseScraper

```python
# Выполнить HTTP GET с повторными попытками и exponential backoff
html: str = self._make_request(url)

# Получить BeautifulSoup-подобный DataSelector
page = self._parse_page(html, url)

# Логирование
self.logger.info("Парсинг страницы %s", url)
self.logger.warning("Товар без цены: %s", product_name)
self.logger.error("Ошибка запроса: %s", error)

# Задержка между запросами (настраивается в ScraperConfig)
# self.delay_range = (min, max) в секундах — уже встроено в _make_request

# HTTP клиент (httpx.Client с настроенными заголовками)
response = self.client.get(url)
response = self.client.post(url, json=data)
```

### 4.3. Утилиты для обработки данных

```python
from ..base.utils import clean_text, normalize_price, extract_currency

clean_text("<b>Название</b> товара\n\n ")  # → "Название товара"
normalize_price("1 290 руб.")             # → 1290.0
extract_currency("1 290 руб.")            # → "RUB"
extract_currency("$19.99")               # → "USD"
```

---

## 5. Создание нового парсера — пошаговый чеклист

### Шаг 1: Создать файл парсера

Путь: `backend/apps/scrapers/parsers/{имя_сайта}.py`

Минимальный шаблон:

```python
"""Парсер для MySite.com."""

import logging
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup

from ..base.scraper import BaseScraper, ScrapedProduct
from ..base.utils import clean_text, normalize_price, extract_currency


class MySiteParser(BaseScraper):
    """Парсер для сайта MySite.com."""

    def get_name(self) -> str:
        return "mysite"

    def get_supported_domains(self) -> List[str]:
        return ["mysite.com", "www.mysite.com"]

    def parse_product_list(
        self, category_url: str, max_pages: int = 10
    ) -> List[ScrapedProduct]:
        products = []
        page = 1

        while page <= max_pages:
            # Формируем URL страницы пагинации
            url = f"{category_url}?page={page}"
            html = self._make_request(url)
            if not html:
                break

            soup = BeautifulSoup(html, "html.parser")
            items = soup.select(".product-card")
            if not items:
                break

            for item in items:
                try:
                    product_url = item.select_one("a")["href"]
                    detail = self.parse_product_detail(product_url)
                    if detail:
                        products.append(detail)
                except Exception as e:
                    self.logger.warning("Пропуск товара: %s", e)

            page += 1

        return products

    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        html = self._make_request(product_url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        try:
            name = clean_text(soup.select_one("h1.product-title").text)
            description = clean_text(soup.select_one(".product-description").text)
            price_text = soup.select_one(".price").text
            images = [
                img["src"]
                for img in soup.select(".product-gallery img")
                if img.get("src")
            ]

            # Извлекаем external_id из URL (уникальный идентификатор)
            external_id = product_url.rstrip("/").split("/")[-1]

            return ScrapedProduct(
                name=name,
                description=description,
                price=normalize_price(price_text),
                currency=extract_currency(price_text),
                url=product_url,
                images=images,
                external_id=external_id,
                is_available=True,
                stock_quantity=None,  # система подставит 3
                source=self.get_name(),
                attributes={
                    # Специфичные поля — для книг:
                    # "author": ...,
                    # "publisher": ...,
                    # "pages": ...,
                    # "isbn": ...,
                    # "cover_type": ...,
                    # "publication_year": ...,
                },
            )
        except Exception as e:
            self.logger.error("Ошибка парсинга %s: %s", product_url, e)
            return None
```

### Шаг 2: Зарегистрировать парсер

В файле `backend/apps/scrapers/parsers/registry.py` добавить в функцию `register_default_parsers()`:

```python
def register_default_parsers():
    """Регистрирует парсеры по умолчанию."""
    try:
        from .ilacabak import IlacabakParser
        from .zara import ZaraParser
        from .instagram import InstagramParser
        from .ummaland import UmmalandParser
        from .mysite import MySiteParser          # ← добавить

        _registry.register(IlacabakParser)
        _registry.register(ZaraParser)
        _registry.register(InstagramParser)
        _registry.register(UmmalandParser)
        _registry.register(MySiteParser)          # ← добавить
        _registry.register(IlacFiyatiParser)      # ← добавить
    except ImportError as e:
        logging.getLogger(__name__).warning(f"Не удалось импортировать парсеры: {e}")
```

### Шаг 3: Создать ScraperConfig в Admin

Перейти в `/admin/scrapers/scraperconfig/` → Добавить:

| Поле | Значение |
|------|----------|
| **Name** | `mysite` ← точно как `get_name()` |
| **Base URL** | `https://mysite.com` |
| **Parser class** | `mysite` |
| **Is enabled** | ✅ |
| **Delay min** | `1.0` (секунды между запросами) |
| **Delay max** | `3.0` |
| **Max pages per run** | `50` (или нужное число) |
| **Max products per page** | `100` |

### Шаг 4: Создать SiteScraperTask в Admin

Перейти в `/admin/scrapers/sitescrapertask/` → Добавить:

| Поле | Значение |
|------|----------|
| **Scraper config** | `mysite` (выбрать из списка) |
| **URL** | `https://mysite.com/category/books` ← URL категории |
| **Target category** | Выбрать категорию из каталога (например: "Книги") |
| **Max pages** | `10` |
| **Max products** | `100` |
| **Is active** | ✅ |

> **Важно: Target category** — обязательное поле! Без него товары не попадут
> в нужный раздел. Категория должна уже существовать в каталоге.

### Шаг 5: Запустить парсинг

Через Admin: `/admin/scrapers/sitescrapertask/` → выбрать задачу → Action: "Запустить выбранные задачи".

Или вручную из Django shell:
```python
from apps.scrapers.tasks import run_scraper_task
run_scraper_task.delay(task_id=1)
```

---

## 6. Регистрация парсера

### 6.1. Файл реестра

`backend/apps/scrapers/parsers/registry.py`

Реестр хранит маппинг: `{имя_парсера: КлассПарсера}` и `{домен: имя_парсера}`.

При запуске задачи `ScraperIntegrationService` ищет парсер:
1. По имени из `ScraperConfig.name`
2. По домену из URL задачи

### 6.2. Как происходит поиск парсера

```python
# В services.py:
parser_class = get_parser(config.name)  # → по имени из ScraperConfig
# или
parser_class = get_parser(task.url)    # → по домену из URL
```

Если парсер не найден — задача завершится с ошибкой.

### 6.3. Доступные парсеры

| Имя | Класс | Домены |
|-----|-------|--------|
| `ummaland` | `UmmalandParser` | ummaland.com, umma-land.com |
| `instagram` | `InstagramParser` | instagram.com, www.instagram.com |
| `zara` | `ZaraParser` | zara.com, tr.zara.com, ru.zara.com |
| `ilacabak` | `IlacabakParser` | ilacabak.com, www.ilacabak.com |
| `ilacfiyati` | `IlacFiyatiParser` | ilacfiyati.com, www.ilacfiyati.com |
| `ikea` | `IkeaParser` | ikea.com.tr, www.ikea.com.tr |
| `lcw` | `LcwParser` | lcw.com, www.lcw.com |

### 6.4. IKEA Turkey (`ikea.com.tr`)

Парсер `IkeaParser` ходит во внутренний API (`IkeaService`).

**Начальный URL в задаче (`SiteScraperTask.start_url`):**

| Режим | Примеры URL |
|-------|-------------|
| Категория (листинг) | `https://www.ikea.com.tr/en/category/four-seats`, `https://www.ikea.com.tr/kategori/...` |
| Одна карточка товара | `https://www.ikea.com.tr/urun/slug-80275887` **или** `https://www.ikea.com.tr/en/product/slug-39440475` |

Артикул для API — **8 цифр** в конце слага (поддерживаются и `/urun/`, и английский `/en/product/`).

**Категория и подкатегория в задаче:** в админке у `SiteScraperTask` можно задать **целевую категорию** и **подкатегорию**. При запуске через Celery в сессию подставляется категория с **наивысшим приоритетом: `target_subcategory`, если заполнена, иначе `target_category`**. Товары сохраняются в выбранную запись каталога (slug подкатегории уходит в маппинг как у обычной категории).

**Мебель и цветовые варианты:** при парсинге **листинга** и **одной ссылки** собираются все цвета из `colorOptions` API; в `attributes` передаётся `furniture_variants`, по ним создаются записи `FurnitureVariant` и галереи вариантов. В листинге несколько `sprCode` одной модели не порождают дубликаты карточек — учитывается одно «семейство» вариантов.

**Бренд:** в `ScraperConfig` доступно поле **`default_brand`** (миграция `scrapers.0012_scraperconfig_default_brand`). Если задано, оно имеет приоритет над строкой бренда из парсера; для IKEA без поля в конфиге по-прежнему подставляется `IKEA` из кода парсера.

---

### 6.5. LC Waikiki (`lcw.com`)

Парсер `LcwParser` уже встроен в проект и зарегистрирован в реестре. Для команды это **эталонный parser blueprint**: если мы делаем новый парсер для fashion / accessories / shoes / headwear / underwear / похожего e-commerce сайта, сначала ориентируемся именно на LCW и повторяем его паттерны, а не пишем упрощённую версию “на коленке”.

#### Почему именно LCW считаем прототипом

LCW покрывает почти весь “боевой” функционал, который нам нужен от современных товарных парсеров:
- работа и по листингу, и по одной карточке, и по поиску
- надёжное различение URL категории и URL товара
- сбор **семейства вариантов** (цвета/модификации) в одну карточку товара
- размеры и остатки по вариантам
- качественное описание с очисткой от навигационного мусора
- фильтрация галереи и борьба с ложными preview-изображениями
- fallback-логика: сначала богатый разбор DOM, потом regex fallback
- стабильные `external_id` для base product и для variant rows
- тесты на реальные edge cases, а не только happy path

Если новый сайт похож на LCW по структуре, новый парсер должен повторять эту архитектуру максимально близко.

#### Начальный URL в задаче (`SiteScraperTask.url`)

| Режим | Примеры URL |
|-------|-------------|
| Категория (листинг) | `https://www.lcw.com/t-shirt-t-590`, `https://www.lcw.com/erkek-polo-yaka-tisort-t-8` |
| Одна карточка товара | `https://www.lcw.com/polo-yaka-erkek-triko-tisort-siyah-o-4823160` |
| Поиск | `https://www.lcw.com/arama?q=polo%20yaka%20tisort` |

#### Как LCW определяется технически

- карточка товара: URL содержит шаблон `-o-<id>`
- категория/листинг: URL содержит шаблон `-t-<id>`
- магазин/навигационные страницы исключаются отдельно (`/magaza/`)

Это важный принцип и для других сайтов: **сперва формализуем типы URL регулярками / детекторами**, и только потом пишем парсинг. Не наоборот.

#### Архитектура LCW-парсера

Файл: `backend/apps/scrapers/parsers/lcw.py`

Ключевые публичные методы:
- `get_name()` → имя парсера (`lcw`)
- `get_supported_domains()` → домены
- `parse_categories()` → сбор категорий по сайту
- `parse_product_list()` → листинг / категория / поиск
- `parse_product_detail()` → одна карточка товара
- `search_products()` → частный случай листинга по поисковому URL

Ключевые внутренние блоки:
- `_is_product_url()` / `_is_category_url()` — типизация URL
- `_parse_single_variant()` — разбор **одной** страницы варианта
- `_parse_product_group()` — сбор нескольких цветовых вариантов в один `ScrapedProduct`
- `_variant_payload_from_parsed()` — канонический payload варианта
- `_extract_description_from_soup()` / `_build_rich_description()` — многоступенчатая сборка описания
- `_extract_images()` — очистка и валидация галереи
- `_extract_sizes()` — размеры и остатки
- `_build_group_external_id()` / `_build_family_key()` — дедупликация и стабилизация family/group identity

#### Какой data contract LCW формирует

LCW возвращает **один** `ScrapedProduct` на семейство вариантов, а не по одной записи на цвет. Это критично.

Обязательные поля:
- `name`
- `price`
- `currency`
- `url`
- `external_id` — base/group id (`lcw-...`)
- `category`
- `brand`
- `description`
- `images`
- `source`

Ключевые `attributes`:
- `fashion_variants` — список вариантов
- `variant_group_id` — стабильный family id
- `group_sku`
- `color`
- `og_image_url`
- сырые характеристики из блока `Ürün İçeriği ve Özellikleri`

Типичный payload варианта:

```python
{
    "external_id": "lcw-var-5044153",
    "sort_order": 0,
    "color": "Lacivert",
    "display_name": "LCW ACCESSORIES Lacivert LA Nakışlı Erkek Kep Şapka - S6CT56Z8-CRP",
    "price": 299.99,
    "currency": "TRY",
    "external_url": "https://www.lcw.com/...",
    "images": [...],
    "stock_quantity": 1000,
    "is_available": True,
    "sizes": [
        {"size": "S", "stock_quantity": 1000, "is_available": True},
        {"size": "M", "stock_quantity": 0, "is_available": False},
    ],
    "sku": "S6CT56Z8-CRP",
}
```

#### Поток выполнения: как LCW работает end-to-end

1. `parse_product_list()` обходит ссылки листинга.
2. Для каждой ссылки сначала быстро определяет, является ли она карточкой товара.
3. Для первого найденного URL товара тянет detail HTML и пытается построить `family_key`.
4. Если это уже виденное семейство, запись пропускается.
5. Иначе вызывает `_parse_product_group()`.
6. `_parse_product_group()`:
   - парсит текущий вариант,
   - вытаскивает ссылки на sibling color variants,
   - ограничивает их `MAX_VARIANTS_PER_PRODUCT`,
   - собирает payload каждого варианта,
   - вычисляет `variant_group_id`,
   - формирует единый `ScrapedProduct`.
7. Дальше `ScraperIntegrationService` уже превращает `fashion_variants` в доменные записи каталога.

Это главный принцип для будущих парсеров одежды/обуви/аксессуаров:
**если сайт хранит товар как семейство вариантов, парсер должен возвращать семейство, а не случайный одиночный вариант**.

#### Какие edge cases LCW уже закрывает

1. **Одинаковое семейство встречается в листинге несколько раз**  
   Парсер дедуплицирует по `family_key`, `variant_group_id`, variant URLs.

2. **Варианты не видны в DOM как ссылки, но лежат в embedded JSON**  
   Парсер умеет подхватывать и такой сценарий.

3. **Некоторые размеры disabled / out of stock**  
   Они сохраняются с `stock_quantity=0`, а не теряются.

4. **На странице много навигационного мусора**  
   `_looks_like_navigation_dump()` отсекает “текст”, который на самом деле является menu dump.

5. **OG preview и реальная галерея конфликтуют**  
   Парсер не берёт любую картинку подряд, а фильтрует по шаблонам реальной product gallery.

6. **Ложные preview чужих вариантов**  
   Галерея очищается от изображений, относящихся к другим sibling-variant SKU.

7. **Описание разбросано по нескольким блокам**  
   Сначала пробуем rich DOM parse, если не вышло — идём в regex fallback.

8. **На листинге есть только урезанные данные**  
   Есть `_build_list_product()` как деградационный сценарий, если detail parse временно не дал результат.

#### Что обязательно повторять в новых парсерах

Если новый сайт похож на fashion e-commerce, новый парсер должен брать у LCW следующие обязательные паттерны:

1. **Разделять parse одного варианта и parse семейства вариантов**  
   То есть аналог `_parse_single_variant()` и `_parse_product_group()`.

2. **Иметь строгие детекторы URL**  
   Аналоги `is_lcw_product_url()` и `is_lcw_category_url()`.

3. **Иметь стабильную схему identity**  
   Отдельно:
   - `external_id` base product
   - `external_id` варианта
   - `family_key` / `variant_group_id`

4. **Собирать варианты в `attributes["fashion_variants"]`**  
   Это текущий контракт со слоем интеграции каталога.

5. **Описывать fallback-стратегии прямо в коде**  
   Не надеяться, что сайт всегда отдаёт идеальный DOM.

6. **Фильтровать галерею и шум**  
   Картинки, текст и размеры должны проходить валидацию, а не сохраняться “как попало”.

7. **Использовать централизованный турецкий vocabulary**  
   Цвета, оттенки и базовые товарные термины (`beyaz`, `lacivert`, `spor ayakkabi`, `çanta`, `gömlek`) должны нормализоваться через единый словарь, а не через локальные таблицы в каждом новом парсере.

8. **Не тратить LLM на простые variant titles**  
   Если вариант отличается только цветом или объёмом, имя варианта должно собираться rule-based от базовой модели (`parent title + color/volume`), а не через отдельный AI вызов.

7. **Покрывать edge cases тестами**  
   Для каждого нового парсера нужны не только happy path тесты, но и минимум:
   - дубликаты семейства
   - пропавшие DOM links
   - disabled sizes
   - preview/foreign gallery contamination
   - navigation dump в description

#### Что НЕ надо копировать слепо из LCW

LCW — это прототип по архитектуре, но не по строковым эвристикам один-в-один.

Не надо бездумно переносить:
- турецкие маркеры текста (`Ürün Açıklaması`, `Ürün İçeriği ve Özellikleri`)
- regex под конкретный HTML LCW
- URL-шаблоны CDN LCW
- логику цветов/размеров без адаптации к новому сайту

Нужно копировать:
- разбиение ответственности
- структуру pipeline
- подход к variant families
- fallback design
- валидацию noisy data
- использование общего словаря `tr -> ru/en` для цветов и товарных терминов

#### Минимальный чеклист “новый парсер как LCW”

Перед merge нового парсера проверь:
- умеет ли он парсить и list, и detail
- умеет ли он возвращать family variants в одном `ScrapedProduct`
- стабилен ли `external_id`
- не создаёт ли дубли по sibling variants
- умеет ли сохранять disabled / out-of-stock размеры
- умеет ли чистить галерею
- умеет ли чистить description от навигации/шума
- не дублирует ли локально словари цветов / товарных терминов, если это уже есть в `backend/apps/catalog/utils/tr_vocab.py`
- не запускает ли variant AI там, где достаточно `base product + color`
- есть ли отдельные тесты на edge cases
- задокументирован ли его contract в этом гайде

#### Общий vocabulary для TR -> RU/EN

Для fashion/accessories/shoes/headwear/underwear парсерный слой должен использовать единый словарь:

- файл: `backend/apps/catalog/utils/tr_vocab.py`
- цвета и оттенки: `translate_turkish_color(...)`
- базовые товарные термины: `translate_turkish_product_term(...)`
- общий normalize helper: `normalize_ascii_text(...)`

Это нужно, чтобы:

- `beyaz` всегда становился `Белый / White`, а не в одном месте `Белый`, а в другом `Светлый`
- `spor ayakkabi` всегда нормализовался как `Кроссовки / Sneakers`
- category inference, variant titles, parser normalization и dynamic attributes говорили на одном языке

Если новому сайту нужны новые TR-токены, их добавляют в `tr_vocab.py`, а не в ad-hoc словарь внутри парсера.

#### Стратегия названий вариантов

По умолчанию variant names не требуют отдельного LLM-вызова.

Текущее правило проекта:

- если вариант отличается только цветом, имя строится как `base product + color`
- если вариант отличается цветом и/или объёмом, используется дешёвая rule-based нормализация
- отдельный variant AI нужен только если у варианта есть собственные содержательные данные:
  - отдельное описание
  - отдельные материалы / dimensions / cover_type / format_type
  - variant-specific snapshot из парсера

Практически это означает:

- парсер должен стараться сохранить `color` и другие variant-axis поля как структурированные данные
- не нужно плодить токены на `Beyaz`, `Siyah`, `Lacivert` и другие простые варианты
- quality bar для variant payload выше, чем для variant prose: сначала структура, потом уже AI

#### Практическая настройка в админке

1. Создать `ScraperConfig` с именем `lcw`
2. Указать `Base URL` = `https://www.lcw.com`
3. Включить конфиг (`Is enabled`)
4. В `SiteScraperTask` указать ссылку на категорию, поиск или карточку товара
5. Обязательно выбрать `target_category` или ещё лучше `target_subcategory`

**Важно по категории:** LCW сам может вернуть строку внешней категории, но надёжнее задавать целевую категорию руками в `SiteScraperTask`, чтобы товары сразу сохранялись в нужный домен каталога.

#### Тесты LCW — обязательная часть прототипа

Файл: `backend/apps/scrapers/test_lcw_parser.py`

LCW считается эталоном ещё и потому, что его тесты фиксируют реальное поведение:
- URL detection
- parse product detail
- parse product list
- дедупликация семейства
- disabled sizes
- embedded variants JSON
- navigation dump detection
- очистка галереи от мусора / foreign previews

Для каждого нового “эталонного” парсера уровень покрытия должен быть не ниже, чем у LCW.

---

## 7. Модели данных

### 7.1. ScraperConfig — конфигурация парсера

Файл: `backend/apps/scrapers/models.py`

```python
class ScraperConfig(models.Model):
    name = CharField(max_length=100)          # имя парсера = get_name()
    base_url = URLField()                      # базовый URL сайта
    is_enabled = BooleanField(default=True)
    delay_min = FloatField(default=1.0)        # мин. задержка между запросами (сек)
    delay_max = FloatField(default=3.0)        # макс. задержка
    max_pages_per_run = IntegerField(default=50)
    max_products_per_page = IntegerField(default=100)
    username = CharField(...)                  # логин (для сайтов с авторизацией)
    password = CharField(...)                  # пароль
    default_category = ForeignKey(Category)   # категория по умолчанию (резерв)
    category_mapping = JSONField(default=dict) # маппинг URL-категорий → категории
    extra_settings = JSONField(default=dict)   # любые доп. настройки
```

### 7.2. ScrapingSession — сессия парсинга

```python
class ScrapingSession(models.Model):
    config = ForeignKey(ScraperConfig)
    target_category = ForeignKey(Category, null=True)  # категория для ВСЕЙ сессии
    status = CharField(...)   # pending / running / completed / failed
    started_at = DateTimeField()
    completed_at = DateTimeField(null=True)
    products_found = IntegerField(default=0)
    products_created = IntegerField(default=0)
    products_updated = IntegerField(default=0)
```

### 7.3. SiteScraperTask — задача парсинга URL

```python
class SiteScraperTask(models.Model):
    config = ForeignKey(ScraperConfig)
    url = URLField()                              # URL категории для парсинга
    target_category = ForeignKey(Category, null=True)  # ← ГЛАВНОЕ ПОЛЕ для категории
    max_pages = IntegerField(default=10)
    max_products = IntegerField(null=True)
    is_active = BooleanField(default=True)
    last_run = DateTimeField(null=True)
    status = CharField(...)  # pending / running / completed / failed
```

> **target_category** — основной способ назначить категорию. Если задан,
> все товары из этой задачи попадут именно в эту категорию.
> Приоритет категорий: `task.target_category` > `session.target_category` >
> `config.category_mapping` > `config.default_category`.

### 7.4. ScrapedProductLog — лог спарсенного товара

```python
class ScrapedProductLog(models.Model):
    session = ForeignKey(ScrapingSession)
    task = ForeignKey(SiteScraperTask, null=True)
    product = ForeignKey(Product, null=True)   # созданный/обновлённый товар
    url = URLField()
    status = CharField(...)  # created / updated / skipped / error
    created_at = DateTimeField()
    error_message = TextField(null=True)
```

---

## 8. Настройка через Django Admin

### 8.1. Полный процесс настройки нового парсера

1. **ScraperConfig** (`/admin/scrapers/scraperconfig/add/`)
   - `Name` = имя парсера (совпадает с `get_name()`)
   - `Base URL` = базовый URL
   - `Is enabled` = ✅
   - Задержки, лимиты страниц/товаров
   - Логин/пароль если сайт требует авторизацию

2. **Категория** — убедиться что в каталоге существует нужная категория
   (`/admin/catalog/category/`)

3. **SiteScraperTask** (`/admin/scrapers/sitescrapertask/add/`)
   - Привязать к конфигу
   - Указать URL категории
   - **Обязательно выбрать `Target category`**
   - Задать лимиты

4. **Запуск** — из списка задач выбрать нужные → Action → "Запустить выбранные задачи"

### 8.2. Просмотр результатов

- Сессии: `/admin/scrapers/scrapingsession/` — статус, количество товаров
- Логи товаров: `/admin/scrapers/scrapedproductlog/` — что создано/обновлено/ошибки
- Логи AI: `/admin/ai/aiprocessinglog/` — статус обработки

### 8.3. Category mapping (альтернатива target_category)

Если на сайте несколько категорий, можно задать маппинг в `ScraperConfig.category_mapping`:

```json
{
    "https://mysite.com/category/books": "Книги",
    "https://mysite.com/category/clothing": "Одежда",
    "https://mysite.com/category/electronics": "Электроника"
}
```

Ключ — URL категории сайта, значение — название категории в нашей системе.

> Если при этом у `SiteScraperTask` заданы категории, приоритет такой:
> **`target_subcategory` → `target_category`** — выше, чем `category_mapping`
> и `default_category` у конфига (см. также раздел 6.4 про IKEA).

---

## 9. Категории: как правильно назначить

### 9.1. Важные правила

1. **Категория определяет тип товара (product_type)**. Книги в категории "Книги"
   получат `product_type="books"` и будут сохранены в таблицу `BookProduct`.
   Одежда → `ClothingProduct`. Электроника → `ElectronicsProduct`.

2. **Категория НЕ определяется автоматически** при парсинге. Её должен выбрать
   администратор через `target_category` в `SiteScraperTask`.

3. `ScrapedProduct.category` (строка с названием категории на сайте-источнике)
   используется только для поиска совпадения с `category_mapping`. Это вторичный
   механизм — полагайтесь на `target_category`.

### 9.2. Маппинг category → product_type

| Slug категории | product_type | Доменная модель |
|----------------|--------------|-----------------|
| `books` | `books` | `BookProduct` |
| `clothing` | `clothing` | `ClothingProduct` |
| `shoes` | `shoes` | `ShoeProduct` |
| `electronics` | `electronics` | `ElectronicsProduct` |
| `jewelry` | `jewelry` | `JewelryProduct` |
| `furniture` | `furniture` | `FurnitureProduct` |
| `medicines` | `medicines` | `MedicineProduct` |

### 9.3. Поля специфичные для книг (BookProduct)

Для корректного заполнения книжных полей парсер должен вернуть в `attributes`:

```python
attributes = {
    "author": "Имя Автора",         # → ProductAuthor (связь с Author)
    "publisher": "Издательство",    # → BookProduct.publisher
    "pages": 208,                   # → BookProduct.pages
    "isbn": "978-...",              # → BookProduct.isbn
    "cover_type": "твердый",        # → BookProduct.cover_type
    "publication_year": 2023,       # → BookProduct.publication_date (1 января года)
    "language": "rus",              # → BookProduct.language
}
```

### 9.4. Расширение: добавление новой категории товаров

Чтобы парсить новый тип товаров (одежда, обувь, украшения и т.д.) и корректно сохранять их в доменные модели (ClothingProduct, ShoeProduct, JewelryProduct), делают по шагам ниже. Подход в коде — **расширяемый через реестры** (один маппинг категория→product_type, реестр sync-обработчиков в каталоге, реестры getter/attribute-handler в скраперах). Так можно добавлять типы без правок старых `if/elif`.

**Чеклист добавления новой категории (например, jewelry, clothing, shoes):**

1. **Документация (этот гайд)**  
   В разделе 3.1 «attributes для разных типов товаров» описать формат `attributes` для нового типа (какие ключи → какие поля доменной модели).

2. **Маппинг категория → product_type**  
   В коде каталога (константы или `resolve_category_and_product_type`) добавить slug категории и при необходимости алиасы названий (например `"украшения"` → `jewelry`). Тогда при выборе `target_category` с этим slug товарам будет выставляться нужный `product_type` и создаваться правильная доменная модель.

3. **CatalogNormalizer (sync из metadata)**  
   Реализовать обработчик «сырые attributes → поля доменной модели» (например `_sync_jewelry_metadata(product, attrs)`) и зарегистрировать его в реестре `_SYNC_METADATA_HANDLERS[product_type]`. Вызов идёт из `_sync_product_fields_from_metadata` при любом нормалайзе (в т.ч. не только из скраперов).

4. **ScraperIntegrationService**  
   - Реализовать «найти или создать доменный объект» (например `_get_jewelry_product(product)`) и зарегистрировать в `_DOMAIN_GETTERS[product_type]`.  
   - Реализовать обновление атрибутов из парсера (например `_update_jewelry_attributes(product, attrs)`) и зарегистрировать в `_ATTRIBUTE_UPDATE_HANDLERS[product_type]`.  
   - Если для типа нужно особое правило (например, обнулять бренд только у книг) — добавить тип в соответствующий набор (например `BRAND_CLEAR_PRODUCT_TYPES`).

5. **Проверка AI и domain_sync**  
   В `domain_sync` и в админке AI маппинг `product_type` → доменная модель обычно уже есть для всех типов из `Product.PRODUCT_TYPE_CHOICES`. При необходимости убедиться, что новый тип там присутствует и AI-обработка открывается для этой доменной модели.

**Как расширять дальше: по плану с реестрами или по «чистой архитектуре»?**

- **Сейчас и в ближайшей перспективе** — расширять **по плану с реестрами**: один маппинг категория→product_type, два слоя реестров (каталог: sync-handlers; скраперы: domain-getters и attribute-handlers). Это не костыль: добавление типа = новые handler’ы и регистрация, без размазывания `if/elif` по коду.
- **Опционально позже** — можно эволюционно перейти к **чистой архитектуре**: ввести один интерфейс (например `ProductTypeHandler` с методами sync_metadata, get_or_create_domain, update_attributes) и один реестр таких обработчиков; каталог и скраперы будут только вызывать этот интерфейс. Тогда «два реестра» сольются в один контракт. Реализовывать это имеет смысл, когда типов станет много или появятся новые источники данных (не только скраперы), которым нужна та же логика по типам.

---

## 10. AI-обработка после парсинга

### 10.1. Принцип: AI запускается ТОЛЬКО вручную

После парсинга товары находятся в состоянии:
- Описание: оригинальный текст (может быть на любом языке)
- SEO поля: **пустые** (meta_title, meta_description и т.д.)
- Переводы: **нет**
- OG поля: **пустые**

AI-обработка запускается вручную из `/admin/catalog/bookproduct/` (или другой
доменной модели).

### 10.2. Два режима запуска AI

**Вариант А: "Полная AI обработка" (без авто-применения)**
- Создаёт лог со статусом `Завершено`
- Результаты доступны в `/admin/ai/aiprocessinglog/`
- Нужно вручную нажать "Применить" для обновления товара
- Используется для ревью перед применением

**Вариант Б: "Полная AI обработка + авто-применение"**
- Применяет результаты сразу автоматически
- Лог получает статус `Одобрено`
- Товар обновляется без ручного вмешательства
- Удобно для пакетной обработки проверенных товаров

### 10.3. Что заполняет AI

AI анализирует изображения товара и имеющийся текст, затем заполняет:

| Поле | Описание |
|------|----------|
| `BookProduct.meta_title` | SEO заголовок на английском |
| `BookProduct.meta_description` | SEO описание на английском |
| `BookProduct.meta_keywords` | Ключевые слова на английском |
| `BookProduct.og_title` | OpenGraph заголовок (EN) |
| `BookProduct.og_description` | OpenGraph описание (EN) |
| `BookProduct.og_image_url` | URL главного изображения |
| `BookProduct.cover_type` | Тип обложки (если не было) |
| `BookProduct.language` | Язык книги (если не было) |
| `BookProduct.publication_date` | Дата публикации (если не было) |
| `BookProduct.stock_quantity` | Устанавливает 3 если пустое |
| Перевод RU | Очищенное описание на русском |
| Перевод EN | Перевод на английский |

### 10.4. Просмотр логов AI

`/admin/ai/aiprocessinglog/` — таблица с логами:
- **Завершено** — ждёт ручного "Применить"
- **Одобрено** — уже применено (через авто-применение или вручную)
- **Провалено** — ошибка при обработке или применении
- **Модерация** — требует ревью (низкое качество результата)

---

## 11. Медиа: загрузка в R2

### 11.1. Как медиа обрабатываются

Парсер возвращает URLs изображений → `ScraperIntegrationService` скачивает их
через `download_and_optimize_parsed_media()` и сохраняет в Cloudflare R2.

В БД хранится только URL в R2.

### 11.2. Путь хранения медиа

```
R2 bucket → products/parsed/{parser_name}/images/{external_id}-{index}-{hash}.{ext}
```

Пример: `products/parsed/ummaland/images/ummaland-2592-0-bbd79f519d59.png`

### 11.3. Лимит изображений

По умолчанию AI обрабатывает до **5 изображений** за раз.
Парсер может вернуть сколько угодно изображений — все они сохраняются в
`BookProductImage`.

### 11.4. Видео

Если у товара есть видео (Instagram Reels, YouTube и т.д.):
- URL видео помещается в `attributes["video_url"]`
- Для Instagram видео скачивается в R2 через `main_video_file`

### 11.5. Предотвращение дублирования

Если URL уже указывает на R2 (`r2.dev`, CDN URL из settings), файл **не скачивается**
повторно — используется существующий путь.

---

## 12. Полный пример нового парсера

Пример реального парсера для книжного магазина на WooCommerce:

```python
"""Парсер для IslamBooks.ru."""

import re
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup

from ..base.scraper import BaseScraper, ScrapedProduct
from ..base.utils import clean_text, normalize_price, extract_currency


class IslamBooksParser(BaseScraper):
    """Парсер для сайта IslamBooks.ru (WooCommerce)."""

    def get_name(self) -> str:
        return "islambooks"

    def get_supported_domains(self) -> List[str]:
        return ["islambooks.ru", "www.islambooks.ru"]

    def parse_product_list(
        self, category_url: str, max_pages: int = 10
    ) -> List[ScrapedProduct]:
        products = []
        page = 1

        while page <= max_pages:
            url = category_url if page == 1 else f"{category_url}page/{page}/"
            html = self._make_request(url)
            if not html:
                break

            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select("ul.products li.product")

            if not cards:
                self.logger.info("Нет товаров на странице %d, завершаем", page)
                break

            for card in cards:
                link = card.select_one("a.woocommerce-LoopProduct-link")
                if not link:
                    continue
                product_url = link.get("href", "")
                if not product_url:
                    continue

                detail = self.parse_product_detail(product_url)
                if detail:
                    products.append(detail)
                    self.logger.info("Спарсен: %s", detail.name)

            page += 1

        return products

    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        html = self._make_request(product_url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        try:
            # Название
            name = clean_text(
                soup.select_one("h1.product_title").text
            )

            # Описание
            desc_el = soup.select_one("div.woocommerce-product-details__short-description")
            description = clean_text(desc_el.text) if desc_el else ""

            # Полное описание
            full_desc_el = soup.select_one("#tab-description")
            if full_desc_el and len(full_desc_el.text) > len(description):
                description = clean_text(full_desc_el.text)

            # Цена
            price_el = soup.select_one("p.price .woocommerce-Price-amount")
            price = normalize_price(price_el.text) if price_el else None
            currency = extract_currency(price_el.text) if price_el else "RUB"

            # Изображения
            images = []
            gallery = soup.select("figure.woocommerce-product-gallery__image a")
            for img_link in gallery:
                href = img_link.get("href")
                if href and href.startswith("http"):
                    images.append(href)
            # Если нет галереи — основное изображение
            if not images:
                main_img = soup.select_one(".woocommerce-product-gallery__image img")
                if main_img:
                    src = main_img.get("data-large_image") or main_img.get("src")
                    if src:
                        images.append(src)

            # external_id из URL (WooCommerce использует ЧПУ slugs)
            slug = product_url.rstrip("/").split("/")[-1]

            # Характеристики из таблицы
            attributes = {}
            table = soup.select("table.woocommerce-product-attributes tr")
            attr_map = {
                "автор": "author",
                "издательство": "publisher",
                "количество страниц": "pages",
                "isbn": "isbn",
                "переплет": "cover_type",
                "год издания": "publication_year",
                "язык": "language",
            }
            for row in table:
                label_el = row.select_one("th")
                value_el = row.select_one("td")
                if not label_el or not value_el:
                    continue
                label = label_el.text.strip().lower()
                value = clean_text(value_el.text)
                for ru_key, en_key in attr_map.items():
                    if ru_key in label:
                        if en_key == "pages":
                            try:
                                attributes[en_key] = int(re.sub(r"\D", "", value))
                            except ValueError:
                                pass
                        elif en_key == "publication_year":
                            try:
                                attributes[en_key] = int(re.sub(r"\D", "", value))
                            except ValueError:
                                pass
                        else:
                            attributes[en_key] = value
                        break

            return ScrapedProduct(
                name=name,
                description=description,
                price=price,
                currency=currency,
                url=product_url,
                images=images,
                external_id=slug,
                is_available=bool(soup.select_one(".in-stock")),
                stock_quantity=None,  # система подставит 3
                attributes=attributes,
            )

        except Exception as e:
            self.logger.error("Ошибка парсинга %s: %s", product_url, e)
            return None
```

---

## 13. Справочник: Ummaland парсер

**Файл:** `backend/apps/scrapers/parsers/ummaland.py`
**Имя:** `ummaland`
**Домены:** `ummaland.com`, `umma-land.com`

### Особенности

- Использует внутренний WordPress REST API: `GET /wp-json/filters/products/?category=<id>`
- Сначала получает список товаров из API (быстро, без пагинации),
  затем для каждого парсит детальную страницу
- Извлекает все галерейные изображения и видео
- Берёт характеристики из HTML-таблицы на странице товара

### Извлекаемые поля

| attributes-ключ | Источник на странице |
|-----------------|----------------------|
| `author` | Таблица характеристик "Автор" |
| `publisher` | Таблица "Издательство" |
| `pages` | Таблица "Количество страниц" |
| `isbn` | Таблица "ISBN" |
| `cover_type` | Таблица "Переплёт" |
| `publication_year` | Таблица "Год издания" |
| `language` | Таблица "Язык" |
| `og_image` | `<meta property="og:image">` |
| `og_title` | `<meta property="og:title">` |

### Конфигурация в Admin

```
ScraperConfig:
  Name: ummaland
  Base URL: https://umma-land.com
  Delay min: 0.5
  Delay max: 2.0

SiteScraperTask:
  URL: https://umma-land.com/product-category/books
  Target category: Книги
  Max pages: 50
```

---

## 14. Справочник: Instagram парсер

**Файл:** `backend/apps/scrapers/parsers/instagram.py`
**Имя:** `instagram`
**Домены:** `instagram.com`, `www.instagram.com`
**Зависимость:** `instaloader`

### Особенности Instagram-парсера

- Парсит публичные профили по username или URL профиля
- Каждый пост → один `ScrapedProduct`
- Название товара: первое предложение из caption
- Описание: полный caption
- Медиа: все изображения/видео из поста (включая карусели)

### Как передать username для парсинга

В `SiteScraperTask.url` указывается URL профиля Instagram:
```
https://www.instagram.com/ummaland_books/
```

### Конфигурация в Admin

```
ScraperConfig:
  Name: instagram
  Base URL: https://www.instagram.com
  Username: (бот-аккаунт, если требуется авторизация)
  Password: (пароль бот-аккаунта)
  Delay min: 5.0    ← Instagram агрессивно блокирует при частых запросах
  Delay max: 15.0

SiteScraperTask:
  URL: https://www.instagram.com/ummaland_books/
  Target category: Книги
  Max pages: 10    ← примерно = max_posts / 12
```

### attributes для Instagram поста

```python
attributes = {
    "video_url": "https://...",     # URL видео (если Reels/видео)
    "is_video": True,               # флаг видео
    "likes_count": 1250,
    "comments_count": 43,
    "hashtags": ["#books", "#islam"],
    "username": "ummaland_books",
    "post_date": "2024-01-15T10:30:00",
}
```

### Ограничения Instagram

- Instagram блокирует IP при частых запросах (используй задержки 5–15 сек)
- Публичные профили парсятся без авторизации
- Для закрытых профилей нужна авторизация через бот-аккаунт
- Не используй личные аккаунты — риск блокировки

---

## 15. Важные ограничения и антипаттерны

### ❌ Не делать

- **Не запускать AI при парсинге** — AI только вручную из Admin
- **Не заполнять SEO поля при парсинге** — `meta_title`, `og_title` и т.д.
  должны оставаться пустыми после скрапинга
- **Не определять категорию в парсере** — только через `target_category`
- **Не вызывать `product.save()` напрямую** в парсере — только возвращать
  `ScrapedProduct`, сохранение — задача сервиса
- **Не ставить `brand`** для книг — при парсинге книг `brand` очищается
  автоматически

### ✅ Правильные паттерны

- Парсер возвращает `ScrapedProduct` с `stock_quantity=None` → система поставит 3
- `external_id` — уникальный ID товара на сайте-источнике (slug, ID из URL и т.д.)
- Максимально заполнять `attributes` — AI использует их для анализа
- При ошибке `parse_product_detail` — возвращать `None`, не поднимать исключение
- Для OG/HTML мета-тегов — сохранять в `attributes["og_image"]`, `attributes["og_title"]`
  (сервис интеграции сам разберётся куда положить)

### Порядок приоритетов для категории

При старте из **SiteScraperTask** в `ScrapingSession.target_category` попадает
уже **разрешённая** категория: сначала подкатегория задачи, если указана.

```
1. SiteScraperTask.target_subcategory  ← если задана (узкая категория)
2. SiteScraperTask.target_category
   → записывается в ScrapingSession.target_category при запуске Celery
3. ScraperConfig.category_mapping (не используется, если п.1–2 задали категорию)
4. ScraperConfig.default_category     ← низший приоритет
```

---

## 16. Устранение неполадок

### Товары не создаются

1. Проверить что `ScraperConfig` существует и `is_enabled=True`
2. Проверить что имя конфига совпадает с `get_name()` парсера
3. Проверить что парсер зарегистрирован в `registry.py`
4. Посмотреть логи в `/admin/scrapers/scrapingsession/` и `ScrapedProductLog`

### Товары попадают не в ту категорию

1. Проверить **`target_subcategory`** и **`target_category`** у `SiteScraperTask`
   (подкатегория важнее; для Celery-запуска обе учитываются в `run_scraper_task`)
2. Проверить что категория существует в `/admin/catalog/category/`
3. Проверить `category_mapping` в `ScraperConfig`

### Фото не загружаются

1. Проверить что URLs изображений корректные (http/https)
2. Убедиться что первый элемент `images[]` — это URL главного изображения
3. Проверить доступность R2 в настройках Django (`.env`)
4. В логах django backend искать `Auto-downloaded ... URL`

### SEO поля заполняются при парсинге (баг)

Это нарушение принципа: SEO = только AI. Убедиться что:
- Парсер не заполняет `og_title`, `og_description` напрямую — только в `attributes`
- `CatalogNormalizer` не копирует SEO поля из `Product` в `BookProduct`
  (проверить `domain_sync.py`)

### AI-обработка не применяется

- После "Полная AI обработка" — нужно вручную нажать "Применить" в логах AI
- После "Полная AI обработка + авто-применение" — применяется автоматически
- Статус лога должен быть "Одобрено" (не "Завершено") при авто-применении
- Если "Завершено" при авто-применении — перезапустить `celery_ai` воркер:
  ```bash
  docker compose restart celery_ai
  ```

### stock_quantity пустое после AI-обработки

- AI устанавливает stock_quantity=3 только если поле пустое (None или 0)
- Если значение уже есть — AI не перезаписывает
- Проверить `domain_sync.py` — `stock_quantity` из базового Product не должен
  перезаписывать доменный product если базовый = None

---

## Продакшен: после `git pull`

Файл `docker-compose.yml` задаёт проект **`pharmaturk`** (`name: pharmaturk`). Сервисы бэкенда: **`backend`**, **`celeryworker`**, **`celery_ai`**, **`celerybeat`** — у всех подключается корневой **`.env`** (`env_file`).

### Entrypoint бэкенда (`docker-entrypoint.sh`)

У контейнера **`backend`** точка входа — `backend/docker-entrypoint.sh`: при **каждом** старте контейнера выполняются `migrate --noinput`, `collectstatic`, затем gunicorn/runserver. То есть после `git pull` и **`docker compose up -d --build backend`** (или `restart backend`) миграции часто уже применятся сами.

Если нужно применить миграции **без** пересоздания backend (только команда внутри работающего контейнера), из **корня репозитория**:

```bash
docker compose exec backend poetry run python manage.py migrate
```

Без Docker — из каталога `backend` с настроенным окружением:

```bash
cd backend && poetry run python manage.py migrate
```

### Celery после обновления кода

Чтобы воркеры подхватили новый код парсеров и задач:

```bash
docker compose restart celeryworker celery_ai celerybeat
```

(достаточно только `celeryworker`, если менялись обычные парсеры, без очереди `ai`.)

### Sentry

В **`.env`** в корне репозитория задайте **`SENTRY_DSN`** (DSN проекта в Sentry). Пустое значение — мониторинг ошибок **выключен**.

Переменная подхватывается сервисами с `env_file: .env` (**`backend`**, **`celeryworker`**, **`celery_ai`**, **`celerybeat`**): в `config/settings.py` вызывается `sentry_sdk.init(...)` только если `SENTRY_DSN` непустой. После смены DSN перезапустите соответствующие контейнеры.

### Миграции, затронувшие парсеры

Пример: **`scrapers.0012`** — поле `ScraperConfig.default_brand`. После выката убедитесь, что `migrate` прошёл (автоматически при старте `backend` или вручную командой выше).

### Если `service "backend" is not running` или `No such image: mudaroba-backend`

Образ **`mudaroba-backend`** в `docker-compose.yml` собирается локально (`build`), в реестр публично не выкладывается. Режим **`./restart.sh --fast` / `--quick`** **не** вызывает `docker compose build` и передаёт **`--no-build`**: на чистом сервере или после `prune` образа не будет — контейнеры не поднимутся.

**Что сделать на проде (из корня репозитория, с нужными `-f`, например prod-override):**

```bash
# Один раз после clone / потери образов — со сборкой (без --fast):
./restart.sh --logs

# Или только сборка backend, затем up:
docker compose -p pharmaturk -f docker-compose.yml -f docker-compose.prod.yml build backend
docker compose -p pharmaturk -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Дальше, когда образ уже есть на машине, для быстрого рестарта можно снова использовать **`--fast`**.

Команда **`docker compose exec backend ...`** работает только при **запущенном** контейнере `backend`; сначала нужен успешный **`up`**.

---

## Краткая справка по файлам

| Задача | Файл |
|--------|------|
| Базовый класс парсера | `backend/apps/scrapers/base/scraper.py` |
| ScrapedProduct dataclass | `backend/apps/scrapers/base/scraper.py` |
| Утилиты (clean_text, normalize_price) | `backend/apps/scrapers/base/utils.py` |
| Реестр парсеров | `backend/apps/scrapers/parsers/registry.py` |
| Парсер Ummaland | `backend/apps/scrapers/parsers/ummaland.py` |
| Парсер Instagram | `backend/apps/scrapers/parsers/instagram.py` |
| Парсер Zara | `backend/apps/scrapers/parsers/zara.py` |
| Парсер Ilacabak | `backend/apps/scrapers/parsers/ilacabak.py` |
| Парсер LC Waikiki | `backend/apps/scrapers/parsers/lcw.py` |
| Сервис интеграции | `backend/apps/scrapers/services.py` |
| Модели ScraperConfig/Task | `backend/apps/scrapers/models.py` |
| Admin парсеров | `backend/apps/scrapers/admin.py` |
| Нормализация товара | `backend/apps/catalog/services.py` |
| Синхронизация доменных моделей | `backend/apps/catalog/domain_sync.py` |
| Загрузка медиа в R2 | `backend/apps/catalog/utils/parser_media_handler.py` |
| AI генерация контента | `backend/apps/ai/services/content_generator.py` |
| AI применение результатов | `backend/apps/ai/services/result_applier.py` |
| Celery задачи | `backend/apps/scrapers/tasks.py` |
