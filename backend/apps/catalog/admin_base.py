from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html


class OrderedAdminActionsMixin:
    """Централизует состав и порядок actions в Django admin."""

    declared_admin_actions = ()
    admin_action_order = ()
    excluded_admin_actions = ()

    def get_declared_admin_actions(self):
        return tuple(self.declared_admin_actions)

    def get_admin_action_order(self):
        order = self.admin_action_order or self.get_declared_admin_actions()
        return tuple(order)

    def get_excluded_admin_actions(self):
        return tuple(self.excluded_admin_actions)

    def _build_admin_action_tuple(self, action_name):
        action = getattr(self, action_name, None)
        if action is None:
            return None

        action_func = getattr(type(self), action_name, None)
        if action_func is None:
            return None

        return (
            action_func,
            action_name,
            getattr(action, "short_description", action_name),
        )

    def get_actions(self, request):
        actions = super().get_actions(request)

        for action_name in self.get_declared_admin_actions():
            action_tuple = self._build_admin_action_tuple(action_name)
            if action_tuple is not None:
                actions[action_name] = action_tuple

        for action_name in self.get_excluded_admin_actions():
            actions.pop(action_name, None)

        ordered_actions = {}
        for action_name in self.get_admin_action_order():
            if action_name in actions:
                ordered_actions[action_name] = actions.pop(action_name)

        ordered_actions.update(actions)
        return ordered_actions


class GlobalActivationActionsMixin(OrderedAdminActionsMixin):
    """Глобальные actions, которые должны быть доступны всем товарам и услугам."""

    global_activation_action_names = (
        "make_active",
        "make_inactive",
    )

    def get_declared_admin_actions(self):
        return tuple(self.global_activation_action_names) + tuple(super().get_declared_admin_actions())

    def get_admin_action_order(self):
        current_order = tuple(super().get_admin_action_order())
        prefixed = [action_name for action_name in self.global_activation_action_names if action_name not in current_order]
        return tuple(prefixed) + current_order

    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            _("Активировано записей: %(count)s.") % {"count": updated},
            level=messages.SUCCESS,
        )

    make_active.short_description = _("[Общее] Сделать активными")

    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            _("Деактивировано записей: %(count)s.") % {"count": updated},
            level=messages.SUCCESS,
        )

    make_inactive.short_description = _("[Общее] Сделать неактивными")


class AIStatusFilter(admin.SimpleListFilter):
    """Фильтр товаров по статусу их AI-обработки."""
    title = _("Статус AI")
    parameter_name = "ai_status"

    def lookups(self, request, model_admin):
        from apps.ai.models import AIProcessingStatus
        return [
            ("none", _("Не обрабатывалось")),
            (AIProcessingStatus.PROCESSING, _("В процессе")),
            (AIProcessingStatus.COMPLETED, _("Завершено (AI)")),
            (AIProcessingStatus.MODERATION, _("На модерации")),
            (AIProcessingStatus.APPROVED, _("Одобрено")),
            (AIProcessingStatus.FAILED, _("Ошибка")),
        ]

    def queryset(self, request, queryset):
        from apps.ai.models import AIProcessingLog

        if not self.value():
            return queryset

        # Проверяем, является ли модель доменной (через наличие base_product)
        is_domain = hasattr(queryset.model, "base_product")
        logs_path = "base_product__ai_logs" if is_domain else "ai_logs"
        id_field = "base_product_id" if is_domain else "id"

        if self.value() == "none":
            return queryset.filter(**{f"{logs_path}__isnull": True})
        
        # Получаем последние логи для каждого товара
        product_ids = queryset.values_list(id_field, flat=True)
        latest_logs = AIProcessingLog.objects.filter(
            product_id__in=product_ids
        ).order_by("product_id", "-created_at").distinct("product_id")
        
        target_product_ids = latest_logs.filter(status=self.value()).values_list("product_id", flat=True)
        return queryset.filter(**{f"{id_field}__in": target_product_ids})


