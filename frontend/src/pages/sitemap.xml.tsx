import { GetServerSideProps } from 'next'
import axios from 'axios'
import { getInternalApiUrl } from '../lib/urls'
import { SITEMAP_DOMAINS, generateSitemapIndexXml } from '../lib/sitemap'

/**
 * Sitemap-индекс: ссылается на секционные sitemap'ы /sitemaps/<name>.xml.
 *
 * Раньше /sitemap.xml был одним файлом на ~6 МБ и генерировался ~10 секунд —
 * краулер тянул всё целиком при любом изменении. Секции генерируются быстро
 * и кэшируются независимо.
 *
 * Пустые товарные секции в индекс не попадают: urlset без <url> Google считает
 * ошибкой «Тег XML отсутствует» (electronics, medical-equipment, auto-parts, 11.2026).
 */

export default function Sitemap() {
  return null
}

// true — в домене есть товар для sitemap; null — API не ответил.
async function domainHasProducts(domain: string): Promise<boolean | null> {
  try {
    const res = await axios.get(getInternalApiUrl('catalog/sitemap-products'), {
      params: { domain, page_size: 1, cursor: 0 },
      timeout: 10000,
    })
    return (res.data?.results || []).length > 0
  } catch (err) {
    console.error(`Sitemap index: failed to check domain ${domain}`, err)
    return null
  }
}

export const getServerSideProps: GetServerSideProps = async ({ res }) => {
  const today = new Date().toISOString().split('T')[0]

  const checks = await Promise.all(SITEMAP_DOMAINS.map(domainHasProducts))
  // Сбой проверки — секцию оставляем (лучше лишняя пустая, чем выпавшие товары)
  // и индекс не кэшируем.
  const productSections = SITEMAP_DOMAINS
    .filter((_, i) => checks[i] !== false)
    .map((domain) => `products-${domain}`)

  const sections = [
    'static',
    'categories',
    'drugs',
    'brands',
    'services',
    ...productSections,
  ]

  res.setHeader('Content-Type', 'application/xml; charset=utf-8')
  res.setHeader(
    'Cache-Control',
    checks.includes(null) ? 'no-store' : 'public, s-maxage=86400, stale-while-revalidate=604800'
  )
  res.write(generateSitemapIndexXml(sections, today))
  res.end()

  return { props: {} }
}
