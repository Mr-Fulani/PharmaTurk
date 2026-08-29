"""Конфигурация Django Admin и группировка главного меню."""

from django.contrib.admin import AdminSite


class MudarobaAdminSite(AdminSite):
    """Логические группы без изменения model admin URL."""

    site_header = "Mudaroba — Панель управления"
    site_title = "Mudaroba Admin"
    index_title = "Панель управления Mudaroba"

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
                "ProductMarketCheck",
                "ProductSourceOffer",
                "VKCategoryMapping",
            }
        ),
        "Цены и валюты": frozenset(
            {
                "CurrencyRate",
                "CurrencyUpdateLog",
                "GlobalCurrencySettings",
                "MarginSettings",
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
        "feedback": "Отзывы и вопросы",
        "marketing": "Маркетинг",
        "orders": "Заказы и корзины",
        "pages": "Контент и настройки",
        "scrapers": "Парсеры",
        "settings": "Контент и настройки",
        "token_blacklist": "Аутентификация",
        "users": "Пользователи",
    }

    GROUP_LABELS = {
        "Товары каталога": "catalog_products",
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

        result = list(grouped.values())
        result.sort(
            key=lambda app: (
                self.GROUP_ORDER.get(app["name"], 999),
                str(app["name"]),
            )
        )
        return result
