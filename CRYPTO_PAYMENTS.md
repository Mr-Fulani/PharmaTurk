# Криптоплатежи (CoinRemitter)

Инструкция по настройке и развёртыванию криптовалютной оплаты через CoinRemitter в режиме разработки и на боевом сервере.

---

## 1. Обзор

- **Провайдер:** [CoinRemitter](https://coinremitter.com/)
- **Поддерживаемые монеты:** USDT (TRC20/ERC20), BTC, ETH, LTC, BCH, DOGE, BNB, TRX, USDC ERC20 и др. (полный список в [документации](https://coinremitter.com/docs))
- **Режим тестирования:** TCN (Test Coin) — лимит 10 TCN на инвойс
- **Архитектура:** Один кошелёк (API key) = одна монета. Для нескольких монет нужны отдельные кошельки и переключение по настройкам.

---

## 2. Разработка и тестовый callback

### 2.1. Тестовая монета TCN

1. Зарегистрируйтесь на [CoinRemitter](https://merchant.coinremitter.com/signup)
2. Создайте кошелёк **Test Coin (TCN)**
3. Получите API Key и Password в настройках кошелька
4. В `.env`:
   ```env
   COINREMITTER_API_KEY=ваш_api_key
COINREMITTER_API_PASSWORD=ваш_пароль
COINREMITTER_COIN=TCN
COINREMITTER_WEBHOOK_IP_WHITELIST=
SITE_URL=http://localhost:3001
   ```

**Ограничение TCN:** максимум 10 TCN на один инвойс. Сумма заказа в фиате конвертируется в TCN — следите, чтобы не превысить лимит.

### 2.2. Публичный callback

CoinRemitter получает `notify_url` только для публичного HTTPS-адреса. Провайдер
в коде намеренно не передаёт localhost и стандартные домены
`ngrok-free.dev`/`ngrok.io`/`ngrok.app`: их interstitial-страница мешает
серверной проверке callback. Для end-to-end теста используйте staging-домен,
Cloudflare Tunnel или другой tunnel без промежуточной HTML-страницы.

При локальном `SITE_URL=http://localhost:3001` инвойс может быть создан, но
callback URL не передаётся и автоматического подтверждения заказа не будет.

---

## 3. Боевой сервер (production)

### 3.1. Требования

- HTTPS (SSL) на всех доменах
- Публично доступный URL для webhook (CoinRemitter делает POST с своих серверов)
- Backend и frontend доступны по настройкам ниже

### 3.2. Создание боевого кошелька

1. Войдите в [CoinRemitter Merchant](https://merchant.coinremitter.com/)
2. Создайте кошелёк нужной монеты (например, **USDT TRC20**)
3. Включите API в настройках кошелька
4. Скопируйте **API Key** и **API Password**

### 3.3. Переменные окружения (.env)

```env
# CoinRemitter — боевой кошелёк
COINREMITTER_API_KEY=ваш_боевой_api_key
COINREMITTER_API_PASSWORD=ваш_боевой_пароль
COINREMITTER_COIN=USDTTRC20
# Необязательный comma-separated allowlist IP CoinRemitter. Заполняйте только
# после trusted-ingress real-IP normalization; за Cloudflare без неё Nginx
# видит адрес edge, а не CoinRemitter.
COINREMITTER_WEBHOOK_IP_WHITELIST=

# URL для webhook (должен вести на backend)
# Вариант A: backend на отдельном поддомене
SITE_URL=https://api.mudaroba.com

# Вариант B: backend за тем же доменом (Nginx проксирует /api)
SITE_URL=https://mudaroba.com

# URL фронтенда (success_url, fail_url — редирект после оплаты)
FRONTEND_SITE_URL=https://mudaroba.com
```

### 3.4. Схема URL

| Переменная         | Назначение                    | Пример                    |
|--------------------|-------------------------------|---------------------------|
| `SITE_URL`         | Базовый URL backend (webhook) | `https://api.mudaroba.com` |
| `FRONTEND_SITE_URL`| URL фронтенда (редиректы)     | `https://mudaroba.com`   |

Формируемые URL:
- `notify_url`: `{SITE_URL}/api/payments/crypto/webhook/` — CoinRemitter шлёт сюда POST при смене статуса
- `success_url`: для `ru` — `{FRONTEND_SITE_URL}/checkout-success?number=...`,
  для `en` — `{FRONTEND_SITE_URL}/en/checkout-success?number=...`;
- `fail_url`: для `ru` — `{FRONTEND_SITE_URL}/checkout-crypto?number=...`,
  для `en` — `{FRONTEND_SITE_URL}/en/checkout-crypto?number=...`.

### 3.5. Модель доверия webhook

CoinRemitter webhook не считается аутентифицированным источником статуса. Поля
`id`/`invoice_id` используются только для поиска локального платежа. Backend
затем вызывает `invoice/get` с API credentials и проверяет идентификаторы,
`custom_data1` (номер заказа), fiat currency, total/paid amounts и provider
status. Только после этой сверки под блокировкой строк заказ переводится в paid
и один раз списываются остатки. Повторный callback идемпотентен, а поздний
`expired` не понижает уже оплаченный заказ.

Если `COINREMITTER_WEBHOOK_IP_WHITELIST` непуст, запрос до разбора payload
отклоняется с `403`, когда доверенный `X-Real-IP` не входит в список. Не
передавайте клиентский `X-Forwarded-For` напрямую в Django; Nginx должен
перезаписывать `X-Real-IP` значением нормализованного `$remote_addr`.

Важно: в стандартном `nginx/default.conf` `$remote_addr` намеренно означает
неподделываемый непосредственный peer. За Cloudflare это адрес edge-узла, а не
исходный адрес CoinRemitter. Поэтому allowlist оставляют пустым, пока внешний
trusted ingress не проверяет proxy source и не выполняет real-IP normalization
(либо IP-фильтрацию делают на самом edge). Даже без IP allowlist статус не
принимается на веру: backend делает авторизованный `invoice/get` и полную сверку.

CoinRemitter возвращает два идентификатора: длинный `id` и короткий
`invoice_id`, используемый методом `invoice/get`. Проект сохраняет их отдельно
как `CryptoPayment.invoice_id` и `CryptoPayment.invoice_code`. Для исторических
строк без `invoice_code` поле безопасно дозаполняется после успешной
аутентифицированной проверки webhook.

### 3.6. Read-only reconciliation

До и после релиза сверяйте локальные платежи с авторизованным `invoice/get`:

```bash
cd backend
poetry run python manage.py reconcile_coinremitter \
  --limit 100 --older-than-minutes 10

# Проверить все локальные статусы и вернуть ненулевой exit code при drift.
poetry run python manage.py reconcile_coinremitter \
  --all-statuses --fail-on-drift
```

Команда всегда работает в режиме **READ ONLY**: она не меняет заказ, платёж или
инвойс провайдера. По умолчанию проверяются только pending-платежи старше пяти
минут. Категория `needs_local_confirmation` является критическим расхождением:
сначала сохраните вывод и provider audit trail, затем повторно доставьте
подлинный webhook либо выполните утверждённую оператором процедуру исправления.
Не меняйте статусы напрямую в БД: подтверждение должно пройти штатную атомарную
логику списания остатков и уведомлений. `provider_unavailable` означает, что
сверку нужно повторить после восстановления исходящего HTTPS/API credentials.

### 3.7. Nginx и маршрутизация

Webhook должен доходить до backend. Пример конфигурации:

**Backend на api.mudaroba.com:**
```nginx
server {
    listen 443 ssl http2;
    server_name api.mudaroba.com;
    # ... ssl ...

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Frontend и API на одном домене (mudaroba.com):**
```nginx
server {
    listen 443 ssl http2;
    server_name mudaroba.com www.mudaroba.com;
    # ... ssl ...

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
В этом случае `SITE_URL=https://mudaroba.com` — запросы на `/api/payments/crypto/webhook/` пойдут на backend.

### 3.8. Проверка доступности webhook

```bash
curl -X POST https://ваш-домен/api/payments/crypto/webhook \
  -H "Content-Type: application/json" \
  -d '{}'
```
При пустом IP allowlist ожидается ответ `200 OK` с телом `{"ok":true}` — это
только валидационный ping, а не имитация оплаты. При включённом allowlist запрос
с постороннего адреса ожидаемо вернёт `403`. Для проверки подтверждения
используйте тестовый инвойс: произвольный `status=paid` в POST не принимается на
доверие.

---

## 4. Поддерживаемые монеты (COINREMITTER_COIN)

| Значение      | Монета           |
|---------------|------------------|
| `TCN`         | Test Coin (тест) |
| `USDTTRC20`   | USDT (Tron)      |
| `USDTERC20`   | USDT (Ethereum)  |
| `BTC`         | Bitcoin          |
| `ETH`         | Ethereum         |
| `LTC`         | Litecoin         |
| `BCH`         | Bitcoin Cash     |
| `DOGE`        | Dogecoin         |
| `BNB`         | Binance Coin     |
| `TRX`         | Tron             |
| `USDCERC20`   | USDC (Ethereum)  |

Точный список — в [документации CoinRemitter](https://coinremitter.com/docs). Монета задаётся кошельком: API key привязан к конкретному кошельку (и монете).

---

## 5. Несколько монет

Сейчас в коде используется один кошелёк (`COINREMITTER_API_KEY`). Для нескольких монет возможны варианты:

1. **Один кошелёк в production** — выбрать основную монету (например, USDT TRC20) и использовать её.
2. **Расширение кода** — добавить поддержку нескольких ключей и выбор монеты при оформлении заказа (потребуются доработки backend и frontend).

---

## 6. Чек-лист перед production

- [ ] Создан боевой кошелёк CoinRemitter (не TCN)
- [ ] В `.env` заданы `COINREMITTER_API_KEY`, `COINREMITTER_API_PASSWORD`, `COINREMITTER_COIN`
- [ ] `SITE_URL` — публичный HTTPS-URL, по которому доступен backend
- [ ] `FRONTEND_SITE_URL` — публичный HTTPS-URL фронтенда
- [ ] Webhook отвечает 200 на POST (проверка через `curl`)
- [ ] `DJANGO_ALLOWED_HOSTS` включает домен backend
- [ ] Nginx (или другой reverse proxy) проксирует `/api/` на backend
- [ ] SSL сертификаты настроены
- [ ] Read-only reconciliation не показывает drift/provider_unavailable

---

## 7. Dummy-режим для локальной разработки

Dummy не включается самим `DEBUG`. Он активируется только явным
`CRYPTO_DUMMY_MODE=1` и используется после ошибки CoinRemitter. При
`DJANGO_DEBUG=0` Django отклоняет такую конфигурацию при старте. Значение
создаёт лишь локальный pending-инвойс и не должно использоваться для проверки
webhook, списания остатков или production-платежей.

---

## 8. Устранение неполадок

| Проблема | Решение |
|----------|---------|
| "Maximum 10 TCN" | Используется TCN; сумма в TCN > 10. Уменьшите сумму или перейдите на боевую монету. |
| "Invalid notify url" | Webhook возвращает не 200. Проверьте доступность URL, trailing slash, Nginx. |
| Django не стартует с `CRYPTO_DUMMY_MODE` | Dummy запрещён при `DJANGO_DEBUG=0`; установите `CRYPTO_DUMMY_MODE=0`. |
| Нет редиректа после оплаты | `success_url`/`fail_url` не передаются (localhost) или указаны неверно. Задайте публичный `FRONTEND_SITE_URL`. |
| Callback отсутствует при localhost/ngrok | Используйте публичный staging/tunnel без interstitial; эти URL намеренно не передаются CoinRemitter. |

---

## 9. Ссылки

- [CoinRemitter API](https://api.coinremitter.com/)
- [Документация USDT TRC20](https://coinremitter.com/docs/api/v3/USDTTRC20)
- [Список поддерживаемых монет](https://coinremitter.com/docs)
