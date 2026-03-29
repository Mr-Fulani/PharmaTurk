import uuid
import logging
from django.conf import settings
from .models import User

import hashlib
import hmac
import time
import operator
from urllib.parse import unquote

logger = logging.getLogger(__name__)

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
    auth_date = int(auth_data.get('auth_date', 0))
    if time.time() - auth_date > 86400:
        return False
        
    return True

def generate_telegram_sync_token(user: User) -> str:
    """Генерирует и сохраняет новый токен для привязки Telegram"""
    token = uuid.uuid4().hex
    user.telegram_sync_token = token
    user.save(update_fields=['telegram_sync_token'])
    return token

def process_telegram_webhook(payload: dict) -> bool:
    """Обрабатывает входящий вебхук от Telegram бота"""
    try:
        message = payload.get('message', {})
        text = message.get('text', '').strip()
        logger.info(
            "Telegram webhook process: text=%r, from_id=%s",
            text[:50] if text else None,
            message.get('from', {}).get('id'),
        )
        from_user = message.get('from', {})
        
        telegram_id = str(from_user.get('id', ''))
        telegram_username = from_user.get('username', '')
        chat_id = message.get('chat', {}).get('id')
        
        if not text.startswith('/start ') or not telegram_id or not chat_id:
            return False
            
        token = text.replace('/start ', '').strip()
        
        # Находим пользователя по токену
        user = User.objects.filter(telegram_sync_token=token).first()
        if not user:
            logger.warning(f"Telegram webhook: user not found for token {token}")
            _send_telegram_message(chat_id, "❌ Неверный или устаревший код привязки.")
            return False
            
        # Привязываем Telegram
        user.telegram_id = telegram_id
        if telegram_username:
            user.telegram_username = telegram_username
            
        # Очищаем токен после успешной привязки
        user.telegram_sync_token = None
        user.save(update_fields=['telegram_id', 'telegram_username', 'telegram_sync_token'])
        
        logger.info(f"Telegram webhook: linked user {user.id} to telegram_id {telegram_id}")
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
    except Exception as e:
        logger.error(f"Failed to send telegram message to {chat_id}: {e}")
