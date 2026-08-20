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
        message = payload.get('message', {})
        text = message.get('text', '').strip()
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
