import { GetServerSideProps } from 'next'
import axios from 'axios'
import { getInternalApiUrl } from '../../lib/urls'
import {
  SITEMAP_DOMAINS,
  SitemapUrl,
  buildProductPath,
  buildUrl,
  fetchAllPages,
  generateSitemapXml,
} from '../../lib/sitemap'
import { createStaleWhileRevalidateCache } from '../../lib/serverPublicCache'
import { BLOG_ARTICLES } from '../../content/blog/articles'

/**
 * Секционные sitemap'ы: /sitemaps/<section>.xml (rewrite в next.config.js
 * срезает .xml). Секции: static (вместе со статьями блога), categories (вместе с
 * подборками категорий), drugs (страницы препаратов /drugs/<slug>), brands, services,
 * products-<домен>. Индекс — /sitemap.xml.
 */

interface SitemapTestimonial {
  id: number
}

// Сюда сборщики пишут, какой запрос к API не удался: такая секция неполная.
type Failures = string[]

async function buildStaticUrls(today: string, failures: Failures): Promise<SitemapUrl[]> {
  const urls: SitemapUrl[] = []

  // 1. Статические страницы
  const basePages: Array<[string, string, SitemapUrl['changefreq'], number]> = [
    ['/', '/', 'daily', 1.0],
    ['/categories', '/categories', 'daily', 0.9],
    ['/brands', '/brands', 'weekly', 0.7],
    ['/how-to-order-medicines', '/how-to-order-medicines', 'monthly', 0.8],
    ['/testimonials', '/testimonials', 'weekly', 0.6],
    ['/delivery', '/delivery', 'monthly', 0.6],
    ['/returns', '/returns', 'monthly', 0.5],
    ['/privacy', '/privacy', 'monthly', 0.4],
    ['/blog', '/blog', 'weekly', 0.6],
  ]

  for (const [enPath, ruPath, changefreq, priority] of basePages) {
    urls.push(buildUrl(enPath, ruPath, changefreq, priority))
  }
  for (const article of BLOG_ARTICLES) {
    const url = buildUrl(`/blog/${article.slug}`, `/blog/${article.slug}`, 'monthly', 0.7)
    url.lastmod = article.updatedAt
    urls.push(url)
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
    failures.push('pages')
    console.error('Sitemap: Failed to fetch dynamic pages', err)
  }

  // 3. Отзывы — отдельные страницы для индексации каждого отзыва
  try {
    const testimonialsRes = await axios.get(getInternalApiUrl('feedback/testimonials'), {
      timeout: 5000,
    })
    const testimonials: SitemapTestimonial[] = testimonialsRes.data?.results || testimonialsRes.data || []
    for (const testimonial of testimonials) {
      if (!testimonial?.id) continue
      urls.push(buildUrl(`/testimonials/${testimonial.id}`, `/testimonials/${testimonial.id}`, 'weekly', 0.5))
    }
  } catch (err) {
    failures.push('testimonials')
    console.error('Sitemap: Failed to fetch testimonials', err)
  }

  return urls
}

async function buildCategoryUrls(failures: Failures): Promise<SitemapUrl[]> {
  const urls: SitemapUrl[] = []
  const seenSlugs = new Set<string>()
  const HIGH_PRIORITY_CATEGORIES = new Set(['medicines', 'supplements', 'uslugi'])
  try {
    // Dedicated endpoint returns every active category (including descendants)
    // without computing product counters, SEO fallbacks and portfolio payloads.
    const categories = await fetchAllPages('catalog/sitemap-entries', {
      kind: 'categories', page_size: 500,
    })
    for (const cat of categories) {
      if (cat.slug && !seenSlugs.has(cat.slug)) {
        seenSlugs.add(cat.slug)
        const priority = HIGH_PRIORITY_CATEGORIES.has(cat.slug) ? 0.95 : 0.8
        const url = buildUrl(`/categories/${cat.slug}`, `/categories/${cat.slug}`, 'daily', priority)
        if (cat.updated_at) {
          url.lastmod = new Date(cat.updated_at).toISOString().split('T')[0]
        }
        urls.push(url)
      }
    }
  } catch (err) {
    failures.push('categories')
    console.error('Sitemap: Failed to fetch categories', err)
  }
  try {
    // Подборки категорий (/categories/<категория>/<подборка>); пустые API не отдаёт
    const collections = await fetchAllPages('catalog/sitemap-entries', { kind: 'collections' })
    for (const item of collections) {
      if (!item.slug || !item.parent_slug) continue
      const path = `/categories/${item.parent_slug}/${item.slug}`
      const url = buildUrl(path, path, 'daily', 0.8)
      if (item.updated_at) {
        url.lastmod = new Date(item.updated_at).toISOString().split('T')[0]
      }
      urls.push(url)
    }
  } catch (err) {
    failures.push('collections')
    console.error('Sitemap: Failed to fetch category collections', err)
  }
  return urls
}

async function buildDrugGroupUrls(failures: Failures): Promise<SitemapUrl[]> {
  const urls: SitemapUrl[] = []
  try {
    // Страницы препаратов; без форм на витрине API их не отдаёт
    const groups = await fetchAllPages('catalog/sitemap-entries', { kind: 'drug_groups' })
    for (const item of groups) {
      if (!item.slug) continue
      const path = `/drugs/${item.slug}`
      const url = buildUrl(path, path, 'weekly', 0.8)
      if (item.updated_at) {
        url.lastmod = new Date(item.updated_at).toISOString().split('T')[0]
      }
      urls.push(url)
    }
  } catch (err) {
    failures.push('drug_groups')
    console.error('Sitemap: Failed to fetch drug groups', err)
  }
  return urls
}

