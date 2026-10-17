"""Small, expiring traversal checkpoints shared by consecutive catalog chunks."""

import hashlib

from django.core.cache import cache


class CatalogTraversalState:
    TTL = 7 * 24 * 60 * 60
    MAX_PAGES_WITHOUT_NEW_PRODUCTS = 3

    def __init__(self, namespace=None):
        self.namespace = namespace
        self.local = {}

    def _key(self, kind, value):
        digest = hashlib.sha256(str(value).encode()).hexdigest()
        return f"scraper:catalog:v1:{self.namespace}:{kind}:{digest}"

    def _get(self, kind, value):
        key = self._key(kind, value)
        if key not in self.local and self.namespace is not None:
            self.local[key] = cache.get(key)
        return self.local.get(key)

    def _set(self, kind, value, data):
        key = self._key(kind, value)
        self.local[key] = data
        if self.namespace is not None:
            cache.set(key, data, timeout=self.TTL)

    def product_seen(self, identity):
        return bool(identity and self._get("product", identity))

    def mark_product(self, identity):
        if identity:
            self._set("product", identity, True)

    @staticmethod
    def page_identity(identities):
        return "\n".join(sorted(set(identities)))

    def page_seen(self, identities, page):
        previous = self._get("page", self.page_identity(identities))
        # Resuming the current page must remain possible after a pause/timeout.
        return previous is not None and previous != page

    def finish_page(self, identities, page, made_progress):
        self._set("page", self.page_identity(identities), page)
        previous_page, empty_count = self._get("progress", "last") or (None, 0)
        if made_progress:
            empty_count = 0
        elif previous_page != page:
            empty_count = empty_count + 1 if previous_page == page - 1 else 1
        self._set("progress", "last", (page, empty_count))
        return empty_count >= self.MAX_PAGES_WITHOUT_NEW_PRODUCTS
