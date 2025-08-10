"""Задачи Celery для каталога: обновление цен и остатков.

В MVP-версии реализованы заглушки, которые позже будут интегрированы с парсером.
"""
from __future__ import annotations

from celery import shared_task


@shared_task
def refresh_stock() -> str:
    """Обновляет данные о наличии товаров (заглушка)."""
    return "stock refreshed"


@shared_task
def refresh_prices() -> str:
    """Обновляет цены на товары с учетом наценок/акций (заглушка)."""
    return "prices refreshed"

