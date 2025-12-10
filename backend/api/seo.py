"""Простые SEO endpoints: sitemap.xml и robots.txt."""

from django.http import HttpResponse
from django.utils import timezone
from django.conf import settings

from apps.catalog.models import Category, Brand, Product


def _cache_header(response: HttpResponse) -> HttpResponse:
    """Устанавливает Cache-Control только в production, чтобы не мешать разработке."""
    if not settings.DEBUG:
        response["Cache-Control"] = "public, max-age=3600"
        response["ETag"] = f'W/"seo-{timezone.now().date().isoformat()}"'
    return response


def robots_txt(request):
    """Возвращает robots.txt c указанием sitemap."""
    base_url = request.build_absolute_uri("/").rstrip("/")
    lines = [
        "User-agent: *",
        "Disallow:",
        f"Sitemap: {base_url}/sitemap.xml",
    ]
    response = HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
    return _cache_header(response)


def sitemap_xml(request):
    """Генерирует минимальный sitemap по категориям, брендам и товарам."""
    base_url = request.build_absolute_uri("/").rstrip("/")
    urls: list[str] = []

    def add_url(path: str, lastmod=None):
        loc = f"{base_url}{path}"
        if lastmod:
            urls.append(f"<url><loc>{loc}</loc><lastmod>{lastmod}</lastmod></url>")
        else:
            urls.append(f"<url><loc>{loc}</loc></url>")

    # Категории
    for cat in Category.objects.filter(is_active=True).only("slug", "updated_at"):
        path = f"/categories/{cat.slug}"
        lastmod = cat.updated_at.date().isoformat() if cat.updated_at else None
        add_url(path, lastmod)

    # Бренды
    for brand in Brand.objects.filter(is_active=True).only("slug", "updated_at"):
        path = f"/brand/{brand.slug}"
        lastmod = brand.updated_at.date().isoformat() if brand.updated_at else None
        add_url(path, lastmod)

    # Товары (ограничение, чтобы не раздувать sitemap)
    for product in Product.objects.filter(is_active=True).only("slug", "updated_at", "product_type")[:5000]:
        slug = product.slug
        product_type = (product.product_type or "").replace("_", "-")
        path = f"/product/{product_type}/{slug}" if product_type else f"/product/{slug}"
        lastmod = product.updated_at.date().isoformat() if product.updated_at else None
        add_url(path, lastmod)

    generated = timezone.now().date().isoformat()
    body = '<?xml version="1.0" encoding="UTF-8"?>\n' \
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + \
           "\n".join(urls) + \
           f"\n<!-- generated {generated} -->\n</urlset>"
    response = HttpResponse(body, content_type="application/xml; charset=utf-8")
    return _cache_header(response)

