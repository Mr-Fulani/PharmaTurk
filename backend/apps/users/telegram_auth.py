import hashlib
import hmac
import logging
import time
import uuid

from django.conf import settings
from django.db import transaction

from .models import User

logger = logging.getLogger(__name__)

TELEGRAM_SYNC_TOKEN_MAX_AGE_SECONDS = 15 * 60
# Кнопка и команды отписки от напоминаний о Списке заявки (apps/orders/cart_reminders.py)
CART_REMINDERS_OFF_CALLBACK = "cart_reminders_off"
CART_REMINDERS_STOP_COMMANDS = ("/stop", "/stop_reminders")
TELEGRAM_SYNC_TOKEN_FUTURE_SKEW_SECONDS = 60
_TELEGRAM_SYNC_TOKEN_SIGNATURE_HEX_LENGTH = 24


def _telegram_sync_token_signature(payload: str) -> str:
    """Return a domain-separated 96-bit HMAC for a compact Telegram deep-link token."""
    secret = str(settings.SECRET_KEY).encode("utf-8")
    message = f"telegram-sync-token:{payload}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()[
        :_TELEGRAM_SYNC_TOKEN_SIGNATURE_HEX_LENGTH
    ]


def validate_telegram_sync_token(token: str, *, now: float | None = None) -> bool:
    """Validate token structure, HMAC and its 15-minute lifetime."""
    try:
        issued_hex, nonce, supplied_signature = str(token or "").split("_")
        if len(nonce) != 24 or len(supplied_signature) != 24:
            return False
        int(nonce, 16)
        int(supplied_signature, 16)
        issued_at = int(issued_hex, 16)
    except (TypeError, ValueError):
        return False

    payload = f"{issued_hex}_{nonce}"
    expected_signature = _telegram_sync_token_signature(payload)
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return False

    current_time = time.time() if now is None else now
    age_seconds = current_time - issued_at
    return (
        -TELEGRAM_SYNC_TOKEN_FUTURE_SKEW_SECONDS
        <= age_seconds
        <= TELEGRAM_SYNC_TOKEN_MAX_AGE_SECONDS
    )


def validate_telegram_data(data: dict) -> bool:
    """
    Валидация данных от виджета Telegram Login.
    Смотри: https://core.telegram.org/widgets/login
    """
    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is not configured")
        return False
        
    secret = hashlib.sha256(bot_token.encode('utf-8')).digest()
    
    # Извлекаем и удаляем хэш из данных
    auth_data = data.copy()
    received_hash = auth_data.pop('hash', None)
    
    if not received_hash:
        return False
        
    # Формируем строку для проверки (сортировка ключей по алфавиту)
    # Исправление линтера: сортируем список кортежей
    try:
        sorted_items = sorted(list(auth_data.items()), key=lambda x: x[0])
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted_items
        )
    except Exception as e:
        logger.error(f"Error sorting auth_data: {e}")
        return False
    
    # Вычисляем HMAC-SHA-256
    expected_hash = hmac.new(
        secret, 
        data_check_string.encode('utf-8'), 
        hashlib.sha256
    ).hexdigest()
    
    # Проверяем хэш
    if not hmac.compare_digest(expected_hash, received_hash):
        return False
        
    # Проверяем что авторизация не старше 24 часов (auth_date в unix time)
    try:
        auth_date = int(auth_data.get('auth_date', 0))
    except (TypeError, ValueError):
        return False
    age_seconds = time.time() - auth_date
    if age_seconds < -60 or age_seconds > 86400:
        return False
        
    return True


def generate_telegram_sync_token(user: User) -> str:
    """Generate a revocable one-time token that expires after 15 minutes."""
    issued_hex = format(int(time.time()), "x")
    nonce = uuid.uuid4().hex[:24]
    payload = f"{issued_hex}_{nonce}"
    token = f"{payload}_{_telegram_sync_token_signature(payload)}"
    user.telegram_sync_token = token
    user.save(update_fields=['telegram_sync_token'])
    return token


