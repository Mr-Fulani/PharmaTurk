"""Ручной запуск AI-задач (тратят токены OpenAI). Только через админку."""
import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.utils.html import format_html

from .tasks import (
    process_uncategorized,
    process_without_description,
    retry_failed_processing,
    cleanup_old_ai_logs,
)

logger = logging.getLogger(__name__)


@require_http_methods(["GET", "POST"])
def ai_manual_tasks_view(request):
    """Страница ручного запуска AI-задач (Admin → AI → Задачи вручную)."""
    if not request.user.is_staff:
        return redirect("admin:login")

    context = {
        "title": "AI-задачи (ручной запуск)",
        "subtitle": "Эти задачи тратят токены OpenAI. Запускать только по необходимости.",
    }

    if request.method == "POST":
        action = request.POST.get("action")
        process_all = request.POST.get("process_all") == "1"

        if action == "uncategorized":
            limit = None if process_all else int(request.POST.get("limit", 50))
            task = process_uncategorized.delay(limit=limit or 99999)
            limit_text = "все" if process_all else f"до {limit} шт."
            logger.info(
                "Manual: process_uncategorized started, limit=%s, task_id=%s, user=%s",
                limit or "all",
                task.id,
                request.user,
            )
            messages.success(
                request,
                f"Запущено: категоризация товаров без категории ({limit_text}). "
                f"Задача: {task.id}. Результаты появятся в логах AI.",
            )
        elif action == "without_description":
            limit = None if process_all else int(request.POST.get("limit", 50))
            task = process_without_description.delay(limit=limit or 99999)
            limit_text = "все" if process_all else f"до {limit} шт."
            logger.info(
                "Manual: process_without_description started, limit=%s, task_id=%s, user=%s",
                limit or "all",
                task.id,
                request.user,
            )
            messages.success(
                request,
                f"Запущено: генерация описаний ({limit_text}). "
                f"Задача: {task.id}. Результаты в логах AI.",
            )
        elif action == "retry_failed":
            limit = None if process_all else int(request.POST.get("limit", 30))
            task = retry_failed_processing.delay(limit=limit or 99999)
            limit_text = "все" if process_all else f"до {limit} шт."
            logger.info(
                "Manual: retry_failed_processing started, limit=%s, task_id=%s, user=%s",
                limit or "all",
                task.id,
                request.user,
            )
            messages.success(
                request,
                f"Запущено: повтор неудачных AI-обработок ({limit_text}). "
                f"Задача: {task.id}.",
            )
        elif action == "cleanup_logs":
            cleanup_all = request.POST.get("cleanup_all") == "1"
            days = 0 if cleanup_all else int(request.POST.get("days", 90))
            task = cleanup_old_ai_logs.delay(days=days)
            logger.info(
                "Manual: cleanup_old_ai_logs started, days=%s, task_id=%s, user=%s",
                days,
                task.id,
                request.user,
            )
            days_text = "все" if cleanup_all else f"{days} дней"
            messages.success(
                request,
                f"Запущено: очистка логов старше {days_text}. Задача: {task.id}. "
                "Не тратит токены.",
            )
        return redirect("ai_manual_tasks")

    return render(request, "admin/ai/manual_tasks.html", context)