class MediaEnrichmentStatusFilter(admin.SimpleListFilter):
    """Фильтр товаров по статусу обогащения медиа."""
    title = _("Статус медиа")
    parameter_name = "media_status"

    def lookups(self, request, model_admin):
        from apps.catalog.models import MediaEnrichmentStatus
        return MediaEnrichmentStatus.choices

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        return queryset.filter(media_enrichment_status=self.value())


class RunAIActionMixin(GlobalActivationActionsMixin):
    """Общий миксин для запуска задач AI из админки."""

    declared_admin_actions = (
        "run_ai",
        "run_ai_auto_apply",
        "run_find_merge_duplicates",
    )
    admin_action_order = declared_admin_actions

    def _resolve_base_product_id(self, obj):
        """Пытаемся достать base_product_id (для прокси или доменных моделей)."""
        return getattr(obj, "base_product_id", None) or getattr(obj, "id", None)

    def run_ai(self, request, queryset):
        """Поставить выбранные товары в очередь AI (без авто-применения)."""
        from apps.ai.tasks import process_product_ai_task
        from apps.ai.models import AIProcessingLog, AIProcessingStatus

        # Проверяем, является ли модель доменной
        is_domain = hasattr(queryset.model, "base_product")
        id_field = "base_product_id" if is_domain else "id"
        product_ids = queryset.values_list(id_field, flat=True)

        # Предварительно находим уже обработанные товары
        processed_ids = set(AIProcessingLog.objects.filter(
            product_id__in=product_ids,
            status__in=[AIProcessingStatus.COMPLETED, AIProcessingStatus.APPROVED, AIProcessingStatus.MODERATION]
        ).values_list("product_id", flat=True))

        queued = 0
        skipped = 0
        for obj in queryset:
            pid = self._resolve_base_product_id(obj)
            if pid in processed_ids:
                skipped += 1
                continue
            
            process_product_ai_task.delay(
                product_id=pid,
                processing_type="full",
                auto_apply=False,
            )
            queued += 1

        msg = _("Запущена полная AI обработка для %(count)s товаров.") % {"count": queued}
        if skipped:
            msg += " " + _("Пропущено %(skipped)s уже обработанных товаров.") % {"skipped": skipped}
        
        self.message_user(request, msg, level=messages.SUCCESS)
    run_ai.short_description = _("[AI] Полная AI обработка (без авто-применения)")

    def run_ai_auto_apply(self, request, queryset):
        """Один запуск: полная обработка + авто-применение."""
        from apps.ai.tasks import process_product_ai_task

        queued = 0
        for obj in queryset:
            pid = self._resolve_base_product_id(obj)
            if not pid:
                continue

            process_product_ai_task.delay(
                product_id=pid,
                processing_type="full",
                auto_apply=True,
            )
            queued += 1

        self.message_user(
            request,
            _(
                "Запущена полная AI обработка/авто-применение для %(count)s товаров. "
                "Если у товара уже есть готовый AI-лог, будет применен он."
            ) % {"count": queued},
            level=messages.SUCCESS,
        )
    run_ai_auto_apply.short_description = _("[AI] Полная AI обработка + авто-применение")

    def run_find_merge_duplicates(self, request, queryset):
        """Запуск поиска кандидатов в дубликаты по всему каталогу."""
        from apps.scrapers.tasks import find_and_merge_duplicates
        find_and_merge_duplicates.delay()
        self.message_user(
            request,
            _("Запущен поиск кандидатов в дубликаты по всему каталогу. Кандидаты появятся в модерации админки."),
            level=messages.SUCCESS,
        )
    run_find_merge_duplicates.short_description = _("[Общее] Поиск кандидатов в дубликаты (на модерацию)")

    ai_logs_prefetch_path = "ai_logs"

    def get_ai_logs_prefetch_path(self):
        if hasattr(getattr(self, "model", None), "base_product"):
            return "base_product__ai_logs"
        return self.ai_logs_prefetch_path

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(self.get_ai_logs_prefetch_path())

    def get_ai_status(self, obj):
        from apps.ai.models import AIProcessingStatus, AIProcessingLog
        
        # Пытаемся взять из prefetch, чтобы избежать N+1 запросов
        log = None
        
        # 1. Если это доменная модель (Одежда, Медицина и т.д.)
        if hasattr(obj, "base_product") and obj.base_product:
            # Префетч обычно идет как 'base_product__ai_logs'
            if hasattr(obj.base_product, "ai_logs"):
                all_logs = obj.base_product.ai_logs.all()
                log = all_logs[0] if all_logs else None
        
        # 2. Если это базовая модель (Product) или прокси
        elif hasattr(obj, "ai_logs"):
            all_logs = obj.ai_logs.all()
            log = all_logs[0] if all_logs else None
        
        # 3. Fallback: если не префетчнуто (например, в детальной вью), делаем прямой запрос
        if log is None:
            pid = self._resolve_base_product_id(obj)
            log = AIProcessingLog.objects.filter(product_id=pid).order_by("-created_at").first()
        
        if not log:
            return format_html('<span style="color: gray;">{}</span>', _("Нет"))
        
        status_colors = {
            AIProcessingStatus.COMPLETED: "green",
            AIProcessingStatus.APPROVED: "blue",
            AIProcessingStatus.MODERATION: "orange",
            AIProcessingStatus.FAILED: "red",
            AIProcessingStatus.PROCESSING: "purple",
            AIProcessingStatus.PENDING: "gray",
        }
        color = status_colors.get(log.status, "black")
        return format_html('<span style="color: {};">{}</span>', color, log.get_status_display())
    get_ai_status.short_description = _("Статус AI")


