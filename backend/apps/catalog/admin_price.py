from django.contrib import admin


class PublicCatalogPriceAdminMixin:
    """Показывает конечную цену с валютной и товарной/категорийной маржой."""

    def _markup_product(self, obj):
        return getattr(obj, "product", None)

    @admin.display(description="Применённая маржа")
    def effective_product_markup_display(self, obj):
        from .utils.product_markup import get_effective_product_markup

        product = self._markup_product(obj)
        if not product:
            return "Нет связанного товара или услуги"
        margin, source = get_effective_product_markup(product)
        source_labels = {
            "brand": "бренд",
            "category": "категория",
            "global": "глобальная настройка",
        }
        return f"{margin}% ({source_labels.get(source, 'не задана')})"

    def _currency_pair_margin_summary_for_base(self, base_currency):
        from .currency_models import MarginSettings

        base_currency = (base_currency or "").upper()
        pairs = list(
            MarginSettings.objects.filter(
                currency_pair__startswith=f"{base_currency}-",
                margin_percentage__gt=0,
                is_active=True,
            )
            .order_by("currency_pair")
            .values_list("currency_pair", "margin_percentage")
        )
        if not pairs:
            return "маржа валютных пар 0%"

        entries = [
            f"{pair.replace('-', '→')} {margin:.2f}%"
            for pair, margin in pairs
        ]
        prefix = "валютная пара" if len(entries) == 1 else "валютные пары"
        return f"{prefix} {', '.join(entries)}"

    @admin.display(description="Маржа валютных пар")
    def currency_pair_margin_display(self, obj):
        return self._currency_pair_margin_summary_for_base(
            getattr(obj, "base_currency", "")
        )

    def _usdt_markup_summary(self):
        from .currency_models import GlobalCurrencySettings

        markup = GlobalCurrencySettings.load().usdt_markup_percentage
        return f"наценка USDT {markup:.2f}%"

    @admin.display(description="Наценка USDT")
    def usdt_markup_display(self, obj):
        return self._usdt_markup_summary()

    def _public_price(self, obj, currency):
        from .currency_price_snapshots import price_with_pair_margin
        from .utils.currency_converter import currency_converter
        from .utils.product_markup import apply_product_markup

        product = self._markup_product(obj)
        if not product:
            return None

        base_currency = (obj.base_currency or "").upper()
        currency = currency.upper()

        # Глобальная USDT-наценка входит в сам курс. Считаем такие направления
        # по текущей настройке сразу, не дожидаясь фонового обновления snapshot.
        if currency == "USDT" or base_currency == "USDT":
            try:
                _original, _converted, value = currency_converter.convert_price(
                    obj.base_price,
                    base_currency,
                    currency,
                    apply_margin=True,
                )
            except (TypeError, ValueError):
                return None
            return apply_product_markup(value, product)

        value = getattr(obj, f"{currency.lower()}_price", None)
        if value is None and currency == base_currency:
            value = obj.base_price
        if value is None:
            return None

        # В админке считаем валютную маржу по актуальной настройке пары, а не
        # ждём асинхронного обновления сохранённых *_price_with_margin.
        pair = f"{base_currency}-{currency}"
        pair_margin = currency_converter.get_margin_rate(base_currency, currency)
        value = price_with_pair_margin(
            value,
            base_currency,
            currency,
            {pair: pair_margin},
        )
        return apply_product_markup(value, product)

    @admin.display(description="Цена в RUB с маржой")
    def public_rub_price(self, obj):
        return self._public_price(obj, "RUB")

    @admin.display(description="Цена в USD с маржой")
    def public_usd_price(self, obj):
        return self._public_price(obj, "USD")

    @admin.display(description="Цена в KZT с маржой")
    def public_kzt_price(self, obj):
        return self._public_price(obj, "KZT")

    @admin.display(description="Цена в EUR с маржой")
    def public_eur_price(self, obj):
        return self._public_price(obj, "EUR")

    @admin.display(description="Цена в TRY с маржой")
    def public_try_price(self, obj):
        return self._public_price(obj, "TRY")

    @admin.display(description="Цена в USDT с маржой")
    def public_usdt_price(self, obj):
        return self._public_price(obj, "USDT")