async function buildBrandUrls(today: string, failures: Failures): Promise<SitemapUrl[]> {
  const urls: SitemapUrl[] = []
  const seenSlugs = new Set<string>()
  try {
    const brands = await fetchAllPages('catalog/sitemap-entries', {
      kind: 'brands', page_size: 500,
    })
    for (const brand of brands) {
      if (!brand.slug || seenSlugs.has(brand.slug)) continue
      seenSlugs.add(brand.slug)
      const lastmod = brand.updated_at
        ? new Date(brand.updated_at).toISOString().split('T')[0]
        : today
      const url = buildUrl(`/brand/${brand.slug}`, `/brand/${brand.slug}`, 'weekly', 0.65)
      url.lastmod = lastmod
      urls.push(url)
    }
  } catch (err) {
    failures.push('brands')
    console.error('Sitemap: Failed to fetch brands', err)
  }
  return urls
}

async function buildServiceUrls(today: string, failures: Failures): Promise<SitemapUrl[]> {
  const urls: SitemapUrl[] = []
  const seenSlugs = new Set<string>()
  try {
    const services = await fetchAllPages('catalog/sitemap-entries', {
      kind: 'services', page_size: 500,
    })
    for (const service of services) {
      if (!service.slug || seenSlugs.has(service.slug)) continue
      seenSlugs.add(service.slug)
      const lastmod = service.updated_at
        ? new Date(service.updated_at).toISOString().split('T')[0]
        : today
      const servicePath = buildProductPath(service.slug, 'uslugi')
      const url = buildUrl(servicePath, servicePath, 'weekly', 0.75)
      url.lastmod = lastmod
      urls.push(url)
    }
  } catch (err) {
    failures.push('services')
    console.error('Sitemap: Failed to fetch services', err)
  }
  return urls
}

async function buildDomainProductUrls(domain: string, today: string, failures: Failures): Promise<SitemapUrl[]> {
  // Лёгкий эндпоинт /api/catalog/sitemap-products?domain=X — только slug + updated_at.
  const urls: SitemapUrl[] = []
  const seenSlugs = new Set<string>()
  try {
    const items = await fetchAllPages('catalog/sitemap-products', {
      domain,
      page_size: 500,
      cursor: 0,
    })
    for (const item of items) {
      if (!item.slug || seenSlugs.has(item.slug)) continue
      seenSlugs.add(item.slug)
      const lastmod = item.updated_at
        ? new Date(item.updated_at).toISOString().split('T')[0]
        : today
      const path = buildProductPath(item.slug, item.product_type)
      const url = buildUrl(path, path, 'weekly', 0.7)
      url.lastmod = lastmod
      urls.push(url)
    }
  } catch (err) {
    failures.push(`products-${domain}`)
    console.error(`Sitemap: Failed to fetch products for domain ${domain}`, err)
  }
  return urls
}

export default function SitemapSection() {
  return null
}

interface SectionXml {
  xml: string
  complete: boolean
  empty: boolean
}

// Холодная сборка products-medicines — ~25 последовательных запросов к API
// (~20 с). Готовый XML живёт в памяти процесса: после первой сборки ответ не
// ждёт API, устаревшая секция пересобирается в фоне. Неполные (сбой API) и
// пустые не кэшируем.
const SECTION_FRESH_MS = 6 * 60 * 60 * 1000
const sectionXmlCache = createStaleWhileRevalidateCache({
  freshMs: SECTION_FRESH_MS,
  shouldStore: (section: SectionXml) => section.complete && !section.empty,
})

function isKnownSection(section: string): boolean {
  if (['static', 'categories', 'drugs', 'brands', 'services'].includes(section)) return true
  return section.startsWith('products-') && SITEMAP_DOMAINS.includes(section.slice('products-'.length))
}

async function buildSectionUrls(section: string, failures: Failures): Promise<SitemapUrl[]> {
  const today = new Date().toISOString().split('T')[0]
  if (section === 'static') return buildStaticUrls(today, failures)
  if (section === 'categories') return buildCategoryUrls(failures)
  if (section === 'drugs') return buildDrugGroupUrls(failures)
  if (section === 'brands') return buildBrandUrls(today, failures)
  if (section === 'services') return buildServiceUrls(today, failures)
  return buildDomainProductUrls(section.slice('products-'.length), today, failures)
}

async function buildSectionXml(section: string): Promise<SectionXml> {
  const failures: Failures = []
  const urls = await buildSectionUrls(section, failures)
  return { xml: generateSitemapXml(urls), complete: failures.length === 0, empty: urls.length === 0 }
}

export const getServerSideProps: GetServerSideProps = async ({ params, res }) => {
  const raw = typeof params?.section === 'string' ? params.section : ''
  const section = raw.replace(/\.xml$/, '')

  if (!isKnownSection(section)) {
    return { notFound: true }
  }
  const { xml, complete, empty }: SectionXml = await sectionXmlCache.get(section, () => buildSectionXml(section))

  res.setHeader('Content-Type', 'application/xml; charset=utf-8')
  if (complete) {
    res.setHeader('Cache-Control', 'public, s-maxage=86400, stale-while-revalidate=604800')
  } else {
    // Сбой API: раньше Cloudflare сутки держал пустую секцию. Неполную не
    // кэшируем, а пустую отдаём 503 — бот повторит позже, URL не выпадут.
    res.setHeader('Cache-Control', 'no-store')
    if (empty) {
      res.statusCode = 503
      res.setHeader('Retry-After', '300')
    }
  }
  res.write(xml)
  res.end()

  return { props: {} }
}
