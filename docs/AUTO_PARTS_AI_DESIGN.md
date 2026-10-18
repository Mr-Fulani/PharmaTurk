# Автозапчасти: модель полей и обработка без LLM (дизайн)

Статус: предложение, код не менялся. Дата: 2026-10-18.

Цель — подготовить домен `auto_parts` так, чтобы карточки (название, описание,
SEO, характеристики, применимость) собирались программно, а LLM вызывался
только для свободного маркетингового текста источника. Принципы те же, что у
остальных не медицинских доменов (`apps/ai/services/rules`, см. `AI_GUIDE.md`):
словари и шаблоны → память переводов → короткий LLM-запрос как fallback.

## 1. Что есть сейчас

- `AutoPartProduct` (`apps/catalog/models.py`): `part_number`, `car_brand`,
  `car_model`, `compatibility_years` — по одной строке на товар.
- `AutoPartVariant`: `condition`, `manufacturer`, `sku`, цена.
- Корневая категория `auto-parts`, общие атрибуты `material`, `weight`,
  `length` (`catalog/constants.py`). В `_get_category_family_rules` домен
  отнесён к семейству `electronics` (focus: compatibility, specs).

Ограничения: одна марка/модель на товар (у запчасти их десятки), нет
OEM-номеров и кросс-номеров, применимость не фильтруется и не ищется,
номер не нормализован (поиск «1K0 615 301 AA» ≠ «1K0615301AA»).

## 2. Предлагаемая модель

### 2.1. `AutoPartProduct` (расширение)

| Поле | Тип | Назначение |
|---|---|---|
| `part_number` | char(100) | артикул производителя как в источнике |
| `part_number_normalized` | char(100), index | верхний регистр, только `[A-Z0-9]` — для поиска |
| `brand` (есть в базе) | FK Brand | производитель детали (Bosch, Mann, TRW) |
| `part_kind` | char(64), index | канонический тип: `brake_pad`, `oil_filter`… (словарь) |
| `position` | char(32) | `front`/`rear`/`left`/`right`/`front_left`… |
| `condition` | choice | `new` / `used` / `refurbished` (сейчас только у варианта) |
| `specs` | через `ProductDynamicAttribute` | диаметр, ширина, напряжение, вязкость… (`attribute_specs.py`) |

### 2.2. `AutoPartNumber` — OEM и кросс-номера (1:N)

| Поле | Тип |
|---|---|
| `product` | FK AutoPartProduct |
| `number` / `number_normalized` | char(100) / char(100), index |
| `kind` | `oem` / `cross` (аналог) |
| `maker` | char(64): «VAG», «Toyota», «Bosch» — как указал источник |
| `source` | char(32): парсер / ручной ввод |

Уникальность `(product, kind, number_normalized)`. Люди ищут запчасть по
OEM-номеру, поэтому эти номера попадают в поиск и в keywords.

### 2.3. `AutoPartFitment` — применимость (1:N)

| Поле | Тип |
|---|---|
| `product` | FK |
| `make` / `make_slug` | char(64) — «Volkswagen» / `volkswagen` |
| `model` / `model_slug` | char(64) — «Passat» / `passat` |
| `generation` | char(64) — «B6 (3C2)», кузов |
| `year_from`, `year_to` | smallint, null |
| `engine` | char(64) — «2.0 TDI», `engine_code` char(32) — «CBAB» |
| `fuel` | choice: petrol/diesel/hybrid/electric/lpg |
| `power_hp` | smallint, null |
| `note` | char(255) — оговорки источника («кроме 4Motion») |

Индексы `(make_slug, model_slug)`, `(year_from, year_to)`. Марки и модели —
нормализованные slug'и по словарю алиасов (`VW` → `volkswagen`,
`Mercedes-Benz`/`Mercedes` → `mercedes-benz`), без справочника поколений на
первом этапе. TecDoc (лицензируемая база) — отдельное решение, см. §6.

Старые `car_brand`/`car_model`/`compatibility_years` остаются для
совместимости и заполняются из первой строки применимости.

## 3. Обработка без LLM

1. **Парсер** складывает сырьё в `external_data.attributes`: название,
   артикул, производитель, список OEM, таблица «Uyumlu Araçlar» /
   «Araç Uyumluluğu», характеристики «Teknik Özellikler».
