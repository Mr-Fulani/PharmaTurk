# Платные web-access сервисы: возможности, бюджет и повторное использование

Последняя сверка кода, production-конфигурации и кабинета провайдера: **2026-08-31**  
Владелец: catalog-commerce / infrastructure  
Область: supplier parsers, проверки цены и наличия, CAPTCHA/anti-bot transport

Этот документ описывает платные транспортные возможности Bright Data, которые уже
подключены к Mudaroba. Он не является бухгалтерским отчётом: баланс, фактический
расход и актуальную цену перед новым rollout всегда сверяйте в кабинете провайдера.

## Краткий выбор транспорта

| Возможность | Когда использовать | Единица оплаты | Состояние в Mudaroba |
| --- | --- | --- | --- |
| Bright Data native Residential proxy | сайту достаточно другого IP/географии и обычного HTTP-клиента | трафик, GB | доступен через `SCRAPER_PROXY_URL` и server-owned `ScraperConfig.use_proxy` |
| Bright Data Web Unlocker API | сайт стабильно возвращает CAPTCHA/anti-bot challenge или неполный JS HTML | запросы/results, CPM | включён для FLO только в интерактивных card/cart событиях |
| Bright Data Browser API | нужны клики, scroll, формы или полноценная browser session | отдельный Browser API тариф | **не подключён**; требует отдельного решения и бюджета |

Не используйте Web Unlocker как browser automation. Провайдер прямо отделяет
получение разблокированного HTML/JSON от сценариев с кликами и навигацией.

## Текущий тариф и защита от расходов

На дату сверки кабинет показывает:

- account plan: **Pay as you go**, без месячного commitment;
- Web Unlocker Free Tier: **5 000 запросов в месяц**;
- Pay-as-you-go Web Unlocker: **$1.50 за 1 000 запросов**;
- для зоны `flo_unlocker` установлен лимит **4 900 REQ/month** с действием
  `Suspend zone and Alert`;
- auto recharge для Proxy & Web-Scraper API/IDE **выключен**;
- payment methods уже есть в аккаунте, но их реквизиты не хранятся в репозитории;
- premium domains для зоны выключены; FLO не был в premium allowlist на дату сверки.

При полностью платном расходе 4 900 запросов по ставке $1.50/1K верхняя оценка —
**$7.35 за месяц**. Free Tier может покрыть этот объём, но код не должен предполагать,
как провайдер применит credits: источником правды остаются Billing и Cost Explorer.

В зоне включён Manual `expect`. Это важно для бюджета: при использовании custom
features Bright Data считает **все запросы, включая неуспешные**, хотя обычный Web
Unlocker PAYG заявлен как pay-only-for-success. Поэтому приложение не делает свой
повтор платного запроса; внутренними retry/IP rotation управляет сам провайдер.

Официальные источники:

