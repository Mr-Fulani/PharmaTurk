"""Задачи маркетинга: публикация очереди Telegram-канала по расписанию."""

from config.celery import app


@app.task(name="marketing.publish_telegram_channel")
def publish_telegram_channel() -> int:
    """Раз в 10 минут: если настало время публикации из настроек — один пост из очереди."""
    from .telegram_channel import run_schedule

    return run_schedule()
