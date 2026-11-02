# Перенос эфирных масел PHYTOIL из БАДов в «Эфирные масла» — показ на проде, 02.11.2026

PR: https://github.com/Mr-Fulani/PharmaTurk/pull/289 (не влит, не выкачен). На проде **ничего не записано**:
команда `move_essential_oils_from_supplements` запускалась только в режиме показа. Разовый контейнер на образе
релиза e82e8482 с файлами ветки поверх, база открыта только на чтение (`default_transaction_read_only=on`).
Чтение прода — с разрешения владельца в сессии PR.

## Итог

- Переносятся **206 товаров** — вся линейка PHYTOIL производителя Elentra İlaç. Все активны и в наличии, цены в лирах,
  источник — ilacfiyati.com. Сейчас лежат в разделах «БАДы» (160), «Растительные» (42), «Иммунитет» (2), «Куркума» (2).
- Масла (5–50 мл) — 131: по растению в подразделы «Одиночных масел», остальные в «Одиночные масла».
  Воды и гидролаты (150–500 мл) — 75: в сам раздел «Эфирные масла».
- Раздел «Эфирные масла» на проде есть и включён (`essential-oils`, тип `incense`, в нём 0 товаров).
- У 204 из 206 в описании стоит «Биологически активная добавка к пище…» — при переносе убирается.
  У всех убираются ключевые слова «БАД …» / «food supplement …».
- «Хитов продаж» среди них нет. Конфликтов slug нет, адреса карточек не меняются.
- Открытые записи модерации AI по этим товарам — 2: 28777 (товар 23956) и 29023 (товар 23923), причина
  `title_category_mismatch`. После переноса — повторная AI-обработка (см. ниже).

## Решение владельца 1: цена на сайте — **решено 02.11.2026: оставить цены (вариант А, `--section-markup 50`)**

Наценка считается от раздела. У «БАДов» она **50 %**, у «Благовоний» и «Эфирных масел» своей нет — сработает
общая **25 %**. Без решения цены всех 206 товаров на сайте упадут примерно на **17 %**
(пример: PHYTOIL эвкалипт 10 мл — источник 180 TRY, на сайте сейчас 270 TRY, станет 225 TRY).

| Вариант | Как запустить | Цена покупателю |
|---|---|---|
| **А (совет)** — оставить цены | `--section-markup 50`: разделу «Эфирные масла» ставится наценка 50 % | не меняется (проверено показом: «Наценка не меняется») |
| Б — снизить цены | `--allow-markup-change` | падает ≈ на 17 % |

Без одного из вариантов команда записывать отказывается. Владелец 02.11.2026 выбрал **вариант А** — цены не меняются.

## Решение владельца 2: другие масла в БАДах (не переносятся)

Правило берёт только товары с явным признаком эфирного масла или гидролата и без пометки источника
«пищевая добавка». Остальное остаётся в БАДах; при желании можно перенести отдельной командой по id:

- ZADE VITAL масла во флаконах (источник продаёт как пищевые): анисовое 22101, 25222, 25252, 25135; фенхеля 25458, 25379;
  кориандра 25517, 25514, 12000, 11967, 26073; тимьяна 7986. Их же капсулы — БАДы.
- OCEAN OREGANO масло орегано 20 мл — 11531; VACROL капли и спрей с эфирными маслами — 23138, 9849
  (в названии источника «TAKVIYE EDICI GIDA» — пищевая добавка); CHINA OEL — 21367, 25298, 22496.
- Масла холодного отжима, масла в капсулах, рыбий жир, пластыри ARPATCH, GRIPE WATER — БАДы, не трогаем.

## Как запускать после релиза (только после «да» владельца)

```bash
# 1. бэкап базы (pg_dump), затем показ
manage.py move_essential_oils_from_supplements --section-markup 50
# 2. запись
manage.py move_essential_oils_from_supplements --section-markup 50 --apply --backup /backups/essential-oils-20261102.json
```

Повторный запуск ничего не находит. Откат — по бэкапу, порядок в `docs/CATALOG_MAINTENANCE_COMMANDS.md`.

## После переноса (TD-040)

- Названия и SEO остаются прежними. Многие RU-названия AI перевёл плохо («Эау-де-жерань (итир суйу)»,
  «Лимонная вода (сок лимона)», вода ладана как «Эфирное масло босвеллии, 500 мл»). Нужен пилот повторной
  AI-обработки на 5 товарах уже как масел, затем остальные и закрытие записей 28777 и 29023.
- Новые PHYTOIL парсер ilacfiyati сразу кладёт в «Эфирные масла». Повторный парсинг перенесённые в БАДы не вернёт.

## Заметки о проверке

- Первый просмотр был запущен со стандартным стартовым скриптом контейнера, и тот выполнил `collectstatic`
  в общий том статики: «0 static files copied, 176 unmodified» — образ тот же, что у работающего backend,
  файлы не изменились. Следующие просмотры — без стартового скрипта.
- Первый вариант правила брал ещё CHINA OEL 21367 и VACROL 23138 (по русскому названию / «esansiyel yağlar»);
  правило исправлено: русское название учитывается, только если нет турецкого, а пометка «takviye edici gıda»
  оставляет товар БАДом. Итог показа после исправления — ровно 206 PHYTOIL.

## Список товаров (показ на проде, 02.11.2026)

Цены — в лирах с товарной наценкой, без перевода в рубли и без валютной наценки.

