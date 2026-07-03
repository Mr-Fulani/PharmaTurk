import { GetServerSideProps } from 'next'
import { SITEMAP_DOMAINS, generateSitemapIndexXml } from '../lib/sitemap'

/**
 * Sitemap-индекс: ссылается на секционные sitemap'ы /sitemaps/<name>.xml.
 *
 * Раньше /sitemap.xml был одним файлом на ~6 МБ и генерировался ~10 секунд —
 * краулер тянул всё целиком при любом изменении. Секции генерируются быстро
 * и кэшируются независимо; сам индекс — статический список.
 */

export default function Sitemap() {
  return null
}

export const getServerSideProps: GetServerSideProps = async ({ res }) => {
  const today = new Date().toISOString().split('T')[0]

  const sections = [
    'static',
    'categories',
    'brands',
    'services',
    ...SITEMAP_DOMAINS.map((domain) => `products-${domain}`),
  ]

  res.setHeader('Content-Type', 'application/xml; charset=utf-8')
  res.setHeader('Cache-Control', 'public, s-maxage=86400, stale-while-revalidate=604800')
  res.write(generateSitemapIndexXml(sections, today))
  res.end()

  return { props: {} }
}
