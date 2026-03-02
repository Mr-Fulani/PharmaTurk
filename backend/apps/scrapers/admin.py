"""Админ-интерфейс для управления парсерами."""

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.http import HttpResponseRedirect

from django.db.models import Count, Case, When, IntegerField
from apps.catalog.models import Product, Category
from .models import (
    ScraperConfig,
    ScrapingSession,
    CategoryMapping,
    BrandMapping,
    ScrapedProductLog,
    InstagramScraperTask,
    SiteScraperTask,
)
from .tasks import run_scraper_task


class InstagramScraperTaskForm(forms.ModelForm):
    """Форма задачи Instagram с проверкой: указан post_url или username."""

    class Meta:
        model = InstagramScraperTask
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        post_url = cleaned.get("post_url") or ""
        username = (cleaned.get("instagram_username") or "").strip()
        if not post_url and not username:
            raise ValidationError(
                _("Укажите либо ссылку на пост (Ссылка на пост), либо Instagram username.")
            )
        return cleaned


@admin.register(ScraperConfig)
class ScraperConfigAdmin(admin.ModelAdmin):
    """Админ для конфигураций парсеров."""

    list_display = [
        "name",
        "status_badge",
        "base_url",
        "priority",
        "success_rate_display",
        "last_run_display",
        "actions_column",
    ]
    list_filter = [
        "status",
        "is_enabled",
        "sync_enabled",
        "use_proxy",
        "ai_on_create_enabled",
        "ai_on_update_enabled",
        "created_at",
    ]
    search_fields = ["name", "base_url", "description"]
    ordering = ["priority", "name"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    fieldsets = [
        ("Основная информация", {"fields": ["name", "parser_class", "base_url", "description", "default_category"]}),
        ("Статус и настройки", {"fields": ["status", "is_enabled", "priority"]}),
        (
            "Параметры парсинга",
            {
                "fields": [
                    ("delay_min", "delay_max"),
                    ("timeout", "max_retries"),
                    ("max_pages_per_run", "max_products_per_run", "max_images_per_product"),
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Расписание",
            {"fields": ["sync_enabled", "sync_interval_hours"], "classes": ["collapse"]},
        ),
        (
            "AI обработка",
            {"fields": ["ai_on_create_enabled", "ai_on_update_enabled"], "classes": ["collapse"]},
        ),
        (
            "Дополнительные настройки",
            {
                "fields": [
                    "use_proxy",
                    "user_agent",
                    "headers",
                    "cookies",
                    "scraper_username",
                    "scraper_password",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Статистика",
            {
                "fields": [
                    "last_run_at",
                    "last_success_at",
                    "last_error_at",
                    "total_runs",
                    "successful_runs",
                    "total_products_scraped",
                ],
                "classes": ["collapse"],
                "description": "Статистика обновляется автоматически",
            },
        ),
    ]

    readonly_fields = [
        "last_run_at",
        "last_success_at",
        "last_error_at",
        "last_error_message",
        "total_runs",
        "successful_runs",
        "total_products_scraped",
    ]

    actions = ["run_selected_scrapers", "enable_scrapers", "disable_scrapers"]

    def status_badge(self, obj):
        """Отображает статус с цветным бейджем."""
        colors = {"active": "green", "inactive": "gray", "error": "red", "maintenance": "orange"}
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="color: {}; font-weight: bold;">●</span> {}',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Статус"

    def success_rate_display(self, obj):
        """Отображает процент успешных запусков."""
        try:
            rate = obj.success_rate
            if rate is None:
                return "0.0%"
            rate_float = float(rate)
            color = "green" if rate_float >= 80 else "orange" if rate_float >= 50 else "red"
            return format_html('<span style="color: {};">{:.1f}%</span>', color, rate_float)
        except (ValueError, TypeError, AttributeError):
            return "0.0%"

    success_rate_display.short_description = "Успешность"

    def last_run_display(self, obj):
        """Отображает время последнего запуска."""
        if not obj.last_run_at:
            return "Никогда"

        delta = timezone.now() - obj.last_run_at
        if delta.days > 0:
            return f"{delta.days} дн. назад"
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f"{hours} ч. назад"
        else:
            minutes = delta.seconds // 60
            return f"{minutes} мин. назад"

    last_run_display.short_description = "Последний запуск"

    def actions_column(self, obj):
        """Колонка с действиями."""
        run_url = reverse("admin:scrapers_scraperconfig_run", args=[obj.pk])
        sessions_url = (
            reverse("admin:scrapers_scrapingsession_changelist") + f"?scraper_config__id={obj.pk}"
        )

        return format_html(
            '<a href="{}" class="button">Запустить</a> ' '<a href="{}" class="button">Сессии</a>',
            run_url,
            sessions_url,
        )

    actions_column.short_description = "Действия"

    def get_urls(self):
        """Добавляем кастомные URL."""
        from django.urls import path

        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:scraper_id>/run/",
                self.admin_site.admin_view(self.run_scraper_view),
                name="scrapers_scraperconfig_run",
            ),
        ]
        return custom_urls + urls

    def run_scraper_view(self, request, scraper_id):
        """Запускает парсер."""
        try:
            scraper_config = ScraperConfig.objects.get(id=scraper_id)

            # Запускаем задачу Celery
            task = run_scraper_task.delay(scraper_id)

            messages.success(
                request, f'Парсер "{scraper_config.name}" запущен. ID задачи: {task.id}'
            )

        except ScraperConfig.DoesNotExist:
            messages.error(request, "Парсер не найден")
        except Exception as e:
            messages.error(request, f"Ошибка запуска парсера: {e}")

        return HttpResponseRedirect(reverse("admin:scrapers_scraperconfig_changelist"))

    def run_selected_scrapers(self, request, queryset):
        """Действие: запустить выбранные парсеры."""
        started_count = 0

        for scraper_config in queryset.filter(is_enabled=True):
            try:
                run_scraper_task.delay(scraper_config.id)
                started_count += 1
            except Exception as e:
                messages.error(request, f"Ошибка запуска {scraper_config.name}: {e}")

        if started_count:
            messages.success(request, f"Запущено {started_count} парсеров")

    run_selected_scrapers.short_description = "Запустить выбранные парсеры"

    def enable_scrapers(self, request, queryset):
        """Действие: включить парсеры."""
        updated = queryset.update(is_enabled=True, status="active")
        messages.success(request, f"Включено {updated} парсеров")

    enable_scrapers.short_description = "Включить выбранные парсеры"

    def disable_scrapers(self, request, queryset):
        """Действие: отключить парсеры."""
        updated = queryset.update(is_enabled=False, status="inactive")
        messages.success(request, f"Отключено {updated} парсеров")

    disable_scrapers.short_description = "Отключить выбранные парсеры"


@admin.register(SiteScraperTask)
class SiteScraperTaskAdmin(admin.ModelAdmin):
    list_display = [
        "scraper_config",
        "target_category",
        "status_badge",
        "max_pages",
        "max_products",
        "max_images_per_product",
        "products_stats",
        "ai_status_display",
        "created_at",
        "duration_display",
        "actions_column",
    ]
    list_filter = ["status", "scraper_config", "target_category", "created_at"]
    search_fields = ["scraper_config__name", "start_url", "error_message"]
    ordering = ["-created_at"]
    raw_id_fields = ["target_category"]

    fieldsets = [
        (
            "Параметры парсинга",
            {
                "fields": [
                    "scraper_config",
                    "target_category",
                    "start_url",
                    "max_pages",
                    "max_products",
                    "max_images_per_product",
                ],
                "description": "Выберите целевую категорию — товары будут сохранены в неё. Если не указана, используется категория по умолчанию из конфигурации парсера.",
            },
        ),
        (
            "Статус и результаты",
            {
                "fields": [
                    "status",
                    "products_found",
                    "products_created",
                    "products_updated",
                    "products_skipped",
                    "pages_processed",
                    "errors_count",
                ]
            },
        ),
        (
            "Временные метки",
            {"fields": ["created_at", "started_at", "finished_at"], "classes": ["collapse"]},
        ),
        ("Логи", {"fields": ["log_output", "error_message"], "classes": ["collapse"]}),
    ]

    readonly_fields = [
        "status",
        "products_found",
        "products_created",
        "products_updated",
        "products_skipped",
        "pages_processed",
        "errors_count",
        "log_output",
        "error_message",
        "created_at",
        "started_at",
        "finished_at",
    ]

    actions = ["run_site_scraping", "rerun_site_scraping", "run_ai_for_tasks"]

    def status_badge(self, obj):
        colors = {"pending": "blue", "running": "orange", "completed": "green", "failed": "red"}
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="color: {}; font-weight: bold;">●</span> {}',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Статус"

    def products_stats(self, obj):
        if obj.status == "pending":
            return "-"
        return format_html(
            '<span style="color: green;">+{}</span> / '
            '<span style="color: blue;">~{}</span> / '
            '<span style="color: gray;">-{}</span>',
            obj.products_created,
            obj.products_updated,
            obj.products_skipped,
        )

    products_stats.short_description = "Создано / Обновлено / Пропущено"

    def duration_display(self, obj):
        if obj.duration:
            total_seconds = int(obj.duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours:
                return f"{hours}ч {minutes}м"
            if minutes:
                return f"{minutes}м {seconds}с"
            return f"{seconds}с"
        return "-"

    duration_display.short_description = "Длительность"

    def ai_status_display(self, obj):
        """AI обработка: количество завершённых/всего логов для товаров задачи."""
        if not obj.session_id:
            return "—"

        from apps.ai.models import AIProcessingLog

        product_ids = list(
            ScrapedProductLog.objects.filter(
                session=obj.session,
                product__isnull=False,
                action__in=["created", "updated"],
            ).values_list("product_id", flat=True).distinct()
        )
        if not product_ids:
            return "—"

        stats = AIProcessingLog.objects.filter(product_id__in=product_ids).aggregate(
            total=Count("id"),
            completed=Count(Case(When(status__in=["completed", "approved", "moderation"], then=1), output_field=IntegerField())),
            processing=Count(Case(When(status="processing", then=1), output_field=IntegerField())),
            failed=Count(Case(When(status="failed", then=1), output_field=IntegerField())),
        )
        total = stats["total"]
        if not total:
            return format_html('<span style="color:gray;">нет логов</span>')

        completed = stats["completed"]
        processing = stats["processing"]
        failed = stats["failed"]
        pending = total - completed - processing - failed

        parts = []
        if completed:
            parts.append(f'<span style="color:green;" title="Завершено">✓{completed}</span>')
        if processing:
            parts.append(f'<span style="color:orange;" title="Обрабатывается">⏳{processing}</span>')
        if failed:
            parts.append(f'<span style="color:red;" title="Ошибка">✗{failed}</span>')
        if pending:
            parts.append(f'<span style="color:#888;" title="Ожидает">◷{pending}</span>')

        logs_url = (
            reverse("admin:ai_aiprocessinglog_changelist")
            + "?product__id__in="
            + ",".join(str(pid) for pid in product_ids)
        )
        inner = " ".join(parts)
        return format_html(
            '<a href="{}" title="Открыть логи AI">{} / {}</a>',
            logs_url,
            mark_safe(inner),
            total,
        )

    ai_status_display.short_description = "AI обработка"

    def actions_column(self, obj):
        if obj.status == "completed" and obj.session_id:
            run_ai_url = reverse("admin:scrapers_sitescrapertask_run_ai", args=[obj.pk])
            task_id_html = f'<span style="font-size:11px;color:gray;">{obj.task_id or "-"}</span>'
            return format_html(
                '{} <a href="{}" class="button" style="margin-left:4px;">Запустить AI</a>',
                task_id_html,
                run_ai_url,
            )
        return format_html("<span>{}</span>", obj.task_id or "-")

    actions_column.short_description = "ID задачи / Действия"

    def get_urls(self):
        from django.urls import path

        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:task_id>/run-ai/",
                self.admin_site.admin_view(self.run_ai_view),
                name="scrapers_sitescrapertask_run_ai",
            ),
        ]
        return custom_urls + urls

    def run_ai_view(self, request, task_id):
        try:
            task = SiteScraperTask.objects.get(id=task_id)
        except SiteScraperTask.DoesNotExist:
            messages.error(request, "Задача парсинга не найдена")
            return HttpResponseRedirect(reverse("admin:scrapers_sitescrapertask_changelist"))

        if not task.session_id:
            messages.warning(request, "У задачи нет привязанной сессии — нечего обработать AI")
            return HttpResponseRedirect(reverse("admin:scrapers_sitescrapertask_changelist"))

        product_ids = (
            ScrapedProductLog.objects.filter(
                session=task.session,
                product__isnull=False,
                action__in=["created", "updated"],
            )
            .values_list("product_id", flat=True)
            .distinct()
        )

        product_ids = list(product_ids)
        if not product_ids:
            messages.warning(request, "В задаче нет товаров для AI обработки")
            return HttpResponseRedirect(reverse("admin:scrapers_sitescrapertask_changelist"))

        from apps.ai.tasks import process_product_ai_task

        for product_id in product_ids:
            process_product_ai_task.delay(
                product_id=product_id,
                processing_type="full",
                auto_apply=False,
            )

        messages.success(
            request,
            f"Запущена AI обработка для {len(product_ids)} товаров из задачи #{task_id}. "
            "Результаты появятся в разделе «Логи AI»; применить к товару — вручную после проверки.",
        )
        return HttpResponseRedirect(reverse("admin:scrapers_sitescrapertask_changelist"))

    def run_site_scraping(self, request, queryset):
        from django.utils import timezone

        for task in queryset.filter(status="pending"):
            try:
                task.status = "running"
                task.started_at = timezone.now()
                task.finished_at = None
                task.error_message = ""
                task.log_output = ""
                task.products_found = 0
                task.products_created = 0
                task.products_updated = 0
                task.products_skipped = 0
                task.pages_processed = 0
                task.errors_count = 0
                task.save()

                celery_task = run_scraper_task.delay(
                    task.scraper_config_id,
                    start_url=task.start_url,
                    max_pages=task.max_pages,
                    max_products=task.max_products,
                    max_images_per_product=task.max_images_per_product,
                    site_task_id=task.id,
                )
                task.task_id = celery_task.id
                task.save()

                messages.success(request, f"Запущена задача для {task.scraper_config.name}")
            except Exception as e:
                task.status = "failed"
                task.error_message = str(e)
                task.finished_at = timezone.now()
                task.save()
                messages.error(request, f"Ошибка запуска задачи: {e}")

    run_site_scraping.short_description = "Запустить парсинг сайта"

    def rerun_site_scraping(self, request, queryset):
        from django.utils import timezone

        for task in queryset.exclude(status="running"):
            try:
                task.status = "running"
                task.started_at = timezone.now()
                task.finished_at = None
                task.error_message = ""
                task.log_output = ""
                task.products_found = 0
                task.products_created = 0
                task.products_updated = 0
                task.products_skipped = 0
                task.pages_processed = 0
                task.errors_count = 0
                task.save()

                celery_task = run_scraper_task.delay(
                    task.scraper_config_id,
                    start_url=task.start_url,
                    max_pages=task.max_pages,
                    max_products=task.max_products,
                    max_images_per_product=task.max_images_per_product,
                    site_task_id=task.id,
                )
                task.task_id = celery_task.id
                task.save()

                messages.success(
                    request, f"Повторно запущена задача для {task.scraper_config.name}"
                )
            except Exception as e:
                task.status = "failed"
                task.error_message = str(e)
                task.finished_at = timezone.now()
                task.save()
                messages.error(request, f"Ошибка повторного запуска: {e}")

    rerun_site_scraping.short_description = "Повторно запустить парсинг сайта"

    def run_ai_for_tasks(self, request, queryset):
        """Запустить AI обработку для всех товаров выбранных задач."""
        from apps.ai.tasks import process_product_ai_task

        total = 0
        for task in queryset.filter(session__isnull=False):
            product_ids = (
                ScrapedProductLog.objects.filter(
                    session=task.session,
                    product__isnull=False,
                    action__in=["created", "updated"],
                )
                .values_list("product_id", flat=True)
                .distinct()
            )
            for pid in product_ids:
                process_product_ai_task.delay(
                    product_id=pid,
                    processing_type="full",
                    auto_apply=False,
                )
                total += 1

        if total:
            messages.success(request, f"Запущена AI обработка для {total} товаров (auto_apply=False)")
        else:
            messages.warning(request, "Не найдено товаров для AI обработки в выбранных задачах")

    run_ai_for_tasks.short_description = "Запустить AI обработку для товаров задач"


@admin.register(ScrapingSession)
class ScrapingSessionAdmin(admin.ModelAdmin):
    """Админ для сессий парсинга."""

    list_display = [
        "scraper_config",
        "status_badge",
        "started_at",
        "duration_display",
        "products_stats",
        "pages_processed",
        "errors_count",
        "actions_column",
    ]
    list_filter = ["status", "scraper_config", "started_at", "finished_at"]
    search_fields = ["scraper_config__name", "start_url", "error_message"]
    ordering = ["-created_at"]

    fieldsets = [
        ("Основная информация", {"fields": ["scraper_config", "status", "task_id"]}),
        (
            "Параметры запуска",
            {"fields": ["start_url", "max_pages", "max_products", "max_images_per_product"]},
        ),
        (
            "Результаты",
            {
                "fields": [
                    ("products_found", "products_created"),
                    ("products_updated", "products_skipped"),
                    ("pages_processed", "errors_count"),
                ]
            },
        ),
        (
            "Временные метки",
            {"fields": ["started_at", "finished_at", "created_at"], "classes": ["collapse"]},
        ),
        ("Логи и ошибки", {"fields": ["error_message", "log_messages"], "classes": ["collapse"]}),
    ]

    readonly_fields = ["created_at", "started_at", "finished_at"]

    def status_badge(self, obj):
        """Отображает статус с цветным бейджем."""
        colors = {
            "pending": "blue",
            "running": "orange",
            "completed": "green",
            "failed": "red",
            "cancelled": "gray",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="color: {}; font-weight: bold;">●</span> {}',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Статус"

    def duration_display(self, obj):
        """Отображает продолжительность."""
        if obj.duration:
            total_seconds = int(obj.duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours:
                return f"{hours}ч {minutes}м {seconds}с"
            elif minutes:
                return f"{minutes}м {seconds}с"
            else:
                return f"{seconds}с"
        return "-"

    duration_display.short_description = "Длительность"

    def products_stats(self, obj):
        """Отображает статистику товаров."""
        return format_html(
            '<span style="color: green;">+{}</span> / '
            '<span style="color: blue;">~{}</span> / '
            '<span style="color: gray;">-{}</span>',
            int(obj.products_created),
            int(obj.products_updated),
            int(obj.products_skipped),
        )

    products_stats.short_description = "Создано / Обновлено / Пропущено"

    def actions_column(self, obj):
        run_ai_url = reverse("admin:scrapers_scrapingsession_run_ai", args=[obj.pk])
        return format_html('<a href="{}" class="button">Запустить AI</a>', run_ai_url)

    actions_column.short_description = "Действия"

    def get_urls(self):
        from django.urls import path

        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:session_id>/run-ai/",
                self.admin_site.admin_view(self.run_ai_view),
                name="scrapers_scrapingsession_run_ai",
            ),
        ]
        return custom_urls + urls

    def run_ai_view(self, request, session_id):
        try:
            session = ScrapingSession.objects.get(id=session_id)
        except ScrapingSession.DoesNotExist:
            messages.error(request, "Сессия парсинга не найдена")
            return HttpResponseRedirect(reverse("admin:scrapers_scrapingsession_changelist"))

        product_ids = (
            ScrapedProductLog.objects.filter(
                session=session,
                product__isnull=False,
                action__in=["created", "updated"],
            )
            .values_list("product_id", flat=True)
            .distinct()
        )

        product_ids = list(product_ids)
        if not product_ids:
            messages.warning(request, "В сессии нет товаров для AI обработки")
            return HttpResponseRedirect(reverse("admin:scrapers_scrapingsession_changelist"))

        from apps.ai.tasks import process_product_ai_task

        for product_id in product_ids:
            process_product_ai_task.delay(
                product_id=product_id,
                processing_type="full",
                auto_apply=False,
            )

        messages.success(
            request,
            f"Запущена AI обработка для {len(product_ids)} товаров. "
            "Результаты появятся в разделе «Логи AI»; применить к товару — вручную после одобрения.",
        )
        return HttpResponseRedirect(reverse("admin:scrapers_scrapingsession_changelist"))


@admin.register(CategoryMapping)
class CategoryMappingAdmin(admin.ModelAdmin):
    """Админ для маппинга категорий."""

    list_display = [
        "external_category_name",
        "internal_category",
        "scraper_config",
        "is_active",
        "priority",
    ]
    list_filter = ["scraper_config", "is_active", "internal_category"]
    search_fields = ["external_category_name", "internal_category__name"]
    ordering = ["scraper_config", "priority", "external_category_name"]

    fieldsets = [
        (
            "Маппинг",
            {
                "fields": [
                    "scraper_config",
                    "internal_category",
                    "external_category_name",
                    "external_category_url",
                    "external_category_id",
                ]
            },
        ),
        ("Настройки", {"fields": ["is_active", "priority"]}),
    ]


@admin.register(BrandMapping)
class BrandMappingAdmin(admin.ModelAdmin):
    """Админ для маппинга брендов."""

    list_display = [
        "external_brand_name",
        "internal_brand",
        "scraper_config",
        "is_active",
        "priority",
    ]
    list_filter = ["scraper_config", "is_active", "internal_brand"]
    search_fields = ["external_brand_name", "internal_brand__name"]
    ordering = ["scraper_config", "priority", "external_brand_name"]

    fieldsets = [
        (
            "Маппинг",
            {
                "fields": [
                    "scraper_config",
                    "internal_brand",
                    "external_brand_name",
                    "external_brand_url",
                    "external_brand_id",
                ]
            },
        ),
        ("Настройки", {"fields": ["is_active", "priority"]}),
    ]


@admin.register(ScrapedProductLog)
class ScrapedProductLogAdmin(admin.ModelAdmin):
    """Админ для логов товаров."""

    list_display = ["product_name", "action_badge", "session", "external_id", "created_at"]
    list_filter = ["action", "session__scraper_config", "created_at"]
    search_fields = ["product_name", "external_id", "external_url", "message"]
    ordering = ["-created_at"]

    fieldsets = [
        ("Основная информация", {"fields": ["session", "product", "action"]}),
        ("Данные товара", {"fields": ["product_name", "external_id", "external_url"]}),
        ("Дополнительно", {"fields": ["message", "scraped_data"], "classes": ["collapse"]}),
    ]

    readonly_fields = ["created_at"]

    def action_badge(self, obj):
        """Отображает действие с цветным бейджем."""
        colors = {
            "created": "green",
            "updated": "blue",
            "skipped": "gray",
            "error": "red",
            "duplicate": "orange",
        }
        color = colors.get(obj.action, "gray")
        return format_html(
            '<span style="color: {}; font-weight: bold;">●</span> {}',
            color,
            obj.get_action_display(),
        )

    action_badge.short_description = "Действие"


@admin.register(InstagramScraperTask)
class InstagramScraperTaskAdmin(admin.ModelAdmin):
    """Админ для задач парсинга Instagram."""

    form = InstagramScraperTaskForm

    list_display = [
        "source_display",
        "category",
        "status_badge",
        "max_posts",
        "products_stats",
        "created_at",
        "duration_display",
        "actions_column",
    ]
    list_filter = ["status", "category", "created_at"]
    search_fields = ["instagram_username", "post_url", "error_message"]
    ordering = ["-created_at"]

    fieldsets = [
        (
            "Параметры парсинга",
            {
                "fields": ["post_url", "instagram_username", "category", "max_posts"],
                "description": "Укажите либо ссылку на пост (парсинг одного поста), либо username профиля и количество постов.",
            },
        ),
        (
            "Статус и результаты",
            {"fields": ["status", "products_created", "products_updated", "products_skipped"]},
        ),
        (
            "Временные метки",
            {"fields": ["created_at", "started_at", "finished_at"], "classes": ["collapse"]},
        ),
        ("Логи", {"fields": ["log_output", "error_message"], "classes": ["collapse"]}),
    ]

    readonly_fields = [
        "status",
        "products_created",
        "products_updated",
        "products_skipped",
        "log_output",
        "error_message",
        "created_at",
        "started_at",
        "finished_at",
    ]

    actions = ["run_instagram_scraping", "rerun_instagram_scraping"]

    def status_badge(self, obj):
        """Отображает статус с цветным бейджем."""
        colors = {"pending": "blue", "running": "orange", "completed": "green", "failed": "red"}
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="color: {}; font-weight: bold;">●</span> {}',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Статус"

    def products_stats(self, obj):
        """Отображает статистику товаров."""
        if obj.status == "pending":
            return "-"
        return format_html(
            '<span style="color: green;">+{}</span> / '
            '<span style="color: blue;">~{}</span> / '
            '<span style="color: gray;">-{}</span>',
            obj.products_created,
            obj.products_updated,
            obj.products_skipped,
        )

    products_stats.short_description = "Создано / Обновлено / Пропущено"

    def duration_display(self, obj):
        """Отображает продолжительность."""
        if obj.duration:
            total_seconds = int(obj.duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours:
                return f"{hours}ч {minutes}м"
            elif minutes:
                return f"{minutes}м {seconds}с"
            else:
                return f"{seconds}с"
        return "-"

    duration_display.short_description = "Длительность"

    def source_display(self, obj):
        """Отображает источник: ссылка на пост или @username."""
        if obj.post_url:
            short = obj.post_url[:50] + "…" if len(obj.post_url) > 50 else obj.post_url
            return format_html('<span title="{}">Пост: {}</span>', obj.post_url, short)
        return format_html("@{}", obj.instagram_username or "—")

    source_display.short_description = "Источник"

    def _build_instagram_cmd(self, task, scraper_config):
        """Собирает аргументы для run_instagram_scraper: post_url или username + max_posts."""
        cmd = [
            "poetry",
            "run",
            "python",
            "manage.py",
            "run_instagram_scraper",
            "--category",
            task.category,
        ]
        if task.post_url:
            cmd.extend(["--post-url", task.post_url])
        else:
            cmd.extend(["--username", task.instagram_username or ""])
            cmd.extend(["--max-posts", str(task.max_posts)])
        if (
            scraper_config
            and scraper_config.scraper_username
            and scraper_config.scraper_password
        ):
            cmd.extend(["--login", scraper_config.scraper_username])
            cmd.extend(["--password", scraper_config.scraper_password])
        return cmd

    def _task_label(self, task):
        """Подпись задачи для сообщений."""
        if task.post_url:
            s = task.post_url[:40] + "…" if len(task.post_url) > 40 else task.post_url
            return f"пост {s}"
        return f"@{task.instagram_username}"

    def run_instagram_scraping(self, request, queryset):
        """Действие: запустить парсинг для выбранных задач."""
        import subprocess
        from django.utils import timezone

        # Try to find Instagram scraper config to get credentials
        from .models import ScraperConfig

        scraper_config = ScraperConfig.objects.filter(
            parser_class="instagram", is_enabled=True
        ).first()

        valid_tasks = queryset.filter(status="pending").filter(
            models.Q(post_url__isnull=False) | models.Q(instagram_username__iregex=r".+")
        )
        for task in valid_tasks:
            try:
                task.status = "running"
                task.started_at = timezone.now()
                task.save()

                cmd = self._build_instagram_cmd(task, scraper_config)

                # Запускаем команду парсинга
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=600  # 10 минут таймаут
                )

                task.log_output = result.stdout + "\n" + result.stderr

                # Парсим результаты из вывода
                output = result.stdout
                if "создано" in output.lower():
                    import re

                    created_match = re.search(r"создано (\d+)", output.lower())
                    updated_match = re.search(r"обновлено (\d+)", output.lower())
                    skipped_match = re.search(r"пропущено (\d+)", output.lower())

                    if created_match:
                        task.products_created = int(created_match.group(1))
                    if updated_match:
                        task.products_updated = int(updated_match.group(1))
                    if skipped_match:
                        task.products_skipped = int(skipped_match.group(1))

                if result.returncode == 0:
                    task.status = "completed"
                    messages.success(
                        request, f"Парсинг {self._task_label(task)} завершен успешно"
                    )
                else:
                    task.status = "failed"
                    task.error_message = result.stderr
                    messages.error(request, f"Ошибка парсинга {self._task_label(task)}")

            except subprocess.TimeoutExpired:
                task.status = "failed"
                task.error_message = "Превышен таймаут выполнения (10 минут)"
                messages.error(request, f"Таймаут парсинга {self._task_label(task)}")
            except Exception as e:
                task.status = "failed"
                task.error_message = str(e)
                messages.error(request, f"Ошибка: {e}")
            finally:
                task.finished_at = timezone.now()
                task.save()

    run_instagram_scraping.short_description = "Запустить парсинг Instagram"

    def rerun_instagram_scraping(self, request, queryset):
        """Действие: повторно запустить парсинг для выбранных задач."""
        import subprocess
        from django.utils import timezone

        # Try to find Instagram scraper config to get credentials
        from .models import ScraperConfig

        scraper_config = ScraperConfig.objects.filter(
            parser_class="instagram", is_enabled=True
        ).first()

        # Работаем с любыми задачами, кроме running; только с заданным post_url или username
        valid_tasks = queryset.exclude(status="running").filter(
            models.Q(post_url__isnull=False) | models.Q(instagram_username__iregex=r".+")
        )
        for task in valid_tasks:
            try:
                # Сбрасываем статус и результаты
                task.status = "running"
                task.started_at = timezone.now()
                task.finished_at = None
                task.products_created = 0
                task.products_updated = 0
                task.products_skipped = 0
                task.log_output = ""
                task.error_message = ""
                task.save()

                cmd = self._build_instagram_cmd(task, scraper_config)

                # Запускаем команду парсинга
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=600  # 10 минут таймаут
                )

                task.log_output = result.stdout + "\n" + result.stderr

                # Парсим результаты из вывода
                output = result.stdout
                if "создано" in output.lower():
                    import re

                    created_match = re.search(r"создано (\d+)", output.lower())
                    updated_match = re.search(r"обновлено (\d+)", output.lower())
                    skipped_match = re.search(r"пропущено (\d+)", output.lower())

                    if created_match:
                        task.products_created = int(created_match.group(1))
                    if updated_match:
                        task.products_updated = int(updated_match.group(1))
                    if skipped_match:
                        task.products_skipped = int(skipped_match.group(1))

                if result.returncode == 0:
                    task.status = "completed"
                    messages.success(
                        request, f"Повторный парсинг {self._task_label(task)} завершен успешно"
                    )
                else:
                    task.status = "failed"
                    task.error_message = result.stderr
                    messages.error(
                        request, f"Ошибка повторного парсинга {self._task_label(task)}"
                    )

            except subprocess.TimeoutExpired:
                task.status = "failed"
                task.error_message = "Превышен таймаут выполнения (10 минут)"
                messages.error(request, f"Таймаут парсинга {self._task_label(task)}")
            except Exception as e:
                task.status = "failed"
                task.error_message = str(e)
                messages.error(request, f"Ошибка: {e}")
            finally:
                task.finished_at = timezone.now()
                task.save()

    rerun_instagram_scraping.short_description = "Запустить снова (повторный парсинг)"

    def actions_column(self, obj):
        """Колонка с действиями."""
        if obj.status != "running":
            rerun_url = reverse("admin:scrapers_instagramscrapertask_rerun", args=[obj.pk])
            return format_html('<a href="{}" class="button">🔄 Запустить снова</a>', rerun_url)
        return format_html('<span style="color: orange;">⏳ Выполняется...</span>')

    actions_column.short_description = "Действия"

    def get_urls(self):
        """Добавляем кастомные URL."""
        from django.urls import path

        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:task_id>/rerun/",
                self.admin_site.admin_view(self.rerun_task_view),
                name="scrapers_instagramscrapertask_rerun",
            ),
        ]
        return custom_urls + urls

    def rerun_task_view(self, request, task_id):
        """Повторно запускает задачу парсинга."""
        try:
            task = InstagramScraperTask.objects.get(id=task_id)

            if task.status == "running":
                messages.warning(request, f"Задача @{task.instagram_username} уже выполняется")
            else:
                # Используем существующий метод для повторного запуска
                self.rerun_instagram_scraping(
                    request, InstagramScraperTask.objects.filter(pk=task_id)
                )

        except InstagramScraperTask.DoesNotExist:
            messages.error(request, "Задача не найдена")
        except Exception as e:
            messages.error(request, f"Ошибка запуска: {e}")

        return HttpResponseRedirect(reverse("admin:scrapers_instagramscrapertask_changelist"))

    def save_model(self, request, obj, form, change):
        """При создании новой задачи автоматически запускаем парсинг."""
        is_new = obj.pk is None
        super().save_model(request, obj, form, change)

        if is_new and obj.status == "pending":
            # Автоматически запускаем парсинг для новой задачи
            self.run_instagram_scraping(request, InstagramScraperTask.objects.filter(pk=obj.pk))


# Кастомизация админки
admin.site.site_header = "PharmaTurk - Управление парсерами"
admin.site.site_title = "PharmaTurk Admin"
admin.site.index_title = "Панель управления парсерами"
