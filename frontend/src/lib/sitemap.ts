import axios from 'axios'
import { getInternalApiUrl } from './urls'

/**
 * Общие помощники генерации sitemap.
 * /sitemap.xml — индекс, секции — /sitemaps/<name>.xml (pages/sitemaps/[section].tsx).
 */

export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || 'https://mudaroba.com').replace(/\/$/, '')

export interface SitemapUrl {
  loc: string
  lastmod?: string
  changefreq?: 'always' | 'hourly' | 'daily' | 'weekly' | 'monthly' | 'yearly' | 'never'
  priority?: number
  alternates?: { lang: string; href: string }[]
}

function escapeXml(value: string): string {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

// Типы, для которых URL = /product/{slug} (без типа в пути).
// Синхронизировать с backend TYPES_NEEDING_PATH и frontend needsTypeInPath.
export const BASE_PRODUCT_TYPES = new Set([
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

// Все доменные типы товаров для sitemap-products эндпоинта.
// Используется лёгкий /api/catalog/sitemap-products?domain=X — только slug + updated_at.
export const SITEMAP_DOMAINS = [
  'clothing', 'shoes', 'electronics', 'jewelry', 'headwear', 'underwear', 'islamic-clothing',
  'medicines', 'supplements', 'medical-equipment', 'furniture', 'books',
  'perfumery', 'tableware', 'accessories', 'incense', 'sports', 'auto-parts',
]

export function buildProductPath(slug: string, productType?: string | null): string {
  const normalizedType = (productType || '').trim().replace(/_/g, '-')

  // Deduplicate repeated slug halves (e.g. "cap-cap" → "cap")
  const rawSlug = (slug || '').trim()
  if (normalizedType === 'uslugi') {
    return `/product/uslugi/${rawSlug}`
  }

  const normalizedSlug = rawSlug.replace(/_/g, '-')
  const parts = normalizedSlug.split('-')
  let deduplicatedSlug = normalizedSlug
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

export function buildUrl(
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

export function generateSitemapXml(urls: SitemapUrl[]): string {
  const urlsXml = urls
    .map((url) => {
      const alternatesXml = (url.alternates || [])
        .map(
          (alt) =>
            `    <xhtml:link rel="alternate" hreflang="${escapeXml(alt.lang)}" href="${escapeXml(alt.href)}"/>`
        )
        .join('\n')

      return `  <url>
    <loc>${escapeXml(url.loc)}</loc>
    ${url.lastmod ? `<lastmod>${escapeXml(url.lastmod)}</lastmod>` : ''}
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

export function generateSitemapIndexXml(sections: string[], lastmod: string): string {
  const items = sections
    .map(
      (name) => `  <sitemap>
    <loc>${escapeXml(`${SITE_URL}/sitemaps/${name}.xml`)}</loc>
    <lastmod>${escapeXml(lastmod)}</lastmod>
  </sitemap>`
    )
    .join('\n')

  return `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${items}
</sitemapindex>`
}

export async function fetchAllPages(
  apiPath: string,
  params: Record<string, unknown>,
  // One sitemap may contain up to 50,000 URLs. The compact endpoints cap a
  // page at 500 rows, so 100 pages covers the complete standards-compliant file.
  maxPages = 100
): Promise<any[]> {
  const results: any[] = []
  let page = 1
  let totalPages = 1

  while (page <= totalPages && page <= maxPages) {
    const res = await axios.get(getInternalApiUrl(apiPath), {
      params: { ...params, page },
      timeout: 30000,
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
