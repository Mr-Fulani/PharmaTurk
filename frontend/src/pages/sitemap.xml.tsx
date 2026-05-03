import { GetServerSideProps } from 'next'
import axios from 'axios'
import { getInternalApiUrl } from '../lib/urls'

/**
 * Динамический sitemap.xml с поддержкой мультиязычных (hreflang) URL.
 * Включает: главную, категории, товары, статические страницы.
 *
 * Доступен по адресу: /sitemap.xml
 */

const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || 'https://mudaroba.com').replace(/\/$/, '')

interface SitemapUrl {
  loc: string
  lastmod?: string
  changefreq?: 'always' | 'hourly' | 'daily' | 'weekly' | 'monthly' | 'yearly' | 'never'
  priority?: number
  alternates?: { lang: string; href: string }[]
}

const BASE_PRODUCT_TYPES = new Set([
  '',
  'product',
  'products',
  'medicine',
  'medicines',
  'supplement',
  'supplements',
  'medical_equipment',
  'medical-equipment',
  'tableware',
  'accessory',
  'accessories',
  'incense',
  'sports',
  'auto_parts',
  'auto-parts',
])

function buildProductPath(slug: string, productType?: string | null): string {
  const normalizedType = (productType || '').trim().replace(/_/g, '-')
  if (!normalizedType || BASE_PRODUCT_TYPES.has(normalizedType)) {
    return `/product/${slug}`
  }
  return `/product/${normalizedType}/${slug}`
}

function buildUrl(
  ruPath: string,
  enPath: string,
  changefreq: SitemapUrl['changefreq'] = 'weekly',
  priority = 0.8
): SitemapUrl {
  const ruHref = `${SITE_URL}${ruPath}`        // ru — без префикса (основной)
  const enHref = `${SITE_URL}/en${enPath}`    // en — с /en
  return {
    loc: ruHref,
    changefreq,
    priority,
    alternates: [
      { lang: 'ru', href: ruHref },
      { lang: 'en', href: enHref },
      { lang: 'x-default', href: ruHref },
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

  // 1. Статические страницы (базовые роуты)
  const basePages: Array<[string, string, SitemapUrl['changefreq'], number]> = [
    ['/', '/', 'daily', 1.0],
    ['/categories', '/categories', 'daily', 0.9],
    ['/brands', '/brands', 'weekly', 0.7],
    ['/how-to-order-medicines', '/how-to-order-medicines', 'monthly', 0.5],
    ['/testimonials', '/testimonials', 'weekly', 0.6],
    ['/categories/uslugi', '/categories/uslugi', 'weekly', 0.8],
  ]

  for (const [enPath, ruPath, changefreq, priority] of basePages) {
    urls.push(buildUrl(enPath, ruPath, changefreq, priority))
  }

  // 2. Динамические страницы из базы (О нас, Доставка, Возврат и т.д.)
  try {
    const pagesRes = await axios.get(getInternalApiUrl('pages/'), {
      params: { is_active: true },
      timeout: 5000,
    })
    const pages = pagesRes.data?.results || pagesRes.data || []
    for (const page of pages) {
      if (page.slug) {
        // Пропускаем те, что уже добавлены вручную (на всякий случай)
        const path = `/${page.slug}`
        if (urls.some(u => u.loc.endsWith(path))) continue

        const lastmod = page.updated_at
          ? new Date(page.updated_at).toISOString().split('T')[0]
          : today
        
        const url = buildUrl(path, path, 'monthly', 0.6)
        url.lastmod = lastmod
        urls.push(url)
      }
    }
  } catch (err) {
    console.error('Sitemap: Failed to fetch dynamic pages', err)
  }

  // Категории из API
  try {
    const categoriesRes = await axios.get(getInternalApiUrl('catalog/categories'), {
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
    let currentPage = 1
    let totalPages = 1
    const maxPagesLimit = 50 // Limit to 50,000 products to avoid timeout

    while (currentPage <= totalPages && currentPage <= maxPagesLimit) {
      const productsRes = await axios.get(getInternalApiUrl('catalog/products/'), {
        params: { lang: 'en', page_size: 1000, is_active: true, page: currentPage },
        timeout: 10000,
      })
      const data = productsRes.data
      const products = data?.results || data || []

      if (data?.count) {
        totalPages = Math.ceil(data.count / 1000)
      } else {
        totalPages = 1
      }

      for (const product of products) {
        if (product.slug) {
          const lastmod = product.updated_at
            ? new Date(product.updated_at).toISOString().split('T')[0]
            : today
          const productPath = buildProductPath(product.slug, product.product_type)
          const url = buildUrl(productPath, productPath, 'weekly', 0.7)
          url.lastmod = lastmod
          urls.push(url)
        }
      }
      currentPage++
    }
  } catch {
    // Если API недоступен — продолжаем без товаров
  }

  // Услуги из API
  try {
    let currentPage = 1
    let totalPages = 1
    const maxPagesLimit = 50

    while (currentPage <= totalPages && currentPage <= maxPagesLimit) {
      const servicesRes = await axios.get(getInternalApiUrl('catalog/services/'), {
        params: { lang: 'en', page_size: 1000, is_active: true, page: currentPage },
        timeout: 10000,
      })
      const data = servicesRes.data
      const services = data?.results || data || []

      if (data?.count) {
        totalPages = Math.ceil(data.count / 1000)
      } else {
        totalPages = 1
      }

      for (const service of services) {
        if (service.slug) {
          const lastmod = service.updated_at
            ? new Date(service.updated_at).toISOString().split('T')[0]
            : today
          const url = buildUrl(
            `/product/uslugi/${service.slug}`,
            `/product/uslugi/${service.slug}`,
            'weekly',
            0.75
          )
          url.lastmod = lastmod
          urls.push(url)
        }
      }
      currentPage++
    }
  } catch {
    // Если API недоступен — продолжаем без услуг
  }

  const sitemap = generateSitemapXml(urls)

  res.setHeader('Content-Type', 'application/xml; charset=utf-8')
  res.setHeader('Cache-Control', 'public, s-maxage=3600, stale-while-revalidate=86400')
  res.write(sitemap)
  res.end()

  return { props: {} }
}
