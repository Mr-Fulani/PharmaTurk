# Криптоплатежи (CoinRemitter)

Инструкция по настройке и развёртыванию криптовалютной оплаты через CoinRemitter в режиме разработки и на боевом сервере.

---

## 1. Обзор

- **Провайдер:** [CoinRemitter](https://coinremitter.com/)
- **Поддерживаемые монеты:** USDT (TRC20/ERC20), BTC, ETH, LTC, BCH, DOGE, BNB, TRX, USDC ERC20 и др. (полный список в [документации](https://coinremitter.com/docs))
- **Режим тестирования:** TCN (Test Coin) — лимит 10 TCN на инвойс
- **Архитектура:** Один кошелёк (API key) = одна монета. Для нескольких монет нужны отдельные кошельки и переключение по настройкам.

---

## 2. Режим разработки (localhost / ngrok)

### 2.1. Тестовая монета TCN

1. Зарегистрируйтесь на [CoinRemitter](https://merchant.coinremitter.com/signup)
2. Создайте кошелёк **Test Coin (TCN)**
3. Получите API Key и Password в настройках кошелька
4. В `.env`:
   ```env
   COINREMITTER_API_KEY=ваш_api_key
   COINREMITTER_API_PASSWORD=ваш_пароль
   COINREMITTER_COIN=TCN
   SITE_URL=http://localhost:3001
   ```

**Ограничение TCN:** максимум 10 TCN на один инвойс. Сумма заказа в фиате конвертируется в TCN — следите, чтобы не превысить лимит.

### 2.2. Доступ через ngrok (мобильные устройства, внешние тесты)

1. Запустите туннель на **frontend** (порт 3001):
   ```bash
   ngrok http 3001
   ```
2. В `.env` укажите ngrok-URL:
   ```env
   SITE_URL=https://ваш-поддомен.ngrok-free.dev
   ```
3. Frontend автоматически добавляет заголовок `ngrok-skip-browser-warning` для обхода страницы предупреждения ngrok free tier.

**Важно:** CoinRemitter проверяет `notify_url` POST-запросом. URL должен быть публично доступен. При `SITE_URL` с localhost webhook не передаётся — инвойс создаётся, но уведомления о статусе не приходят. При ngrok всё работает.

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

# URL для webhook (должен вести на backend)
# Вариант A: backend на отдельном поддомене
SITE_URL=https://api.pharmaturk.ru

# Вариант B: backend за тем же доменом (Nginx проксирует /api)
SITE_URL=https://pharmaturk.ru

# URL фронтенда (success_url, fail_url — редирект после оплаты)
FRONTEND_SITE_URL=https://pharmaturk.ru
```

### 3.4. Схема URL

| Переменная         | Назначение                    | Пример                    |
|--------------------|-------------------------------|---------------------------|
| `SITE_URL`         | Базовый URL backend (webhook) | `https://api.pharmaturk.ru` |
| `FRONTEND_SITE_URL`| URL фронтенда (редиректы)     | `https://pharmaturk.ru`   |

Формируемые URL:
- `notify_url`: `{SITE_URL}/api/payments/crypto/webhook/` — CoinRemitter шлёт сюда POST при смене статуса
- `success_url`: `{FRONTEND_SITE_URL}/checkout-success?number=...` — редирект после успешной оплаты
- `fail_url`: `{FRONTEND_SITE_URL}/checkout-crypto?number=...` — редирект при отмене

### 3.5. Nginx и маршрутизация

Webhook должен доходить до backend. Пример конфигурации:

**Backend на api.pharmaturk.ru:**
```nginx
server {
    listen 443 ssl http2;
    server_name api.pharmaturk.ru;
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

**Frontend и API на одном домене (pharmaturk.ru):**
```nginx
server {
    listen 443 ssl http2;
    server_name pharmaturk.ru www.pharmaturk.ru;
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
В этом случае `SITE_URL=https://pharmaturk.ru` — запросы на `/api/payments/crypto/webhook/` пойдут на backend.

### 3.6. Проверка webhook

```bash
curl -X POST https://ваш-домен/api/payments/crypto/webhook \
  -H "Content-Type: application/json" \
  -d '{}'
```
Ожидается ответ `200 OK` с телом `{"ok":true}` (валидационный ping).

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

---

## 7. Режим dummy (fallback)

При ошибке CoinRemitter (неверный webhook, лимиты, сеть) и `DEBUG=1` используется тестовый режим с фиктивным адресом `TDevWallet123456789012345678901`. В production при ошибке API инвойс не создаётся, пользователь получает сообщение об ошибке.

---

## 8. Устранение неполадок

| Проблема | Решение |
|----------|---------|
| "Maximum 10 TCN" | Используется TCN; сумма в TCN > 10. Уменьшите сумму или перейдите на боевую монету. |
| "Invalid notify url" | Webhook возвращает не 200. Проверьте доступность URL, trailing slash, Nginx. |
| Dummy-адрес в production | Ошибка CoinRemitter. Проверьте логи backend, ключи, webhook. |
| Нет редиректа после оплаты | `success_url`/`fail_url` не передаются (localhost) или указаны неверно. Задайте публичный `FRONTEND_SITE_URL`. |
| 404 на /api/... через ngrok | Добавлен заголовок `ngrok-skip-browser-warning` в `api.ts` — проверьте, что frontend обновлён. |

---

## 9. Ссылки

- [CoinRemitter API](https://api.coinremitter.com/)
- [Документация USDT TRC20](https://coinremitter.com/docs/api/v3/USDTTRC20)
- [Список поддерживаемых монет](https://coinremitter.com/docs)