- [Web Unlocker pricing](https://brightdata.com/pricing/web-unlocker);
- [Web Unlocker features и billing custom expect](https://docs.brightdata.com/scraping-automation/web-unlocker/features);
- [Pay as you go и auto recharge](https://docs.brightdata.com/general/account/billing-and-pricing/payment);
- [проверка payment method и free credit](https://docs.brightdata.com/general/account/billing-and-pricing/payment-verification).

Нельзя включать auto recharge, добавлять средства, менять тариф или повышать лимит
зоны без явного подтверждения владельца проекта.

## Native Residential proxy

Возможности:

- турецкий egress и обход блокировок по репутации IP;
- rotation/session средствами провайдера;
- совместимость с обычными `httpx`, `requests` и `curl-cffi` parser adapters;
- единый transport для источников, которым не требуется provider-side CAPTCHA solver.

Текущий код:

- URL и credentials берутся только из server-owned `SCRAPER_PROXY_URL`;
- proxy активируется только совпавшим active/enabled `ScraperConfig.use_proxy`;
- Bright Data TLS inspection разрешён только через port `44445` и закреплённый
  `/app/certs/brightdata_root_ca_44445.crt`;
- `verify=False` запрещён; client-controlled proxy URL не принимается;
- для разных источников пока используется один глобальный proxy URL.

Цена native proxy зависит от account/zone. Кабинет на дату сверки показывал
Residential pay-per-GB **$8/GB**; перед новым источником цену нужно перепроверить.
Этот transport подходит, например, для Zara/Inditex и Akakçe, если одного
residential IP достаточно. CAPTCHA solver он сам по себе не гарантирует.

## Web Unlocker API

Возможности провайдера:

- автоматические proxy rotation и retries;
- CAPTCHA solving и anti-bot обход;
- browser/TLS fingerprint и user-agent rotation;
- геотаргетинг;
- автоматический JavaScript rendering;
- ожидание конкретного элемента или текста (`x-unblock-expect`);
- возврат HTML/JSON; отдельно доступны markdown и screenshot режимы;
- асинхронный API для будущих больших batch workloads.

Текущая реализация намеренно уже возможностей провайдера:

- fixed endpoint `https://api.brightdata.com/request`;
- только HTTPS targets из server-owned host allowlist;
- сейчас разрешены только `flo.com.tr` и `www.flo.com.tr`;
- API key и zone name читаются из secrets, не из request пользователя;
- `x-unblock-expect={"text":"window.productDetail"}` передаётся в JSON `headers`;
- `country=tr`, `format=raw`, принудительный render выключен;
- timeout 30 секунд, тело не больше 10 MiB;
- проверяются target status, непустое тело, CAPTCHA markers, product marker и SKU;
- секреты, response body и provider credentials не пишутся в логи.

Зона провайдера дополнительно ограничена production egress IP и FLO target hosts.
При создании нового adapter этого недостаточно расширить: предпочтительна отдельная
zone или отдельный узкий allowlist с собственным лимитом и canary.

## Где платный запрос разрешён сейчас

Web Unlocker можно активировать только из явного интерактивного события:

1. пользователь открыл карточку — frontend делает один `POST .../source-refresh`;
2. пользователь открыл корзину — frontend делает один `POST /orders/cart/revalidate`,
   backend последовательно проверяет все подходящие строки корзины.

Poll статуса карточки выполняет только `GET` к Mudaroba и не вызывает поставщика.
React Strict Mode дубли подавляются promise/single-flight. Cart GET, add/update,
acknowledge и checkout используют сохранённый snapshot и не делают supplier HTTP.

Фоновая задача `catalog.refresh_source_offers` не зарегистрирована и не присутствует
в `CELERY_BEAT_SCHEDULE`. Полный импорт FLO также не включает Web Unlocker только
из-за environment flag. Это защищает free tier от незаметного batch-расхода.

## Правила повторного использования

Перед подключением другого магазина:

1. Сначала проверить direct HTTP, затем native proxy. Web Unlocker выбирать только
   при подтверждённом challenge/CAPTCHA или неполном JS response.
2. Зафиксировать один business event, который имеет право тратить запрос. Не включать
   scheduled/background обход без отдельного бюджета.
3. Добавить отдельный feature flag и точный parser/source allowlist.
4. Разрешить только точные HTTPS hostnames. URL, zone, country, proxy и credentials
   не должны приходить от клиента.
5. Выбрать source-specific `expect` marker, который невозможен на CAPTCHA-странице.
6. Проверять identity: supplier SKU/external id должен совпадать с сохранённым offer.
7. Ограничить timeout, response bytes, concurrency, rate и число запросов на событие.
8. Не добавлять app-level retry поверх Web Unlocker. Любое изменение retry требует
   пересчёта worst-case стоимости.
9. Настроить provider target/IP allowlists, monthly `Suspend and Alert` и Cost Explorer.
10. Пройти fixture tests, один staging canary и один bounded production canary.

Подходящие кандидаты для переиспользования: точечные проверки price/stock на
Zara/Inditex, Akakçe и других supplier cards, где обычный proxy стабильно не проходит.
Неподходящие сценарии: логин в аккаунты, social account management, массовый импорт
каталога без бюджета, произвольный URL fetch и действия в браузере.

## Наблюдаемость и аварийное отключение

Проверять:

- application log `flo_web_unlocker_request` — outcome, target host, status и bytes;
- `source_offer_verification_total{source,outcome}`;
- `product_card_source_refresh_total{source,outcome}`;
- Billing → Cost Explorer и usage конкретной zone;
- provider limit alerts и account balance alerts.

При неожиданном росте расхода:

1. `FLO_WEB_UNLOCKER_ENABLED=false` и recreate только application containers;
2. выключить источник в `PRODUCT_CARD_SOURCE_REFRESH_SOURCES` и/или
   `SOURCE_OFFER_VERIFICATION_SOURCES`;
3. suspend zone в Bright Data;
4. сохранить логи и выяснить event/request cardinality до повторного включения;
5. не повышать лимит и не включать auto recharge как способ скрыть runaway traffic.

## Секреты и аудит

Никогда не коммитить API key, proxy password, card data, полный `.env` или raw curl с
credentials. В документации допустимы только имена env, zone и несекретные policy.
Production secret file должен иметь права `0600`; API key следует ротировать после
утечки и не выводить даже в диагностический stdout.
