"""Конфигурация Django Admin и группировка главного меню."""

from django.conf import settings
from django.contrib.admin import AdminSite
from django_otp import user_has_device
from django_otp.middleware import OTPMiddleware


class AdminOTPMiddleware(OTPMiddleware):
    """OTPMiddleware без ``user.is_verified()``: у нашего User есть поле
    ``is_verified`` (почта подтверждена), и штатный слой подменял его функцией
    у каждого пользователя с сессией. Признак входа с кодом — ``user.otp_device``."""

    @staticmethod
    def _init_user_fields(user):
        user.otp_device = None


def admin_otp_required(user) -> bool:
    """Нужен ли этому сотруднику код второго фактора для входа в админку."""
    return settings.ADMIN_OTP_REQUIRED or user_has_device(user)


class MudarobaAdminSite(AdminSite):
    """Логические группы без изменения model admin URL."""

    site_header = "Mudaroba — Панель управления"
    site_title = "Mudaroba Admin"
    index_title = "Панель управления Mudaroba"
    # Плитки частых разделов (docs/ADMIN_HOME_TILES.md) и поле «Проверить лекарство»
    # над списком разделов (TD-044, docs/DRUG_CHECK.md).
    index_template = "admin/mudaroba_index.html"
    # Форма входа с полем кода второго фактора (docs/ADMIN_TWO_FACTOR.md).
    login_template = "admin/mudaroba_login.html"

    def get_urls(self):
        from django.urls import path

        return [
            path("two-factor/", self.admin_view(self.two_factor_view), name="two_factor"),
            *super().get_urls(),
        ]

    def two_factor_view(self, request):
        """Сотрудник сам включает второй фактор: устройство подтверждается
        только верным кодом, поэтому остаться без входа нельзя."""
        import base64
        from io import BytesIO

        import django_otp
        from django.template.response import TemplateResponse
        from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
        from django_otp.plugins.otp_totp.models import TOTPDevice
        from django_otp.qr import write_qrcode_image

        user = request.user
        context = {**self.each_context(request), "title": "Второй фактор входа"}
        if user_has_device(user):
            return TemplateResponse(request, "admin/mudaroba_two_factor.html", {**context, "enabled": True})

        device, _created = TOTPDevice.objects.get_or_create(
            user=user, confirmed=False, defaults={"name": "Приложение"}
        )
        if request.method == "POST":
            token = (request.POST.get("otp_token") or "").replace(" ", "")
            if token and device.verify_token(token):
                device.confirmed = True
                device.save(update_fields=["confirmed"])
                backup = StaticDevice.objects.create(user=user, name="Запасные коды", confirmed=True)
                backup_codes = [StaticToken.random_token() for _index in range(5)]
                StaticToken.objects.bulk_create(
                    StaticToken(device=backup, token=code) for code in backup_codes
                )
                django_otp.login(request, device)
                request._admin_otp_allowed = True
                return TemplateResponse(
                    request,
                    "admin/mudaroba_two_factor.html",
                    {**context, "enabled": True, "backup_codes": backup_codes},
                )
            context["error"] = "Код не подошёл. Проверьте время на телефоне и введите новый код."

        qr_image = BytesIO()
        write_qrcode_image(device.config_url, qr_image)
        context["qr_data_uri"] = "data:image/svg+xml;base64," + base64.b64encode(qr_image.getvalue()).decode()
        context["secret_key"] = base64.b32encode(device.bin_key).decode()
        return TemplateResponse(request, "admin/mudaroba_two_factor.html", context)

    def has_permission(self, request):
        if not super().has_permission(request):
            return False
        # Админка спрашивает права несколько раз за запрос — в базу один раз.
        allowed = getattr(request, "_admin_otp_allowed", None)
        if allowed is None:
            user = request.user
            # otp_device ставит AdminOTPMiddleware: сессия вошла с кодом.
            allowed = getattr(user, "otp_device", None) is not None or not admin_otp_required(user)
            request._admin_otp_allowed = allowed
        return allowed

    MEDIA_MODELS = frozenset(
        {
            "MediaEnrichmentCandidate",
            "ProductImage",
            "MarketingBannerMedia",
        }
    )

    CATALOG_MODEL_GROUPS = {
        "Категории и справочники": frozenset(
            {
                "Author",
                "Brand",
                "Category",
                "CategoryAccessories",
                "CategoryBooks",
                "CategoryClothing",
                "CategoryCollection",
                "CategoryElectronics",
                "CategoryFurniture",
                "CategoryHeadwear",
                "CategoryIncense",
                "CategoryJewelry",
                "CategoryMedicalEquipment",
                "CategoryMedicines",
                "CategoryPerfumery",
                "CategoryServices",
                "CategoryShoes",
                "CategorySupplements",
                "CategoryTableware",
                "CategoryType",
                "CategoryUnderwear",
                "MedicineGroup",
                "ProductAuthor",
            }
        ),
        "Варианты товаров": frozenset(
            {
                "BookVariant",
                "ClothingVariant",
                "FurnitureVariant",
                "HeadwearVariant",
                "IslamicClothingVariant",
                "JewelryVariant",
                "PerfumeryVariant",
                "ShoeVariant",
                "UnderwearVariant",
            }
        ),
        "Источники и проверки": frozenset(
            {
                "ProductDeletionLog",
                "ProductMarketCheck",
                "ProductSourceOffer",
                "StaleProductCandidate",
                "StockCheckSourceState",
                "VKCategoryMapping",
            }
        ),
        "Цены и валюты": frozenset(
            {
                "CurrencyRate",
                "CurrencyUpdateLog",
                "GlobalCurrencySettings",
                "MarginSettings",
                "MarkupScale",
                "PriceHistory",
                "ProductPrice",
                "ProductVariantPrice",
                "ServicePrice",
            }
        ),
        "Настройки каталога": frozenset(
            {
                "GlobalAttributeKey",
                "GlobalShippingSettings",
                "ProductAttributeValue",
            }
        ),
        "Избранное": frozenset({"Favorite"}),
    }

    APP_GROUPS = {
        "ai": "AI-модуль",
        "auth": "Аутентификация",
        "drug_check": "Проверка лекарств",
        "feedback": "Отзывы и вопросы",
        "marketing": "Маркетинг",
        "orders": "Заказы и корзины",
        "otp_static": "Аутентификация",
        "otp_totp": "Аутентификация",
        "pages": "Контент и настройки",
        "scrapers": "Парсеры",
        "settings": "Контент и настройки",
        "token_blacklist": "Аутентификация",
        "users": "Пользователи",
    }

    GROUP_LABELS = {
        "Товары каталога": "catalog_products",
        "Проверка лекарств": "drug_check_group",
        "Изображения и медиа": "catalog_media",
        "Категории и справочники": "catalog_reference",
        "Варианты товаров": "catalog_variants",
        "Источники и проверки": "catalog_sources",
        "Цены и валюты": "catalog_prices",
        "Настройки каталога": "catalog_settings",
        "Заказы и корзины": "orders_and_carts",
        "Маркетинг": "marketing_group",
        "Парсеры": "scrapers_group",
        "AI-модуль": "ai_group",
        "Отзывы и вопросы": "feedback_group",
        "Контент и настройки": "content_group",
        "Пользователи": "users_group",
        "Избранное": "favorites_group",
        "Аутентификация": "authentication_group",
    }

    GROUP_ORDER = dict(zip(GROUP_LABELS, range(1, len(GROUP_LABELS) + 1), strict=True))

    MEDIA_MODEL_ORDER = {
        "MediaEnrichmentCandidate": 1,
        "ProductImage": 2,
        "MarketingBannerMedia": 3,
    }

    def index(self, request, extra_context=None):
        from .admin_tiles import home_tiles

        return super().index(request, {**(extra_context or {}), "home_tiles": home_tiles(self, request)})

    def _group_name(self, app_label, app_name, object_name):
        if object_name in self.MEDIA_MODELS:
            return "Изображения и медиа"

        if app_label == "catalog":
            for group_name, model_names in self.CATALOG_MODEL_GROUPS.items():
                if object_name in model_names:
                    return group_name
            return "Товары каталога"

        return self.APP_GROUPS.get(app_label, app_name)

    def get_app_list(self, request, app_label=None):
        """Группировать главную страницу, сохраняя штатные app-index views."""
        app_list = super().get_app_list(request, app_label)
        if app_label is not None:
            return app_list

        grouped = {}
        for app in app_list:
            source_app_label = app.get("app_label", "")
            source_app_name = app.get("name", "")
            for model in app.get("models", ()):
                group_name = self._group_name(
                    source_app_label,
                    source_app_name,
                    model.get("object_name", ""),
                )
                group = grouped.setdefault(
                    group_name,
                    {
                        "name": group_name,
                        "app_label": self.GROUP_LABELS.get(
                            group_name,
                            source_app_label,
                        ),
                        "app_url": (
                            app.get("app_url", "") if group_name == source_app_name else ""
                        ),
                        "has_module_perms": False,
                        "models": [],
                    },
                )
                group["has_module_perms"] = bool(
                    group["has_module_perms"] or app.get("has_module_perms", True)
                )
                group["models"].append(model)

        media_group = grouped.get("Изображения и медиа")
        if media_group:
            media_group["models"].sort(
                key=lambda model: (
                    self.MEDIA_MODEL_ORDER.get(model.get("object_name", ""), 999),
                    str(model.get("name", "")),
                )
            )

        drug_group = grouped.get("Проверка лекарств")
        user = getattr(request, "user", None)
        if drug_group and user is not None and user.has_perm("catalog.view_medicineproduct"):
            # Отдельный пункт меню — поиск по названию или штрихкоду (TD-044).
            from django.urls import reverse

            drug_group["models"].insert(
                0,
                {
                    "name": "Проверить лекарство (название или штрихкод)",
                    "object_name": "DrugCheckLookup",
                    "admin_url": reverse(f"{self.name}:drug_check_lookup"),
                    "add_url": None,
                    "view_only": True,
                    "perms": {"view": True},
                },
            )

        if user is not None and getattr(user, "is_staff", False):
            # Второй фактор — в блоке «Аутентификация»: пункт включения виден каждому
            # сотруднику, списки устройств — тем, у кого есть права на них.
            from django.urls import reverse

            auth_group = grouped.setdefault(
                "Аутентификация",
                {
                    "name": "Аутентификация",
                    "app_label": self.GROUP_LABELS["Аутентификация"],
                    "app_url": "",
                    "has_module_perms": True,
                    "models": [],
                },
            )
            auth_group["models"].insert(
                0,
                {
                    "name": "Второй фактор: включить код из приложения",
                    "object_name": "AdminTwoFactorSetup",
                    "admin_url": reverse(f"{self.name}:two_factor"),
                    "add_url": None,
                    "view_only": True,
                    "perms": {"view": True},
                },
            )

        result = list(grouped.values())
        result.sort(
            key=lambda app: (
                self.GROUP_ORDER.get(app["name"], 999),
                str(app["name"]),
            )
        )
        return result
