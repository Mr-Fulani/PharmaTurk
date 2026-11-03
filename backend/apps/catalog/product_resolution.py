"""Storefront lookup of catalog cards by slug and of their active variant."""

from apps.feedback.review_aggregates import attach_review_aggregates

from .card_payload import compact_card_product_payload


def get_public_variant(variant_model, slug):
    """Resolve only variants whose parent product is also published."""
    if not slug:
        return None
    return (
        variant_model.objects.filter(
            slug=slug,
            is_active=True,
            product__is_active=True,
        )
        .select_related('product')
        .first()
    )


class SmartSlugLookupMixin:
    """
    Mixin для умного поиска объекта по slug.
    Поддерживает случаи, когда в БД слаг продублирован (напр. name-name),
    а фронтенд прислал очищенную (короткую) версию, и наоборот.
    Также обрабатывает доменные префиксы (напр. 'headwear-' + 'cap').
    """
    _compact_card_product = staticmethod(compact_card_product_payload)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if request.query_params.get('view') != 'card':
            return response

        payload = response.data
        if isinstance(payload, dict) and isinstance(payload.get('results'), list):
            payload['results'] = [
                self._compact_card_product(row)
                for row in payload['results']
            ]
            attach_review_aggregates(payload['results'])
        elif isinstance(payload, list):
            response.data = [
                self._compact_card_product(row)
                for row in payload
            ]
            attach_review_aggregates(response.data)
        return response

    def get_object(self):
        queryset = self.get_queryset()
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        slug = self.kwargs.get(lookup_url_kwarg)

        if not slug:
            return super().get_object()

        try:
            # 1. Прямой поиск (как обычно)
            return queryset.get(**{self.lookup_field: slug})
        except queryset.model.DoesNotExist:
            # 2. Если слаг продублирован в БД (ABC-ABC), а пришел короткий (ABC)
            doubled_slug = f"{slug}-{slug}"
            try:
                return queryset.get(**{self.lookup_field: doubled_slug})
            except queryset.model.DoesNotExist:
                # 3. Если слаг "очищен" на фронте (отрезан префикс типа)
                # Попробуем добавить префикс типа товара (напр. 'headwear-' + 'cap')
                if hasattr(queryset.model, '_domain_product_type'):
                    # Убираем подчеркивания, как это делает фронт
                    prefix = f"{queryset.model._domain_product_type}-".lower().replace('_', '-')
                    if not slug.lower().startswith(prefix):
                        prefixed_slug = f"{prefix}{slug}"
                        try:
                            # Пробуем и префикс, и префикс + дубль
                            return queryset.get(**{self.lookup_field: prefixed_slug})
                        except queryset.model.DoesNotExist:
                            doubled_prefixed = f"{prefixed_slug}-{prefixed_slug}"
                            try:
                                return queryset.get(**{self.lookup_field: doubled_prefixed})
                            except queryset.model.DoesNotExist:
                                pass

                # 4. Если слаг продублирован в URL (ABC-ABC), а в БД он короткий (ABC)
                if '-' in slug:
                    parts = slug.split('-')
                    if len(parts) >= 2 and len(parts) % 2 == 0:
                        half = len(parts) // 2
                        if parts[:half] == parts[half:]:
                            short_slug = "-".join(parts[:half])
                            try:
                                return queryset.get(**{self.lookup_field: short_slug})
                            except queryset.model.DoesNotExist:
                                pass

                # 5. Если в URL префикс есть, а в базе его нет (экстремальный случай)
                if hasattr(queryset.model, '_domain_product_type'):
                    prefix = f"{queryset.model._domain_product_type}-".lower().replace('_', '-')
                    if slug.lower().startswith(prefix):
                        no_prefix_slug = slug[len(prefix):]
                        try:
                            return queryset.get(**{self.lookup_field: no_prefix_slug})
                        except queryset.model.DoesNotExist:
                            pass

                # Если ничего не помогло - выбрасываем 404 через стандартный метод
                return super().get_object()


def resolve_active_variant_from_request(request, explicit_slug: str | None = None) -> str | None:
    if explicit_slug:
        return explicit_slug
    raw = request.query_params.get('active_variant_slug')
    return raw.strip() if isinstance(raw, str) and raw.strip() else None