def process_telegram_webhook(payload: dict) -> bool:
    """Обрабатывает входящий вебхук от Telegram бота"""
    try:
        callback = payload.get('callback_query')
        if callback:
            return _process_cart_reminders_callback(callback)

        message = payload.get('message', {})
        text = message.get('text', '').strip()
        if text.split('@', 1)[0].lower() in CART_REMINDERS_STOP_COMMANDS:
            return _process_cart_reminders_stop(message)
        logger.info(
            "Telegram webhook process: has_start_command=%s, from_id=%s",
            text.startswith('/start '),
            message.get('from', {}).get('id'),
        )
        from_user = message.get('from', {})
        
        telegram_id = str(from_user.get('id', ''))
        telegram_username = from_user.get('username', '')
        chat_id = message.get('chat', {}).get('id')
        chat_type = message.get('chat', {}).get('type')
        
        if (
            not text.startswith('/start ')
            or not telegram_id
            or not chat_id
            or chat_type != "private"
            or str(chat_id) != telegram_id
        ):
            return False
            
        token = text.replace('/start ', '').strip()

        if not validate_telegram_sync_token(token):
            # Invalidates legacy UUID tokens and removes a matching expired
            # token without ever logging the secret value.
            User.objects.filter(telegram_sync_token=token).update(
                telegram_sync_token=None
            )
            logger.warning("Telegram webhook: invalid or expired sync token")
            _send_telegram_message(chat_id, "❌ Неверный или устаревший код привязки.")
            return False

        failure_reason = None
        user = None
        with transaction.atomic():
            user = User.objects.filter(telegram_sync_token=token).first()
            if not user:
                failure_reason = "invalid"
            elif (
                User.objects.filter(telegram_id=telegram_id)
                .exclude(pk=user.pk)
                .exists()
            ):
                failure_reason = "already-linked"
            else:
                # Conditional update makes the token single-use even when two
                # Telegram deliveries race each other.
                claimed = User.objects.filter(
                    pk=user.pk,
                    telegram_sync_token=token,
                ).update(telegram_sync_token=None)
                if claimed != 1:
                    failure_reason = "invalid"
                else:
                    user.telegram_id = telegram_id
                    if telegram_username:
                        user.telegram_username = telegram_username
                    user.telegram_notifications = True
                    user.telegram_sync_token = None
                    user.save(
                        update_fields=[
                            'telegram_id',
                            'telegram_username',
                            'telegram_notifications',
                            'telegram_sync_token',
                        ]
                    )

        if failure_reason == "already-linked":
            logger.warning("Telegram webhook: Telegram account is already linked")
            _send_telegram_message(
                chat_id,
                "❌ Этот Telegram уже привязан к другому аккаунту.",
            )
            return False

        if failure_reason or user is None:
            logger.warning("Telegram webhook: invalid or already used sync token")
            _send_telegram_message(chat_id, "❌ Неверный или устаревший код привязки.")
            return False

        logger.info(
            "Telegram webhook: linked user %s to telegram_id %s",
            user.id,
            telegram_id,
        )
        _send_telegram_message(
            chat_id, 
            "✅ Ваш Telegram успешно привязан к аккаунту Mudaroba!\n"
            "Теперь вы будете получать уведомления о заказах и чеки прямо сюда."
        )
        return True
        
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        return False


def _disable_cart_reminders(telegram_id: str, chat_id, language_code: str) -> bool:
    """Отписывает от напоминаний о Списке заявки аккаунт, к которому привязан этот Telegram."""
    updated = User.objects.filter(telegram_id=telegram_id).update(cart_reminders_enabled=False)
    is_en = (language_code or "").lower().startswith("en")
    if updated:
        text = (
            "🔕 Request list reminders are off. Messages about your requests will keep coming. "
            "You can turn reminders back on in your profile on mudaroba.com."
            if is_en else
            "🔕 Напоминания о Списке заявки отключены. Сообщения о ваших заявках будут приходить как раньше. "
            "Включить напоминания снова можно в профиле на mudaroba.com."
        )
    else:
        text = (
            "This Telegram is not linked to a Mudaroba account."
            if is_en else
            "Этот Telegram не привязан к аккаунту Mudaroba."
        )
    _send_telegram_message(chat_id, text)
    logger.info("Telegram: cart reminders disabled for %s account(s)", updated)
    return bool(updated)


def _process_cart_reminders_stop(message: dict) -> bool:
    """Команда /stop в личном чате с ботом."""
    from_user = message.get('from', {})
    telegram_id = str(from_user.get('id', ''))
    chat = message.get('chat', {})
    if not telegram_id or chat.get('type') != 'private' or str(chat.get('id')) != telegram_id:
        return False
    return _disable_cart_reminders(telegram_id, chat.get('id'), from_user.get('language_code', ''))


def _process_cart_reminders_callback(callback: dict) -> bool:
    """Кнопка «Не присылать напоминания» под напоминанием; from.id — тот, кто нажал."""
    if callback.get('data') != CART_REMINDERS_OFF_CALLBACK:
        return False
    from_user = callback.get('from', {})
    telegram_id = str(from_user.get('id', ''))
    chat = (callback.get('message') or {}).get('chat', {})
    if not telegram_id or str(chat.get('id', '')) != telegram_id:
        return False
    _answer_callback_query(callback.get('id'))
    return _disable_cart_reminders(telegram_id, chat.get('id'), from_user.get('language_code', ''))


def _answer_callback_query(callback_id) -> None:
    """Убирает «часики» с нажатой кнопки."""
    try:
        import requests
        bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        if not bot_token or not callback_id:
            return
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
            timeout=5,
        )
    except Exception:
        logger.error("Failed to answer Telegram callback query")


def _send_telegram_message(chat_id: int, text: str) -> None:
    """Отправка сообщения в Telegram"""
    try:
        import requests
        bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            return
            
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
        }, timeout=5)
    except Exception:
        # requests errors may include the full Telegram URL with the bot token.
        logger.error("Failed to send Telegram message")