| Новый раздел | Товаров |
|---|---:|
| Одиночные масла (`single-essential-oils`) | 121 |
| Эфирные масла (воды и гидролаты) (`essential-oils`) | 75 |
| Чайное дерево (`tea-tree-oil`) | 2 |
| Эвкалиптовое (`eucalyptus-oil`) | 2 |
| Лавандовое (`lavender-oil`) | 2 |
| Мятное (`peppermint-oil`) | 2 |
| Розовое (`rose-oil`) | 2 |

| id | Название на сайте | Раздел сейчас | Новый раздел | В наличии | Цена источника | На сайте сейчас (50 %) | Если общая 25 % |
|---:|---|---|---|---|---:|---:|---:|
| 7075 | PHYTOIL Масло сосны обыкновенной, 50 мл | herbal-supplements | single-essential-oils | да | 4126.54 TRY | 6189.81 TRY | 5158.18 TRY |
| 7104 | PHYTOIL Эфирное масло майорана душистого, 10 мл | supplements | single-essential-oils | да | 1475.80 TRY | 2213.70 TRY | 1844.75 TRY |
| 7136 | PHYTOIL Масло майорана сладкого, 50 мл | supplements | single-essential-oils | да | 5903.19 TRY | 8854.79 TRY | 7378.99 TRY |
| 7167 | PHYTOIL Масло чайного дерева, 10 мл | herbal-supplements | tea-tree-oil | да | 865.52 TRY | 1298.28 TRY | 1081.90 TRY |
| 7198 | PHYTOIL Масло чайного дерева, 50 мл | herbal-supplements | tea-tree-oil | да | 3462.07 TRY | 5193.11 TRY | 4327.59 TRY |
| 7229 | PHYTOIL Масло тимьяна, 10 мл | supplements | single-essential-oils | да | 1981.55 TRY | 2972.33 TRY | 2476.94 TRY |
| 7260 | PHYTOIL Масло тимьяна, 50 мл | supplements | single-essential-oils | да | 7926.20 TRY | 11889.30 TRY | 9907.75 TRY |
| 7291 | PHYTOIL Куркума, 10 мл | turmeric | single-essential-oils | да | 1230.48 TRY | 1845.72 TRY | 1538.10 TRY |
| 7323 | PHYTOIL Куркума, масло, 50 мл | turmeric | single-essential-oils | да | 4921.91 TRY | 7382.87 TRY | 6152.39 TRY |
| 7355 | PHYTOIL Ваниль, 5 мл | supplements | single-essential-oils | да | 2251.26 TRY | 3376.89 TRY | 2814.08 TRY |
| 7387 | PHYTOIL Ваниль, масло, 10 мл | supplements | single-essential-oils | да | 4277.39 TRY | 6416.09 TRY | 5346.74 TRY |
| 7419 | PHYTOIL Ваниль, 50 мл | supplements | single-essential-oils | да | 17109.58 TRY | 25664.37 TRY | 21386.98 TRY |
| 7451 | PHYTOIL Масло ветивера, 5 мл | supplements | single-essential-oils | да | 1948.76 TRY | 2923.14 TRY | 2435.95 TRY |
| 7483 | PHYTOIL Ветивер, 10 мл | supplements | single-essential-oils | да | 3702.65 TRY | 5553.98 TRY | 4628.31 TRY |
| 7514 | PHYTOIL Масло ветивера, 50 мл | supplements | single-essential-oils | да | 14810.60 TRY | 22215.90 TRY | 18513.25 TRY |
| 7545 | PHYTOIL Масло дикой моркови, 10 мл | supplements | single-essential-oils | да | 1686.95 TRY | 2530.43 TRY | 2108.69 TRY |
| 7576 | PHYTOIL Дикая морковь, масло, 50 мл | supplements | single-essential-oils | да | 6747.81 TRY | 10121.72 TRY | 8434.76 TRY |
| 7607 | PHYTOIL Дикий чеснок, 10 мл | herbal-supplements | single-essential-oils | да | 1527.93 TRY | 2291.90 TRY | 1909.91 TRY |
| 7638 | PHYTOIL Масло дикого чеснока, 50 мл | herbal-supplements | single-essential-oils | да | 6111.71 TRY | 9167.57 TRY | 7639.64 TRY |
| 7668 | PHYTOIL Масло Wintergreen, 10 мл | supplements | single-essential-oils | да | 1410.09 TRY | 2115.14 TRY | 1762.61 TRY |
| 7699 | PHYTOIL Масло грушанки, 50 мл | supplements | single-essential-oils | да | 5640.36 TRY | 8460.54 TRY | 7050.45 TRY |
| 7730 | PHYTOIL Масло тысячелистника, 5 мл | supplements | single-essential-oils | да | 2931.39 TRY | 4397.09 TRY | 3664.24 TRY |
| 7761 | PHYTOIL Масло тысячелистника, 10 мл | supplements | single-essential-oils | да | 5569.64 TRY | 8354.46 TRY | 6962.05 TRY |
| 7792 | PHYTOIL Тысячелистник, 50 мл | supplements | single-essential-oils | да | 22278.57 TRY | 33417.86 TRY | 27848.21 TRY |
| 7823 | PHYTOIL Иланг-иланг, 5 мл | supplements | single-essential-oils | да | 1753.15 TRY | 2629.73 TRY | 2191.44 TRY |
| 7854 | PHYTOIL Иланг-иланг, 10 мл | supplements | single-essential-oils | да | 3330.99 TRY | 4996.49 TRY | 4163.74 TRY |
| 7884 | PHYTOIL Масло иланг-иланг, 50 мл | supplements | single-essential-oils | да | 13323.96 TRY | 19985.94 TRY | 16654.95 TRY |
| 9682 | PHYTOIL Анисовая вода, 500 мл | supplements | essential-oils | да | 2873.81 TRY | 4310.72 TRY | 3592.26 TRY |
| 9713 | PHYTOIL Гидролат ромашки, 150 мл | herbal-supplements | essential-oils | да | 1382.80 TRY | 2074.20 TRY | 1728.50 TRY |
| 9744 | PHYTOIL Лимонная вода (сок лимона), 250 мл | supplements | essential-oils | да | 1286.01 TRY | 1929.02 TRY | 1607.51 TRY |
| 9775 | PHYTOIL Вода клементина, 250 мл | supplements | essential-oils | да | 2952.78 TRY | 4429.17 TRY | 3690.98 TRY |
| 9806 | PHYTOIL Вода мелиссы, 250 мл | herbal-supplements | essential-oils | да | 1911.24 TRY | 2866.86 TRY | 2389.05 TRY |
| 9838 | PHYTOIL Сосновая вода, 150 мл | supplements | essential-oils | да | 942.96 TRY | 1414.44 TRY | 1178.70 TRY |
| 9870 | PHYTOIL Тимьяновая вода, 150 мл | herbal-supplements | essential-oils | да | 1192.67 TRY | 1789.01 TRY | 1490.84 TRY |
| 9901 | PHYTOIL Вода тысячелистника, 150 мл | supplements | essential-oils | да | 1885.93 TRY | 2828.90 TRY | 2357.41 TRY |
| 9932 | PHYTOIL Эау де Ярроу (вода тысячелистника), 500 мл | supplements | essential-oils | да | 5733.22 TRY | 8599.83 TRY | 7166.53 TRY |
| 10398 | PHYTOIL Анисовая вода, 150 мл | supplements | essential-oils | да | 945.33 TRY | 1418.00 TRY | 1181.66 TRY |
| 10431 | PHYTOIL Ромашковая вода, 500 мл | herbal-supplements | essential-oils | да | 4203.70 TRY | 6305.55 TRY | 5254.63 TRY |
| 11412 | PHYTOIL Эау-де-клементин, 150 мл | supplements | essential-oils | да | 1845.49 TRY | 2768.24 TRY | 2306.86 TRY |
| 11442 | PHYTOIL Вода с ароматом клементина, 500 мл | supplements | essential-oils | да | 5610.28 TRY | 8415.42 TRY | 7012.85 TRY |
| 11472 | PHYTOIL Эау-де-жерань (итир суйу), 150 мл | supplements | essential-oils | да | 1308.14 TRY | 1962.21 TRY | 1635.18 TRY |
| 11502 | PHYTOIL Гидролат из цветков бессмертника итальянского, 150 мл | supplements | essential-oils | да | 1697.66 TRY | 2546.49 TRY | 2122.08 TRY |
| 11532 | PHYTOIL Вода из мирта, 250 мл | supplements | essential-oils | да | 1506.40 TRY | 2259.60 TRY | 1883.00 TRY |
| 11562 | PHYTOIL Розовая вода, 150 мл | supplements | essential-oils | да | 1848.60 TRY | 2772.90 TRY | 2310.75 TRY |
| 11592 | PHYTOIL Розмариновая вода, 500 мл | supplements | essential-oils | да | 2862.16 TRY | 4293.24 TRY | 3577.70 TRY |
| 11622 | PHYTOIL Эау-де майорана (вода майорана), 150 мл | supplements | essential-oils | да | 1192.67 TRY | 1789.01 TRY | 1490.84 TRY |
| 21784 | PHYTOIL Эвкалиптовая вода, 500 мл | supplements | essential-oils | да | 2443.42 TRY | 3665.13 TRY | 3054.28 TRY |
| 21816 | PHYTOIL Масло бальзамического дерева боsvелия, 150 мл | supplements | essential-oils | да | 1460.70 TRY | 2191.05 TRY | 1825.88 TRY |
| 21848 | PHYTOIL Вода лимонной вербены, 250 мл | supplements | essential-oils | да | 1911.24 TRY | 2866.86 TRY | 2389.05 TRY |
| 21879 | PHYTOIL Вода мелиссы, 150 мл | herbal-supplements | essential-oils | да | 1194.53 TRY | 1791.80 TRY | 1493.16 TRY |
| 21911 | PHYTOIL Вода мелиссы, 500 мл | herbal-supplements | essential-oils | да | 3631.37 TRY | 5447.06 TRY | 4539.21 TRY |
| 21943 | PHYTOIL Вода мятная, 250 мл | herbal-supplements | essential-oils | да | 1286.01 TRY | 1929.02 TRY | 1607.51 TRY |
| 21975 | PHYTOIL Вода мирта, 150 мл | supplements | essential-oils | да | 941.50 TRY | 1412.25 TRY | 1176.88 TRY |
| 22006 | PHYTOIL Вода мирта (Eau de Myrtle), 500 мл | supplements | essential-oils | да | 2862.16 TRY | 4293.24 TRY | 3577.70 TRY |
| 22037 | PHYTOIL Имбирная вода, жидкость, 150 мл | herbal-supplements | essential-oils | да | 942.96 TRY | 1414.44 TRY | 1178.70 TRY |
| 22911 | PHYTOIL Масло Agarwood (Oud), 5 мл | supplements | single-essential-oils | да | 5500.00 TRY | 8250.00 TRY | 6875.00 TRY |
| 22942 | PHYTOIL Анис, масло, 10 мл | supplements | single-essential-oils | да | 500.95 TRY | 751.43 TRY | 626.19 TRY |
| 22953 | PHYTOIL Гвоздичная вода, 150 мл | supplements | essential-oils | да | 631.99 TRY | 947.99 TRY | 789.99 TRY |
| 22973 | PHYTOIL Анис, масло, 50 мл | supplements | single-essential-oils | да | 2003.80 TRY | 3005.70 TRY | 2504.75 TRY |
| 22984 | PHYTOIL Вода гвоздичная, 250 мл | supplements | essential-oils | да | 1011.18 TRY | 1516.77 TRY | 1263.98 TRY |
| 23004 | PHYTOIL Базилик, 10 мл | supplements | single-essential-oils | да | 765.87 TRY | 1148.81 TRY | 957.34 TRY |
| 23015 | PHYTOIL Вода можжевельника, 500 мл | supplements | essential-oils | да | 2443.42 TRY | 3665.13 TRY | 3054.28 TRY |
| 23035 | PHYTOIL Масло базилика, 50 мл | supplements | single-essential-oils | да | 3063.50 TRY | 4595.25 TRY | 3829.38 TRY |
| 23046 | PHYTOIL Лавандовая вода, 150 мл | herbal-supplements | essential-oils | да | 1306.11 TRY | 1959.17 TRY | 1632.64 TRY |
| 23066 | PHYTOIL Бергамот, 10 мл | supplements | single-essential-oils | да | 1061.46 TRY | 1592.19 TRY | 1326.83 TRY |
| 23077 | PHYTOIL Мятная вода, 150 мл | herbal-supplements | essential-oils | да | 803.76 TRY | 1205.64 TRY | 1004.70 TRY |
| 23097 | PHYTOIL Бергамот, 50 мл | supplements | single-essential-oils | да | 4245.83 TRY | 6368.75 TRY | 5307.29 TRY |
| 23108 | PHYTOIL Розмариновая вода, 150 мл | supplements | essential-oils | да | 941.50 TRY | 1412.25 TRY | 1176.88 TRY |
| 23128 | PHYTOIL Капсикум, 10 мл | supplements | single-essential-oils | да | 691.82 TRY | 1037.73 TRY | 864.78 TRY |
| 23139 | PHYTOIL Тимьяновая вода, 500 мл | herbal-supplements | essential-oils | да | 3625.73 TRY | 5438.60 TRY | 4532.16 TRY |
| 23159 | PHYTOIL Масло тмина, 10 мл | supplements | single-essential-oils | да | 1609.12 TRY | 2413.68 TRY | 2011.40 TRY |
| 23170 | PHYTOIL Имбирная вода, 250 мл | herbal-supplements | essential-oils | да | 1508.74 TRY | 2263.11 TRY | 1885.93 TRY |
| 23185 | PHYTOIL Вода базилика, 150 мл | supplements | essential-oils | да | 1458.43 TRY | 2187.65 TRY | 1823.04 TRY |
| 23190 | PHYTOIL Масло тмина, 50 мл | supplements | single-essential-oils | да | 6436.49 TRY | 9654.74 TRY | 8045.61 TRY |
| 23201 | PHYTOIL Имбирная вода, 500 мл | herbal-supplements | essential-oils | да | 2866.61 TRY | 4299.92 TRY | 3583.26 TRY |
| 23216 | PHYTOIL Эау де Синнаниом (корица), вода, 500 мл | supplements | essential-oils | да | 2453.38 TRY | 3680.07 TRY | 3066.73 TRY |
| 23221 | PHYTOIL Катнип, 10 мл | supplements | single-essential-oils | да | 5774.40 TRY | 8661.60 TRY | 7218.00 TRY |
| 23247 | PHYTOIL Лимонная вода (сок лимона), 500 мл | supplements | essential-oils | да | 2443.42 TRY | 3665.13 TRY | 3054.28 TRY |
| 23252 | PHYTOIL Эфирное масло кедра атласского, 10 мл | supplements | single-essential-oils | да | 696.10 TRY | 1044.15 TRY | 870.13 TRY |
| 23279 | PHYTOIL Эфирное масло босвеллии, 500 мл | supplements | essential-oils | да | 4440.53 TRY | 6660.80 TRY | 5550.66 TRY |
| 23284 | PHYTOIL Эфирное масло кедра атласского, 50 мл | supplements | single-essential-oils | да | 2784.42 TRY | 4176.63 TRY | 3480.53 TRY |
| 23312 | PHYTOIL Гидролат бессмертника итальянского (олмез чичек суюу), 500 мл | supplements | essential-oils | да | 5160.88 TRY | 7741.32 TRY | 6451.10 TRY |
| 23317 | PHYTOIL Эфирное масло кедра виргинского, 10 мл | supplements | single-essential-oils | да | 1812.38 TRY | 2718.57 TRY | 2265.48 TRY |
| 23345 | PHYTOIL Лавандовая вода, 500 мл | herbal-supplements | essential-oils | да | 3970.56 TRY | 5955.84 TRY | 4963.20 TRY |
| 23350 | PHYTOIL Эфирное масло кедра виргинского, 50 мл | supplements | single-essential-oils | да | 7249.54 TRY | 10874.31 TRY | 9061.93 TRY |
| 23378 | PHYTOIL Вода лимонной вербены, 500 мл | supplements | essential-oils | да | 3631.37 TRY | 5447.06 TRY | 4539.21 TRY |
| 23383 | PHYTOIL Масло корицы, 10 мл | supplements | single-essential-oils | да | 923.74 TRY | 1385.61 TRY | 1154.68 TRY |
| 23411 | PHYTOIL Эау де нероли, 250 мл | supplements | essential-oils | да | 2212.47 TRY | 3318.71 TRY | 2765.59 TRY |
| 23416 | PHYTOIL Масло коры корицы, 50 мл | supplements | single-essential-oils | да | 3694.94 TRY | 5542.41 TRY | 4618.68 TRY |
| 23444 | PHYTOIL Сосновая вода (сок сосны), жидкость, 250 мл | supplements | essential-oils | да | 1508.74 TRY | 2263.11 TRY | 1885.93 TRY |
| 23449 | PHYTOIL Цитронелла, 10 мл | supplements | single-essential-oils | да | 689.47 TRY | 1034.21 TRY | 861.84 TRY |
| 23477 | PHYTOIL Тимьяновая вода, 250 мл | herbal-supplements | essential-oils | да | 1908.28 TRY | 2862.42 TRY | 2385.35 TRY |
| 23482 | PHYTOIL Цитронелла, 50 мл | supplements | single-essential-oils | да | 2757.88 TRY | 4136.82 TRY | 3447.35 TRY |
| 23515 | PHYTOIL Масло шалфея мускатного, 5 мл | herbal-supplements | single-essential-oils | да | 1982.59 TRY | 2973.89 TRY | 2478.24 TRY |
| 23549 | PHYTOIL Масло шалфея мускатного, 10 мл | herbal-supplements | single-essential-oils | да | 3766.92 TRY | 5650.38 TRY | 4708.65 TRY |
| 23583 | PHYTOIL Масло шалфея мускатного, 50 мл | herbal-supplements | single-essential-oils | да | 15067.68 TRY | 22601.52 TRY | 18834.60 TRY |
| 23617 | PHYTOIL Масло гвоздики, 10 мл | supplements | single-essential-oils | да | 1083.14 TRY | 1624.71 TRY | 1353.93 TRY |
| 23651 | PHYTOIL Масло гвоздики, 50 мл | supplements | single-essential-oils | да | 4332.54 TRY | 6498.81 TRY | 5415.68 TRY |
| 23685 | PHYTOIL Масло копаиба, 10 мл | supplements | single-essential-oils | да | 2838.19 TRY | 4257.29 TRY | 3547.74 TRY |
| 23719 | PHYTOIL Масло копайба, 50 мл | supplements | single-essential-oils | да | 11352.74 TRY | 17029.11 TRY | 14190.93 TRY |
| 23753 | PHYTOIL Масло кориандра, 10 мл | supplements | single-essential-oils | да | 2483.61 TRY | 3725.42 TRY | 3104.51 TRY |
| 23787 | PHYTOIL Кориандр, масло, 50 мл | supplements | single-essential-oils | да | 9934.43 TRY | 14901.65 TRY | 12418.04 TRY |
| 23821 | PHYTOIL Кипарисовое масло, 10 мл | supplements | single-essential-oils | да | 1134.08 TRY | 1701.12 TRY | 1417.60 TRY |
| 23855 | PHYTOIL Кипарисовое масло, 50 мл | supplements | single-essential-oils | да | 4536.32 TRY | 6804.48 TRY | 5670.40 TRY |
| 23889 | PHYTOIL Элеми, 10 мл | supplements | single-essential-oils | да | 1320.30 TRY | 1980.45 TRY | 1650.38 TRY |
| 23923 | PHYTOIL EUCALYPTUS 10 ML | supplements | eucalyptus-oil | да | 922.88 TRY | 1384.32 TRY | 1153.60 TRY |
| 23956 | PHYTOIL EUCALYPTUS 50 ML | supplements | eucalyptus-oil | да | 3691.51 TRY | 5537.27 TRY | 4614.39 TRY |
| 23989 | PHYTOIL Фракинсенс, 10 мл | supplements | single-essential-oils | да | 1881.60 TRY | 2822.40 TRY | 2352.00 TRY |
| 24021 | PHYTOIL Frankincense масло, 50 мл | supplements | single-essential-oils | да | 7526.40 TRY | 11289.60 TRY | 9408.00 TRY |
| 24053 | PHYTOIL Масло ромашки германской, 5 мл | herbal-supplements | single-essential-oils | да | 8049.01 TRY | 12073.52 TRY | 10061.26 TRY |
| 24086 | PHYTOIL Масло ромашки германской, 10 мл | herbal-supplements | single-essential-oils | да | 15293.13 TRY | 22939.70 TRY | 19116.41 TRY |
| 24119 | PHYTOIL Имбирь, 5 мл | herbal-supplements | single-essential-oils | да | 2040.79 TRY | 3061.19 TRY | 2550.99 TRY |
| 24152 | PHYTOIL Имбирное масло, 10 мл | herbal-supplements | single-essential-oils | да | 3877.49 TRY | 5816.24 TRY | 4846.86 TRY |
| 24185 | PHYTOIL Масло с имбирём, 50 мл | herbal-supplements | single-essential-oils | да | 15509.97 TRY | 23264.96 TRY | 19387.46 TRY |
| 24218 | PHYTOIL Масло грейпфрута, 10 мл | supplements | single-essential-oils | да | 964.83 TRY | 1447.25 TRY | 1206.04 TRY |
| 24251 | PHYTOIL Масло грейпфрута, 50 мл | supplements | single-essential-oils | да | 3859.31 TRY | 5788.97 TRY | 4824.14 TRY |
| 24284 | PHYTOIL Масло зелёного мандарина, 10 мл | supplements | single-essential-oils | да | 825.73 TRY | 1238.60 TRY | 1032.16 TRY |
| 24317 | PHYTOIL Зелёный мандарин, 50 мл | supplements | single-essential-oils | да | 3302.93 TRY | 4954.40 TRY | 4128.66 TRY |
| 24350 | PHYTOIL Иммортель, 5 мл | supplements | single-essential-oils | да | 5046.12 TRY | 7569.18 TRY | 6307.65 TRY |
| 24383 | PHYTOIL Иммортель, 10 мл | supplements | single-essential-oils | да | 9587.63 TRY | 14381.45 TRY | 11984.54 TRY |
| 24416 | PHYTOIL Иммортель масло, 50 мл | supplements | single-essential-oils | да | 38350.51 TRY | 57525.77 TRY | 47938.14 TRY |
| 24447 | PHYTOIL Жасмин, эфирное масло, 5 мл | supplements | single-essential-oils | да | 1825.32 TRY | 2737.98 TRY | 2281.65 TRY |
| 24479 | PHYTOIL Масло жасмина, 10 мл | supplements | single-essential-oils | да | 3468.12 TRY | 5202.18 TRY | 4335.15 TRY |
| 24510 | PHYTOIL Жасмин, 50 мл | supplements | single-essential-oils | да | 13872.46 TRY | 20808.69 TRY | 17340.58 TRY |
| 24541 | PHYTOIL Можжевельник, 10 мл | supplements | single-essential-oils | да | 964.18 TRY | 1446.27 TRY | 1205.23 TRY |
| 24572 | PHYTOIL Можжевеловое масло, 50 мл | supplements | single-essential-oils | да | 3856.73 TRY | 5785.10 TRY | 4820.91 TRY |
| 24603 | PHYTOIL Хелла, масло, 5 мл | supplements | single-essential-oils | да | 10032.05 TRY | 15048.08 TRY | 12540.06 TRY |
| 24634 | PHYTOIL Хелла, 10 мл | supplements | single-essential-oils | да | 19060.90 TRY | 28591.35 TRY | 23826.13 TRY |
| 24665 | PHYTOIL KHELLA, масло, 50 мл | supplements | single-essential-oils | да | 76243.58 TRY | 114365.37 TRY | 95304.48 TRY |
| 24696 | PHYTOIL Лавровое масло, 10 мл | supplements | single-essential-oils | да | 953.65 TRY | 1430.48 TRY | 1192.06 TRY |
| 24726 | PHYTOIL Лаванда, 10 мл | supplements | lavender-oil | да | 850.55 TRY | 1275.83 TRY | 1063.19 TRY |
| 24756 | PHYTOIL Лаванда, 50 мл | supplements | lavender-oil | да | 3402.19 TRY | 5103.29 TRY | 4252.74 TRY |
| 24786 | PHYTOIL Эфирное масло лимона, 10 мл | supplements | single-essential-oils | да | 530.52 TRY | 795.78 TRY | 663.15 TRY |
| 24816 | PHYTOIL Лимон, 50 мл | supplements | single-essential-oils | да | 2122.09 TRY | 3183.14 TRY | 2652.61 TRY |
| 24846 | PHYTOIL Масло лемонграсса, 10 мл | supplements | single-essential-oils | да | 1091.92 TRY | 1637.88 TRY | 1364.90 TRY |
| 24876 | PHYTOIL Масло лемонграсса, 50 мл | supplements | single-essential-oils | да | 4367.69 TRY | 6551.54 TRY | 5459.61 TRY |
| 24906 | PHYTOIL Масло мелиссы, 5 мл | herbal-supplements | single-essential-oils | да | 7290.54 TRY | 10935.81 TRY | 9113.18 TRY |
| 24936 | PHYTOIL Масло мелиссы, 10 мл | herbal-supplements | single-essential-oils | да | 13852.03 TRY | 20778.05 TRY | 17315.04 TRY |
| 24966 | PHYTOIL Мелисса, 50 мл | herbal-supplements | single-essential-oils | да | 55408.10 TRY | 83112.15 TRY | 69260.13 TRY |
| 24995 | PHYTOIL Масло мирры, 5 мл | supplements | single-essential-oils | да | 3272.72 TRY | 4909.08 TRY | 4090.90 TRY |
| 25024 | PHYTOIL Масло мирры, 10 мл | supplements | single-essential-oils | да | 6218.18 TRY | 9327.27 TRY | 7772.73 TRY |
| 25053 | PHYTOIL Масло мирры, 50 мл | supplements | single-essential-oils | да | 24872.70 TRY | 37309.05 TRY | 31090.88 TRY |
| 25082 | PHYTOIL Масло мирта, 10 мл | supplements | single-essential-oils | да | 1534.24 TRY | 2301.36 TRY | 1917.80 TRY |
| 25112 | PHYTOIL Масло мирта, 50 мл | supplements | single-essential-oils | да | 6136.94 TRY | 9205.41 TRY | 7671.18 TRY |
| 25142 | PHYTOIL Масло неролли, 5 мл | supplements | single-essential-oils | да | 1819.40 TRY | 2729.10 TRY | 2274.25 TRY |
| 25173 | PHYTOIL Нероли, масло, 10 мл | supplements | single-essential-oils | да | 3456.85 TRY | 5185.28 TRY | 4321.06 TRY |
| 25203 | PHYTOIL Масло неролы, 50 мл | supplements | single-essential-oils | да | 13827.41 TRY | 20741.12 TRY | 17284.26 TRY |
| 25233 | PHYTOIL Ниаули, 10 мл | supplements | single-essential-oils | да | 764.24 TRY | 1146.36 TRY | 955.30 TRY |
| 25264 | PHYTOIL Масло Ниаули, 50 мл | supplements | single-essential-oils | да | 3056.94 TRY | 4585.41 TRY | 3821.18 TRY |
| 25294 | PHYTOIL Масло апельсиновой корки, 10 мл | supplements | single-essential-oils | да | 629.33 TRY | 944.00 TRY | 786.66 TRY |
| 25324 | PHYTOIL Масло апельсиновой цедры, 50 мл | supplements | single-essential-oils | да | 2517.30 TRY | 3775.95 TRY | 3146.63 TRY |
| 25353 | PHYTOIL Масло орегано, 10 мл | supplements | single-essential-oils | да | 881.31 TRY | 1321.97 TRY | 1101.64 TRY |
| 25383 | PHYTOIL Масло орегано, 50 мл | supplements | single-essential-oils | да | 3525.23 TRY | 5287.85 TRY | 4406.54 TRY |
| 25413 | PHYTOIL Пальмароза, эфирное масло, 10 мл | supplements | single-essential-oils | да | 1043.51 TRY | 1565.27 TRY | 1304.39 TRY |
| 25443 | PHYTOIL Масло пальмарозы, 50 мл | supplements | single-essential-oils | да | 4174.03 TRY | 6261.05 TRY | 5217.54 TRY |
| 25473 | PHYTOIL Пачули, 10 мл | supplements | single-essential-oils | да | 1846.53 TRY | 2769.80 TRY | 2308.16 TRY |
| 25502 | PHYTOIL Масло пачули, 50 мл | supplements | single-essential-oils | да | 7386.11 TRY | 11079.17 TRY | 9232.64 TRY |
| 25531 | PHYTOIL Пеларгония, 10 мл | immunity | single-essential-oils | да | 1943.86 TRY | 2915.79 TRY | 2429.83 TRY |
| 25560 | PHYTOIL Масло пеларгонии, 50 мл | immunity | single-essential-oils | да | 7775.42 TRY | 11663.13 TRY | 9719.28 TRY |
| 25589 | PHYTOIL Перечная мята, 10 мл | supplements | peppermint-oil | да | 818.16 TRY | 1227.24 TRY | 1022.70 TRY |
| 25619 | PHYTOIL Перечная мята, 50 мл | supplements | peppermint-oil | да | 3272.64 TRY | 4908.96 TRY | 4090.80 TRY |
| 25649 | PHYTOIL Петитгрейн, 10 мл | supplements | single-essential-oils | да | 1003.30 TRY | 1504.95 TRY | 1254.13 TRY |
| 25679 | PHYTOIL Вода базилика, 500 мл | supplements | essential-oils | да | 4433.63 TRY | 6650.45 TRY | 5542.04 TRY |
| 25680 | PHYTOIL Масло петитгрейн, 50 мл | supplements | single-essential-oils | да | 4013.20 TRY | 6019.80 TRY | 5016.50 TRY |
| 25710 | PHYTOIL Гвоздичная вода, 500 мл | supplements | essential-oils | да | 1921.24 TRY | 2881.86 TRY | 2401.55 TRY |
| 25711 | PHYTOIL Масло римской ромашки, 5 мл | herbal-supplements | single-essential-oils | да | 5670.00 TRY | 8505.00 TRY | 7087.50 TRY |
| 25741 | PHYTOIL Кедровая вода, 250 мл | supplements | essential-oils | да | 1288.01 TRY | 1932.02 TRY | 1610.01 TRY |
| 25742 | PHYTOIL Масло римской ромашки, 10 мл | herbal-supplements | single-essential-oils | да | 10773.00 TRY | 16159.50 TRY | 13466.25 TRY |
| 25772 | PHYTOIL Вода с лимонным соком, 150 мл | supplements | essential-oils | да | 803.76 TRY | 1205.64 TRY | 1004.70 TRY |
| 25773 | PHYTOIL Масло ромашки римской, 50 мл | herbal-supplements | single-essential-oils | да | 43092.00 TRY | 64638.00 TRY | 53865.00 TRY |
| 25804 | PHYTOIL Эвкалиптовая вода, 150 мл | supplements | essential-oils | да | 803.76 TRY | 1205.64 TRY | 1004.70 TRY |
| 25805 | PHYTOIL Масло розы дамасской, 1 мл | supplements | rose-oil | да | 6379.28 TRY | 9568.92 TRY | 7974.10 TRY |
| 25821 | PHYTOIL Анисовая вода, 250 мл | supplements | essential-oils | да | 1512.53 TRY | 2268.80 TRY | 1890.66 TRY |
| 25835 | PHYTOIL Эфирное масло босвеллии, 250 мл | supplements | essential-oils | да | 2337.12 TRY | 3505.68 TRY | 2921.40 TRY |
| 25836 | PHYTOIL Масло розы дамасской, 5 мл | supplements | rose-oil | да | 25517.14 TRY | 38275.71 TRY | 31896.43 TRY |
| 25853 | PHYTOIL Эау-де-сиди (кедровая вода), 150 мл | supplements | essential-oils | да | 805.01 TRY | 1207.52 TRY | 1006.26 TRY |
| 25867 | PHYTOIL Герань, гидролат, 250 мл | supplements | essential-oils | да | 2093.02 TRY | 3139.53 TRY | 2616.28 TRY |
| 25868 | PHYTOIL Розмарин с камфорой, 10 мл | supplements | single-essential-oils | да | 3864.00 TRY | 5796.00 TRY | 4830.00 TRY |
| 25883 | PHYTOIL Ромашковая вода, 250 мл | herbal-supplements | essential-oils | да | 2212.47 TRY | 3318.71 TRY | 2765.59 TRY |
| 25897 | PHYTOIL Эау-де-Жераниум (ароматическая вода), 500 мл | supplements | essential-oils | да | 3976.74 TRY | 5965.11 TRY | 4970.93 TRY |
| 25898 | PHYTOIL Розмариновое масло с цинеолом, 10 мл | supplements | single-essential-oils | да | 1206.66 TRY | 1809.99 TRY | 1508.33 TRY |
| 25913 | PHYTOIL Эау де Синнамон (вода корицы), 150 мл | supplements | essential-oils | да | 807.03 TRY | 1210.55 TRY | 1008.79 TRY |
| 25916 | PHYTOIL Вода с экстрактом базилика, 250 мл | herbal-supplements | essential-oils | да | 2333.49 TRY | 3500.24 TRY | 2916.86 TRY |
| 25927 | PHYTOIL Сосновая вода (вода из сосновых игл), 500 мл | supplements | essential-oils | да | 2866.61 TRY | 4299.92 TRY | 3583.26 TRY |
| 25928 | PHYTOIL Масло розмарина с цинеолом, 50 мл | supplements | single-essential-oils | да | 4826.65 TRY | 7239.98 TRY | 6033.31 TRY |
| 25943 | PHYTOIL Можжевеловая вода, 150 мл | supplements | essential-oils | да | 803.76 TRY | 1205.64 TRY | 1004.70 TRY |
| 25946 | PHYTOIL Корица, жидкость, 250 мл | supplements | essential-oils | да | 1291.25 TRY | 1936.88 TRY | 1614.06 TRY |
| 25957 | PHYTOIL Розовая вода, 500 мл | supplements | essential-oils | да | 5619.73 TRY | 8429.60 TRY | 7024.66 TRY |
| 25958 | PHYTOIL Розмарин Verbenone, 10 мл | supplements | single-essential-oils | да | 3900.42 TRY | 5850.63 TRY | 4875.53 TRY |
| 25973 | PHYTOIL Вода лавандовая, 250 мл | herbal-supplements | essential-oils | да | 2089.77 TRY | 3134.66 TRY | 2612.21 TRY |
| 25976 | PHYTOIL Эвкалиптовая вода, 250 мл | supplements | essential-oils | да | 1286.01 TRY | 1929.02 TRY | 1607.51 TRY |
| 25988 | PHYTOIL Розмарин Verbenone, масло, 50 мл | supplements | single-essential-oils | да | 15601.68 TRY | 23402.52 TRY | 19502.10 TRY |
| 26003 | PHYTOIL Мятная вода, 500 мл | herbal-supplements | essential-oils | да | 2443.42 TRY | 3665.13 TRY | 3054.28 TRY |
| 26006 | PHYTOIL Гидролат цветков бессмертника итальянского, 250 мл | supplements | essential-oils | да | 2716.25 TRY | 4074.38 TRY | 3395.31 TRY |
| 26018 | PHYTOIL Масло шалфея, 10 мл | herbal-supplements | single-essential-oils | да | 1885.48 TRY | 2828.22 TRY | 2356.85 TRY |
| 26033 | PHYTOIL Вода нероли, 500 мл | supplements | essential-oils | да | 4203.70 TRY | 6305.55 TRY | 5254.63 TRY |
| 26036 | PHYTOIL Можжевеловая вода, 250 мл | supplements | essential-oils | да | 1286.01 TRY | 1929.02 TRY | 1607.51 TRY |
| 26048 | PHYTOIL Шалфей, 50 мл | herbal-supplements | single-essential-oils | да | 7541.93 TRY | 11312.90 TRY | 9427.41 TRY |
| 26063 | PHYTOIL Розовая вода, 250 мл | supplements | essential-oils | да | 2957.76 TRY | 4436.64 TRY | 3697.20 TRY |
| 26066 | PHYTOIL Вода с экстрактом цветков лимонной вербены, 150 мл | herbal-supplements | essential-oils | да | 1194.53 TRY | 1791.80 TRY | 1493.16 TRY |
| 26079 | PHYTOIL Сандаловое масло, 1 мл | supplements | single-essential-oils | да | 2743.70 TRY | 4115.55 TRY | 3429.63 TRY |
| 26094 | PHYTOIL Вода тысячелистника, 250 мл | supplements | essential-oils | да | 3017.48 TRY | 4526.22 TRY | 3771.85 TRY |
| 26097 | PHYTOIL Вода нероли, 150 мл | supplements | essential-oils | да | 1382.80 TRY | 2074.20 TRY | 1728.50 TRY |
| 26110 | PHYTOIL Масло сандалового дерева, 5 мл | supplements | single-essential-oils | да | 10974.79 TRY | 16462.19 TRY | 13718.49 TRY |
| 26128 | PHYTOIL Розмариновая вода, 250 мл | supplements | essential-oils | да | 1506.40 TRY | 2259.60 TRY | 1883.00 TRY |
| 26141 | PHYTOIL Эфирное масло сосны обыкновенной, 10 мл | herbal-supplements | single-essential-oils | да | 1031.63 TRY | 1547.45 TRY | 1289.54 TRY |