class MediaEnrichmentMixin:
    """Миксин для ручного запуска обогащения медиа из админки."""

    def run_media_enrichment(self, request, queryset):
        """Запустить обогащение медиа для выбранных товаров."""
        from apps.catalog.tasks import enrich_medicine_media
        
        # Берем только ID
        product_ids = list(queryset.values_list("id", flat=True))
        model_name = queryset.model.__name__
        
        # Запускаем задачу
        enrich_medicine_media.delay(
            product_ids=product_ids,
            ignore_cache=True,  # При ручном запуске игнорируем кэш ошибок
            model_name=model_name
        )
        
        self.message_user(
            request, 
            _("Запущено обогащение медиа для %(count)s товаров.") % {"count": len(product_ids)},
            level=messages.SUCCESS
        )
    run_media_enrichment.short_description = _("[Категория] Обогатить медиа (картинки)")


class ShadowProductCleanupAdminMixin:
    """Гарантирует удаление shadow Product при удалении доменного товара из админки."""

    def delete_queryset(self, request, queryset):
        from apps.catalog.models import Product

        base_ids = list(queryset.values_list("base_product_id", flat=True).distinct())
        super().delete_queryset(request, queryset)
        live_ids = [pk for pk in base_ids if pk]
        if live_ids:
            Product.objects.filter(pk__in=live_ids).delete()

    def delete_model(self, request, obj):
        from apps.catalog.models import Product

        base_id = getattr(obj, "base_product_id", None)
        super().delete_model(request, obj)
        if base_id:
            Product.objects.filter(pk=base_id).delete()

    def get_media_enrichment_status(self, obj):
        """Отображение статуса медиа с цветовой индикацией."""
        from apps.catalog.models import MediaEnrichmentStatus
        
        status = getattr(obj, 'media_enrichment_status', MediaEnrichmentStatus.PENDING)
        color = "gray"
        label = _("В очереди")
        
        if status == MediaEnrichmentStatus.PROCESSING:
            color = "orange"
            label = _("Обработка")
        elif status == MediaEnrichmentStatus.COMPLETED:
            color = "green"
            label = _("Завершено")
        elif status == MediaEnrichmentStatus.FAILED:
            color = "red"
            label = _("Ошибка")
            
        error = getattr(obj, 'media_enrichment_error', None)
        title_attr = f' title="{error}"' if error else ""
        
        return format_html(
            '<span style="color: {}; font-weight: bold;"{}>{}</span>',
            color, title_attr, label
        )
    get_media_enrichment_status.short_description = _("Статус медиа")
    get_media_enrichment_status.admin_order_field = "media_enrichment_status"
