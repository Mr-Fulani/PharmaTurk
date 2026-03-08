# Уведомления и чеки — PharmaTurk

## Обзор

При создании заказа автоматически запускается цепочка задач Celery:

```
Создание заказа (views.py)
    │
    ├──[КРИПТО]─→ Платёж создаётся → NowPayments webhook → send_order_receipt_task
    │
    └──[COD/остальные]─→ send_order_receipt_task ──link──→ notify_new_order_telegram
```

---

## 1. Email-уведомление с чеком (`send_order_receipt_task`)

**Файл:** `backend/apps/orders/tasks.py`

### Что делает:
1. Генерирует красивый HTML-чек из шаблона `backend/templates/emails/order_receipt.html`
2. Генерирует PDF через **WeasyPrint** и загружает его в **Cloudflare R2**
3. Сохраняет URL чека в поле `order.receipt_url`
4. Отправляет email покупателю с PDF-вложением

### Шаблон письма (`emails/order_receipt.html`):
- **Шапка**: тёмный фон (#0c1628) с логотипом PharmaTurk, золотой полумесяц
- **Данные**: покупатель/продавец, список товаров, доставка, оплата, итоги
- **Футер**: иконки соцсетей (Telegram, WhatsApp, Instagram) + контакты продавца

### Соцсети в письме:
Ссылки берутся **автоматически** из `FooterSettings` в Django админке:
- Панель администратора → **Settings → Footer Settings**
- Поля: `telegram_url`, `whatsapp_url`, `instagram_url`

> Если поля пустые — иконки всё равно отображаются, но ведут на `#` (кликабельны, но никуда не ведут).

---

## 2. Telegram-уведомление (`notify_new_order_telegram`)

**Файл:** `backend/apps/orders/tasks.py`

### Что делает:
Запускается **автоматически после** `send_order_receipt_task` через Celery chain `link`.

1. Скачивает готовый PDF из `order.receipt_url` (не перегенерирует!)
2. Отправляет уведомление **админу** — через `sendDocument` с PDF-файлом чека
3. Отправляет уведомление **покупателю** — тоже с PDF-файлом чека

### Настройка:

| Параметр | Где задаётся | Описание |
|----------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | `.env` | Токен вашего бота (получить у @BotFather) |
| `TELEGRAM_CHAT_ID` | `.env` | Chat ID **администратора** (получить у @userinfobot) |
| `telegram_id` пользователя | Профиль в Django Admin | Числовой Chat ID покупателя |

> ⚠️ Покупатель должен **сначала написать боту /start**, иначе бот не сможет отправить ему сообщение.

### Формат уведомления:
- **Администратор**: всегда на русском, с номером заказа, суммой, способом оплаты и доставки
- **Покупатель**: на языке заказа (ru/en), с информацией о заказе

---

## 3. Имя PDF-файла

Формат: `receipt_YYYYMMDD_НОМЕРЗАКАЗА_ИМЯ.pdf`

**Пример:** `receipt_20260308_ECFDD7C1F885_Enver_Pasha.pdf`

- `YYYYMMDD` — дата создания чека
- `НОМЕРЗАКАЗА` — уникальный hex-номер заказа
- `ИМЯ` — имя контакта из заказа (очищено от спецсимволов, до 20 символов)

---

## 4. Ручная отправка чека

Пользователь может сам запросить чек на email через кнопку **"Send receipt"** на странице `checkout-success`.

**API endpoint:** `POST /api/orders/send-receipt/{number}/`

**Тело запроса:**
```json
{
  "email": "buyer@example.com",
  "locale": "ru"
}
```

---

## 5. Ключевые файлы

| Файл | Назначение |
|------|-----------|
| `backend/apps/orders/tasks.py` | Celery-задачи: email + Telegram |
| `backend/apps/orders/services.py` | Генерация payload чека, рендер HTML, сохранение PDF в R2 |
| `backend/templates/emails/order_receipt.html` | HTML-шаблон письма |
| `backend/apps/orders/views.py` | Точка запуска цепочки задач при создании заказа |
| `backend/apps/settings/models.py` | `FooterSettings` — соцсети для письма |

---

## 6. Проверка работоспособности

```bash
# Проверить отправку чека вручную
docker compose exec backend bash -c "cd /app && poetry run python manage.py shell -c \"
from apps.orders.tasks import send_order_receipt_task
from apps.orders.models import Order
order = Order.objects.latest('created_at')
send_order_receipt_task(order.id, 'test@example.com', locale='ru')
\""

# Проверить Telegram-уведомление
docker compose exec backend bash -c "cd /app && poetry run python manage.py shell -c \"
from apps.orders.tasks import notify_new_order_telegram
from apps.orders.models import Order
order = Order.objects.latest('created_at')
notify_new_order_telegram(order_id=order.id, locale='ru')
\""
```
