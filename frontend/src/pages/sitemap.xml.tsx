import { GetServerSideProps } from 'next'
import axios from 'axios'
import { getInternalApiUrl } from '../lib/urls'

/**
 * Динамический sitemap.xml с поддержкой мультиязычных (hreflang) URL.
 * Включает: главную, категории, товары, статические страницы.
 *
 * Доступен по адресу: /sitemap.xml
 */

const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || 'https://pharmaturk.ru').replace(/\/$/, '')

interface SitemapUrl {
  loc: string
  lastmod?: string
  changefreq?: 'always' | 'hourly' | 'daily' | 'weekly' | 'monthly' | 'yearly' | 'never'
  priority?: number
  alternates?: { lang: string; href: string }[]
}

function buildUrl(
  enPath: string,
  ruPath: string,
  changefreq: SitemapUrl['changefreq'] = 'weekly',
  priority = 0.8
): SitemapUrl {
  const enHref = `${SITE_URL}${enPath}`
  const ruHref = `${SITE_URL}/ru${ruPath}`
  return {
    loc: enHref,
    changefreq,
    priority,
    alternates: [
      { lang: 'en', href: enHref },
      { lang: 'ru', href: ruHref },
      { lang: 'x-default', href: enHref },
    ],
  }
}

function generateSitemapXml(urls: SitemapUrl[]): string {
  const urlsXml = urls
    .map((url) => {
      const alternatesXml = (url.alternates || [])
        .map(
          (alt) =>
            `    <xhtml:link rel="alternate" hreflang="${alt.lang}" href="${alt.href}"/>`
        )
        .join('\n')

      return `  <url>
    <loc>${url.loc}</loc>
    ${url.lastmod ? `<lastmod>${url.lastmod}</lastmod>` : ''}
    <changefreq>${url.changefreq || 'weekly'}</changefreq>
    <priority>${url.priority ?? 0.8}</priority>
${alternatesXml}
  </url>`
    })
    .join('\n')

  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset
  xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
  xmlns:xhtml="http://www.w3.org/1999/xhtml"
>
${urlsXml}
</urlset>`
}

// Этот компонент не рендерится — данные отдаются через getServerSideProps
export default function Sitemap() {
  return null
}

export const getServerSideProps: GetServerSideProps = async ({ res }) => {
  const today = new Date().toISOString().split('T')[0]

  const urls: SitemapUrl[] = []

  // Статические страницы
  const staticPages: Array<[string, string, SitemapUrl['changefreq'], number]> = [
    ['/', '/', 'daily', 1.0],
    ['/categories', '/categories', 'daily', 0.9],
    ['/brands', '/brands', 'weekly', 0.7],
    ['/delivery', '/delivery', 'monthly', 0.5],
    ['/returns', '/returns', 'monthly', 0.5],
    ['/privacy', '/privacy', 'monthly', 0.4],
    ['/how-to-order-medicines', '/how-to-order-medicines', 'monthly', 0.5],
    ['/testimonials', '/testimonials', 'weekly', 0.6],
  ]

  for (const [enPath, ruPath, changefreq, priority] of staticPages) {
    urls.push(buildUrl(enPath, ruPath, changefreq, priority))
  }

  // Категории из API
  try {
    const categoriesRes = await axios.get(getInternalApiUrl('catalog/categories/'), {
      params: { lang: 'en', page_size: 200 },
      timeout: 5000,
    })
    const categories = categoriesRes.data?.results || categoriesRes.data || []
    for (const cat of categories) {
      if (cat.slug) {
        urls.push(
          buildUrl(
            `/categories/${cat.slug}`,
            `/categories/${cat.slug}`,
            'daily',
            0.8
          )
        )
      }
    }
  } catch {
    // Если API недоступен — продолжаем без категорий
  }

  // Товары из API
  try {
    const productsRes = await axios.get(getInternalApiUrl('catalog/products/'), {
      params: { lang: 'en', page_size: 500, is_active: true },
      timeout: 8000,
    })
    const products = productsRes.data?.results || productsRes.data || []
    for (const product of products) {
      if (product.slug) {
        const lastmod = product.updated_at
          ? new Date(product.updated_at).toISOString().split('T')[0]
          : today
        const url = buildUrl(
          `/product/${product.slug}`,
          `/product/${product.slug}`,
          'weekly',
          0.7
        )
        url.lastmod = lastmod
        urls.push(url)
      }
    }
  } catch {
    // Если API недоступен — продолжаем без товаров
  }

  const sitemap = generateSitemapXml(urls)

  res.setHeader('Content-Type', 'application/xml; charset=utf-8')
  res.setHeader('Cache-Control', 'public, s-maxage=3600, stale-while-revalidate=86400')
  res.write(sitemap)
  res.end()

  return { props: {} }
}
