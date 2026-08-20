# Уведомления и чеки Mudaroba

Документ описывает фактическое поведение Django/Celery на 20 августа 2026 года.

## Потоки событий

```text
Обычный заказ
  └─ transaction.on_commit
       ├─ send_order_receipt_task (если есть email)
       └─ notify_new_order_telegram (независимая задача)

Криптозаказ
  └─ CoinRemitter webhook
       └─ authenticated invoice/get + атомарная сверка
            ├─ paid: списание остатков один раз
            │        └─ notify_crypto_payment_confirmed
            │             └─ send_order_receipt_task (если есть email)
            └─ expired/cancelled: notify_crypto_payment_expired
```

Тело публичного webhook служит только подсказкой для поиска инвойса. Статус,
идентификаторы, привязка к заказу и суммы повторно проверяются через
аутентифицированный CoinRemitter API. Повторный callback не списывает остатки и
не отправляет подтверждение второй раз; оплаченный заказ не понижается поздним
`expired`/`cancelled`.

## Email и PDF-чек

Задача `send_order_receipt_task` находится в
`backend/apps/orders/tasks.py` и:

1. строит payload и HTML из `backend/templates/emails/order_receipt.html`;
2. создаёт PDF через WeasyPrint;
3. загружает PDF в Cloudflare R2/S3 и сохраняет `order.receipt_url`;
4. прикладывает PDF к письму и отправляет его через настроенный Django email
   backend/API provider;
5. повторяет задачу при ошибке генерации, R2 или отправки.

Для PDF обязательны корректные `R2_*`: без endpoint или bucket генератор
возвращает пустой результат, после чего Celery-задача уходит в retry. Рендерер
намеренно запрещает любые внешние ресурсы; это ограничивает SSRF и сетевые
зависания WeasyPrint. Логотипы и стили чека должны быть self-contained.

Email берётся сначала из `order.contact_email`, затем из профиля обычного
пользователя. Адрес staff/superuser как fallback не используется.

Имя PDF: `receipt_YYYYMMDD_НОМЕР_ИМЯ.pdf`.

## Telegram

`notify_new_order_telegram` уведомляет администратора и, если пользователь
включил `telegram_notifications`, покупателя. Задача не загружает
`order.receipt_url` по HTTP: она читает детерминированный HMAC-namespaced объект
`receipts/{digest}/{order.number}.pdf` напрямую из доверенного R2, ограничивает
его 5 МБ и проверяет сигнатуру PDF. Legacy-путь без digest больше не читается;
новые URL невозможно угадать только по номеру заказа. При
отсутствии или ошибке чтения чек создаётся заново; уведомление при
необходимости отправляется без вложения. Старые объекты
`receipts/{order.number}.pdf` нужно отдельно удалить/переместить в R2 по
dry-run inventory — изменение кода не удаляет внешние объекты автоматически.

Инвентаризация по умолчанию ничего не удаляет и не печатает PII-содержащие
ключи:

```bash
cd backend
poetry run python manage.py cleanup_legacy_receipts
```

Сначала зафиксируйте количество/объём, проверьте backup, retention policy и
provider audit logs. `--show-keys` используйте только в приватном терминале:
ключи содержат номера заказов. Перемещение разрешается лишь с тремя явными
параметрами и только после полной инвентаризации:

```bash
poetry run python manage.py cleanup_legacy_receipts \
  --apply \
  --confirm-bucket "точное-имя-bucket" \
  --quarantine-bucket "private-backup-bucket" \
  --quarantine-prefix "security-quarantine/legacy-receipts-YYYY-MM-DD-random"
```

Команда сначала копирует все плоские legacy PDF в отдельный непредсказуемый
quarantine-префикс и только после успешного копирования всего inventory удаляет
исходные предсказуемые ключи. Новые HMAC-namespaced ключи не затрагиваются.
Если отдельный private/non-CDN bucket недоступен, параметр
`--quarantine-bucket` можно опустить, но same-bucket copy остаётся доступным по
точному URL и полагается на непредсказуемость quarantine prefix.
Dry-run 20 августа 2026 года без
`--show-keys` просмотрел 6 объектов и нашёл 6 legacy PDF суммарным размером
125568 bytes. Отдельный повторный dry-run текущего локального `dev/` namespace
нашёл 4 legacy PDF/83391 bytes; это не отменяет inventory другого prefix. Оба
набора требуют отдельного private backup/retention решения до удаления.

Для администратора нужны `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`. Для
покупателя дополнительно нужны привязанный `User.telegram_id`, включённая
настройка уведомлений и предварительный `/start` у бота.

Подтверждение и webhook-истечение криптоплатежа отправляются отдельными задачами
из `backend/apps/payments/tasks.py`. Периодическая cleanup-задача только массово
помечает просроченные платежи и сама уведомления не отправляет. При
подтверждении дополнительно планируется email-чек.

## Ручные API

Из-за текущего префикса router фактические маршруты имеют двойное `orders`:

- `GET /api/orders/orders/receipt/{number}?format=html`;
- `POST /api/orders/orders/send-receipt/{number}`.

Оба endpoint требуют JWT и возвращают/отправляют чек только владельцу заказа.
Получатель повторной отправки не принимается из тела запроса: используется
`contact_email` заказа либо подтверждённый профильный email. Отправка ограничена
user throttle, поэтому endpoint нельзя использовать как произвольный email
relay.
Для POST можно передать:

```json
{
  "email": "buyer@example.com",
  "locale": "ru"
}
```

Двойной префикс сохранён для совместимости с frontend; его устранение требует
отдельной versioned API-миграции.

## Настройки и эксплуатационная проверка

Ссылки Telegram/WhatsApp/Instagram для письма берутся из первого
`FooterSettings`; пустые WhatsApp/Instagram сейчас превращаются в `#`.

Без запуска Docker можно проверить синтаксис и unit-тесты. Полная проверка
должна выполняться на staging с PostgreSQL, Redis, Celery worker, тестовым R2,
SMTP/API-провайдером и Telegram:

1. создать обычный и криптозаказ;
2. убедиться, что задача ставится только после commit;
3. проверить PDF в R2 и вложение письма;
4. повторить один и тот же webhook и убедиться в отсутствии повторного
   списания/уведомления;
5. проверить пользователя с включёнными и выключенными Telegram-уведомлениями.

## Ключевые файлы

| Файл | Назначение |
| --- | --- |
| `backend/apps/orders/tasks.py` | Email и Telegram обычного заказа |
| `backend/apps/orders/services.py` | Payload, HTML, PDF и R2 |
| `backend/apps/orders/views.py` | Создание заказа и ручные receipt API |
| `backend/apps/payments/views.py` | Безопасная сверка CoinRemitter webhook |
| `backend/apps/payments/tasks.py` | События подтверждения/истечения оплаты |
| `backend/templates/emails/order_receipt.html` | HTML-шаблон письма |
