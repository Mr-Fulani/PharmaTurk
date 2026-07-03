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

/**
 * Секционные sitemap'ы: /sitemaps/<section>.xml (rewrite в next.config.js
 * срезает .xml). Секции: static, categories, brands, services,
 * products-<домен>. Индекс — /sitemap.xml.
 */

interface SitemapTestimonial {
  id: number
}

async function buildStaticUrls(today: string): Promise<SitemapUrl[]> {
  const urls: SitemapUrl[] = []

  // 1. Статические страницы
  const basePages: Array<[string, string, SitemapUrl['changefreq'], number]> = [
    ['/', '/', 'daily', 1.0],
    ['/categories', '/categories', 'daily', 0.9],
    ['/brands', '/brands', 'weekly', 0.7],
    ['/how-to-order-medicines', '/how-to-order-medicines', 'monthly', 0.5],
    ['/testimonials', '/testimonials', 'weekly', 0.6],
    ['/delivery', '/delivery', 'monthly', 0.6],
    ['/returns', '/returns', 'monthly', 0.5],
    ['/privacy', '/privacy', 'monthly', 0.4],
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
    console.error('Sitemap: Failed to fetch testimonials', err)
  }

  return urls
}

async function buildCategoryUrls(): Promise<SitemapUrl[]> {
  const urls: SitemapUrl[] = []
  const HIGH_PRIORITY_CATEGORIES = new Set(['medicines', 'supplements', 'uslugi'])
  try {
    const categories = await fetchAllPages('catalog/categories', { lang: 'en', page_size: 1000 })
    for (const cat of categories) {
      if (cat.slug) {
        const priority = HIGH_PRIORITY_CATEGORIES.has(cat.slug) ? 0.95 : 0.8
        urls.push(buildUrl(`/categories/${cat.slug}`, `/categories/${cat.slug}`, 'daily', priority))
      }
    }
  } catch {
    // продолжаем без категорий
  }
  return urls
}

async function buildBrandUrls(today: string): Promise<SitemapUrl[]> {
  const urls: SitemapUrl[] = []
  try {
    const brands = await fetchAllPages('catalog/brands', { page_size: 1000, is_active: true })
    for (const brand of brands) {
      if (!brand.slug) continue
      const lastmod = brand.updated_at
        ? new Date(brand.updated_at).toISOString().split('T')[0]
        : today
      const url = buildUrl(`/brand/${brand.slug}`, `/brand/${brand.slug}`, 'weekly', 0.65)
      url.lastmod = lastmod
      urls.push(url)
    }
  } catch (err) {
    console.error('Sitemap: Failed to fetch brands', err)
  }
  return urls
}

async function buildServiceUrls(today: string): Promise<SitemapUrl[]> {
  const urls: SitemapUrl[] = []
  try {
    const services = await fetchAllPages('catalog/services', {
      lang: 'en', page_size: 1000, is_active: true,
    })
    for (const service of services) {
      if (!service.slug) continue
      const lastmod = service.updated_at
        ? new Date(service.updated_at).toISOString().split('T')[0]
        : today
      const servicePath = buildProductPath(service.slug, 'uslugi')
      const url = buildUrl(servicePath, servicePath, 'weekly', 0.75)
      url.lastmod = lastmod
      urls.push(url)
    }
  } catch (err) {
    console.error('Sitemap: Failed to fetch services', err)
  }
  return urls
}

async function buildDomainProductUrls(domain: string, today: string): Promise<SitemapUrl[]> {
  // Лёгкий эндпоинт /api/catalog/sitemap-products?domain=X — только slug + updated_at.
  const urls: SitemapUrl[] = []
  const seenSlugs = new Set<string>()
  try {
    const items = await fetchAllPages('catalog/sitemap-products', { domain, page_size: 500 })
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
    console.error(`Sitemap: Failed to fetch products for domain ${domain}`, err)
  }
  return urls
}

export default function SitemapSection() {
  return null
}

export const getServerSideProps: GetServerSideProps = async ({ params, res }) => {
  const raw = typeof params?.section === 'string' ? params.section : ''
  const section = raw.replace(/\.xml$/, '')
  const today = new Date().toISOString().split('T')[0]

  let urls: SitemapUrl[] | null = null
  if (section === 'static') {
    urls = await buildStaticUrls(today)
  } else if (section === 'categories') {
    urls = await buildCategoryUrls()
  } else if (section === 'brands') {
    urls = await buildBrandUrls(today)
  } else if (section === 'services') {
    urls = await buildServiceUrls(today)
  } else if (section.startsWith('products-')) {
    const domain = section.slice('products-'.length)
    if (SITEMAP_DOMAINS.includes(domain)) {
      urls = await buildDomainProductUrls(domain, today)
    }
  }

  if (urls === null) {
    return { notFound: true }
  }

  res.setHeader('Content-Type', 'application/xml; charset=utf-8')
  res.setHeader('Cache-Control', 'public, s-maxage=86400, stale-while-revalidate=604800')
  res.write(generateSitemapXml(urls))
  res.end()

  return { props: {} }
}