2. **Нормализация номеров** — `re.sub(r"[^A-Z0-9]", "", number.upper())`;
   номер короче 4 символов или из одних букв отбрасывается в модерацию
   (`part_number_invalid`).
3. **Тип детали** — словарь TR/EN → канон → RU/EN с родом (как `KINDS` в
   `rules/vocab.py`): «fren balatası» → «тормозные колодки» / «Brake Pads»,
   «yağ filtresi» → «масляный фильтр» / «Oil Filter», «amortisör» →
   «амортизатор» / «Shock Absorber», «buji» → «свеча зажигания» / «Spark
   Plug». Стартовый словарь — ~200 терминов по фактическим названиям
   источника (сначала выгрузка частот слов, как сделано для одежды).
4. **Позиция** — «ön/arka/sağ/sol» → «передний/задний/правый/левый» с
   согласованием по роду (`ru_adjective`).
5. **Применимость** — разбор таблицы источника построчно; строка, которую не
   удалось разобрать, не теряется: она уходит в `note`, товар получает
   причину модерации `fitment_unparsed`.
6. **Название по шаблону:**
   - RU: `{Тип} {позиция} {Производитель} {артикул} для {Марка Модель} ({годы})`
     — «Тормозные колодки передние Bosch 0986494104 для Volkswagen Passat (2005–2010)»;
   - EN: `{Manufacturer} {part_number} {Position} {Kind} for {Make Model} ({years})`.
   - Больше трёх моделей — «для Volkswagen, Audi, Skoda»; больше трёх марок —
     без хвоста применимости (она в таблице на карточке).
7. **Описание из фактов** (как `build_fact_description`): тип, производитель,
   артикул, OEM-номера, сводка применимости, таблица характеристик. Свободный
   текст источника переводится LLM только если он есть и не найден в памяти
   переводов (`AITranslationMemory`, namespace `product_description`).
8. **SEO по шаблону:** `meta_title` = «{название} — купить из Турции»,
   `meta_description` = «{Тип} {Производитель} {артикул} для {Марка Модель}.
   OEM: {номера}. Заказ из Турции через менеджера»; keywords — артикул,
   все OEM-номера, «{тип} {марка модель}».
9. **Характеристики** — через `attribute_specs.py` (новые спецификации с
   `product_types=("auto_parts",)` и алиасами значений), без LLM.

## 4. Модерация

Сохраняется общий механизм (`get_moderation_reasons`), новые причины:

- `part_number_invalid` — нет артикула или он не похож на номер;
- `fitment_unparsed` — строки применимости не разобраны;
- `oem_conflict` — один OEM-номер у товаров разных `part_kind`;
- `kind_unknown` — тип не найден в словаре (название тогда даёт LLM).

## 5. Поиск и витрина

- Поиск: точное совпадение по `part_number_normalized` и
  `AutoPartNumber.number_normalized` раньше полнотекстового поиска.
- Фильтры каталога: марка → модель → год из `AutoPartFitment`
  (`select_related`/частичные индексы по правилам `DEVELOPMENT_RULES` §2.4).
- JSON-LD `Product`: `mpn` = артикул, `brand` = производитель,
  `isRelatedTo`/описание применимости — без выдуманных данных.

## 6. Стоимость и открытые вопросы

- При шаблонных названиях/SEO и описании из фактов LLM нужен только для
  свободного текста: ожидаемо 0–20 % SKU, ≈ $0.0003 за вызов узкого запроса.
- Вопросы к владельцу: какие сайты-источники; нужны ли б/у запчасти;
  нужен ли подбор по VIN (это внешний сервис или TecDoc — платная лицензия);
  нужна ли привязка к поколениям кузова сразу или достаточно лет выпуска.

## 7. План внедрения

1. Миграции полей и таблиц `AutoPartNumber`, `AutoPartFitment` (+ админка).
2. Парсер первого источника: сырьё в `external_data.attributes`.
3. Словари типов/позиций/марок и правила в `apps/ai/services/rules`
   (`auto_parts` в `RULE_PRODUCT_TYPES`), тесты на реальных названиях.
4. Поиск по номерам и фильтр применимости, sitemap/фиды.
5. Пилот 20 товаров кнопкой в админке без авто-применения, разбор модерации.
