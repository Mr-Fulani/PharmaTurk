import { GetServerSideProps } from 'next'
import axios from 'axios'
import { getInternalApiUrl } from '../lib/urls'

/**
 * Динамический sitemap.xml с поддержкой мультиязычных (hreflang) URL.
 * Включает: главную, категории, товары (generic + все доменные), услуги, статические страницы.
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

// Типы, для которых URL = /product/{slug} (без типа в пути).
// Синхронизировать с backend TYPES_NEEDING_PATH и frontend needsTypeInPath.
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
  'furniture',
  'tableware',
  'accessory',
  'accessories',
  'books',
  'perfumery',
  'incense',
  'sports',
  'auto_parts',
  'auto-parts',
])

// Доменные эндпоинты: [путь API, product_type для buildProductPath]
// Порядок: сначала самые крупные каталоги.
const DOMAIN_ENDPOINTS: Array<{ path: string; type: string }> = [
  { path: 'catalog/medicines/products', type: 'medicines' },
  { path: 'catalog/supplements/products', type: 'supplements' },
  { path: 'catalog/medical-equipment/products', type: 'medical-equipment' },
  { path: 'catalog/furniture/products', type: 'furniture' },
  { path: 'catalog/books/products', type: 'books' },
  { path: 'catalog/perfumery/products', type: 'perfumery' },
  { path: 'catalog/tableware/products', type: 'tableware' },
  { path: 'catalog/accessories/products', type: 'accessories' },
  { path: 'catalog/incense/products', type: 'incense' },
  { path: 'catalog/sports/products', type: 'sports' },
  { path: 'catalog/auto-parts/products', type: 'auto-parts' },
  { path: 'catalog/clothing/products', type: 'clothing' },
  { path: 'catalog/shoes/products', type: 'shoes' },
  { path: 'catalog/electronics/products', type: 'electronics' },
  { path: 'catalog/jewelry/products', type: 'jewelry' },
  { path: 'catalog/headwear/products', type: 'headwear' },
  { path: 'catalog/underwear/products', type: 'underwear' },
  { path: 'catalog/islamic-clothing/products', type: 'islamic-clothing' },
]

function buildProductPath(slug: string, productType?: string | null): string {
  const normalizedType = (productType || '').trim().replace(/_/g, '-')

  // Deduplicate repeated slug halves (e.g. "cap-cap" → "cap")
  const rawSlug = (slug || '').trim().replace(/_/g, '-')
  const parts = rawSlug.split('-')
  let deduplicatedSlug = rawSlug
  if (parts.length >= 4 && parts.length % 2 === 0) {
    const half = parts.length / 2
    if (parts.slice(0, half).join('-') === parts.slice(half).join('-')) {
      deduplicatedSlug = parts.slice(0, half).join('-')
    }
  }

  if (!normalizedType || BASE_PRODUCT_TYPES.has(normalizedType)) {
    return `/product/${deduplicatedSlug}`
  }

  // Strip type prefix from slug so sitemap URL matches canonical
  // e.g. headwear-carhartt-cap → /product/headwear/carhartt-cap  (not /product/headwear/headwear-carhartt-cap)
  const prefix = `${normalizedType}-`
  let cleanedSlug = deduplicatedSlug
  while (cleanedSlug.startsWith(prefix)) {
    cleanedSlug = cleanedSlug.slice(prefix.length)
  }

  return `/product/${normalizedType}/${cleanedSlug || deduplicatedSlug}`
}

function buildUrl(
  ruPath: string,
  enPath: string,
  changefreq: SitemapUrl['changefreq'] = 'weekly',
  priority = 0.8
): SitemapUrl {
  const ruHref = `${SITE_URL}${ruPath}`
  const enHref = `${SITE_URL}/en${enPath}`
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

async function fetchAllPages(
  apiPath: string,
  params: Record<string, unknown>,
  maxPages = 50
): Promise<any[]> {
  const results: any[] = []
  let page = 1
  let totalPages = 1

  while (page <= totalPages && page <= maxPages) {
    const res = await axios.get(getInternalApiUrl(apiPath), {
      params: { ...params, page },
      timeout: 10000,
    })
    const data = res.data
    const items = data?.results || data || []
    // Use actual items returned on page 1 to calculate real page count.
    // Backend max_page_size may be lower than the requested page_size.
    if (data?.count && page === 1 && items.length > 0) {
      totalPages = Math.ceil(data.count / items.length)
    }
    results.push(...items)
    page++
  }

  return results
}

// Этот компонент не рендерится — данные отдаются через getServerSideProps
export default function Sitemap() {
  return null
}

export const getServerSideProps: GetServerSideProps = async ({ res }) => {
  const today = new Date().toISOString().split('T')[0]

  const urls: SitemapUrl[] = []

  // 1. Статические страницы
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

  // 2. Динамические CMS-страницы (О нас, Доставка, Возврат и т.д.)
  try {
    const pagesRes = await axios.get(getInternalApiUrl('pages/'), {
      params: { is_active: true },
      timeout: 5000,
    })
    const pages = pagesRes.data?.results || pagesRes.data || []
    for (const page of pages) {
      if (page.slug) {
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

  // 3. Категории
  try {
    const categoriesRes = await axios.get(getInternalApiUrl('catalog/categories'), {
      params: { lang: 'en', page_size: 200 },
      timeout: 5000,
    })
    const categories = categoriesRes.data?.results || categoriesRes.data || []
    for (const cat of categories) {
      if (cat.slug) {
        urls.push(buildUrl(`/categories/${cat.slug}`, `/categories/${cat.slug}`, 'daily', 0.8))
      }
    }
  } catch {
    // продолжаем без категорий
  }

  // 4. Товары: generic Product + все доменные модели
  // seenSlugs предотвращает дубли когда доменный товар уже есть в generic таблице через shadow-запись
  const seenSlugs = new Set<string>()

  // 4a. Generic Product (те, у кого есть shadow-запись в базовой таблице)
  try {
    const products = await fetchAllPages('catalog/products/', {
      lang: 'en', page_size: 1000, is_active: true,
    })
    for (const product of products) {
      if (!product.slug) continue
      seenSlugs.add(product.slug)
      const lastmod = product.updated_at
        ? new Date(product.updated_at).toISOString().split('T')[0]
        : today
      const path = buildProductPath(product.slug, product.product_type)
      const url = buildUrl(path, path, 'weekly', 0.7)
      url.lastmod = lastmod
      urls.push(url)
    }
  } catch {
    // продолжаем без generic товаров
  }

  // 4b. Доменные товары (medicines, clothing, books и т.д.)
  // Добавляем только те, чьего slug ещё нет — чтобы не дублировать generic-записи
  for (const endpoint of DOMAIN_ENDPOINTS) {
    try {
      const items = await fetchAllPages(endpoint.path, {
        page_size: 1000, is_active: true,
      })
      for (const item of items) {
        if (!item.slug || seenSlugs.has(item.slug)) continue
        seenSlugs.add(item.slug)
        const lastmod = item.updated_at
          ? new Date(item.updated_at).toISOString().split('T')[0]
          : today
        const path = buildProductPath(item.slug, endpoint.type)
        const url = buildUrl(path, path, 'weekly', 0.7)
        url.lastmod = lastmod
        urls.push(url)
      }
    } catch {
      // продолжаем без этого домена
    }
  }

  // 5. Услуги
  try {
    const services = await fetchAllPages('catalog/services/', {
      lang: 'en', page_size: 1000, is_active: true,
    })
    for (const service of services) {
      if (!service.slug) continue
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
  } catch {
    // продолжаем без услуг
  }

  const sitemap = generateSitemapXml(urls)

  res.setHeader('Content-Type', 'application/xml; charset=utf-8')
  res.setHeader('Cache-Control', 'public, s-maxage=86400, stale-while-revalidate=604800')
  res.write(sitemap)
  res.end()

  return { props: {} }
}
