import Head from 'next/head'
import { useRouter } from 'next/router'

const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || 'https://mudaroba.com').replace(/\/$/, '')
const SITE_NAME = process.env.NEXT_PUBLIC_SITE_NAME || 'Mudaroba'

export interface SEOProps {
  /** Заголовок страницы (без суффикса — суффикс добавляется автоматически) */
  title: string
  /** Meta description */
  description: string
  /** Canonical URL (без домена, например /products/aspirin) */
  canonical?: string
  /** URL OG изображения */
  ogImage?: string
  /** noindex — для страниц поиска, корзины, профиля */
  noindex?: boolean
  /** JSON-LD структурированные данные */
  structuredData?: object | object[]
  /** OG тип страницы */
  ogType?: 'website' | 'product' | 'article'
}

const localeMap: Record<string, string> = {
  ru: 'ru_RU',
  en: 'en_US',
}

/**
 * Универсальный SEO-компонент.
 * Использовать на каждой странице вместо прямого <Head>.
 *
 * @example
 * <SEO
 *   title="Aspirin 500mg"
 *   description="Купить Aspirin 500mg в Турции — доставка по всему миру."
 *   canonical="/product/aspirin-500mg"
 *   structuredData={productJsonLd}
 * />
 */
export default function SEO({
  title,
  description,
  canonical,
  ogImage,
  noindex = false,
  structuredData,
  ogType = 'website',
}: SEOProps) {
  const { locale = 'en', asPath } = useRouter()
  const ogLocale = localeMap[locale] || 'en_US'

  // Строим canonical URL с учётом локали
  const canonicalPath = canonical || asPath.split('?')[0]
  const cleanPath = canonicalPath.replace(/^\/(ru|en)/, '') || '/'

  const canonicalUrl =
    locale === 'ru'
      ? `${SITE_URL}/ru${cleanPath === '/' ? '' : cleanPath}`
      : `${SITE_URL}${cleanPath === '/' ? '' : cleanPath}`

  const fullTitle = `${title} — ${SITE_NAME}`
  const ogImageUrl = ogImage || `${SITE_URL}/og-default.jpg`

  // Нормализуем structuredData в массив
  const schemas = structuredData
    ? Array.isArray(structuredData)
      ? structuredData
      : [structuredData]
    : []

  return (
    <Head>
      {/* Базовые мета */}
      <title>{fullTitle}</title>
      <meta name="description" content={description} />
      {noindex && <meta name="robots" content="noindex, nofollow" />}

      {/* Canonical */}
      <link rel="canonical" href={canonicalUrl} />

      {/* Open Graph */}
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={description} />
      <meta property="og:url" content={canonicalUrl} />
      <meta property="og:type" content={ogType} />
      <meta property="og:locale" content={ogLocale} />
      <meta property="og:image" content={ogImageUrl} />
      <meta property="og:image:width" content="1200" />
      <meta property="og:image:height" content="630" />

      {/* Twitter Card */}
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={description} />
      <meta name="twitter:image" content={ogImageUrl} />

      {/* JSON-LD структурированные данные */}
      {schemas.map((schema, idx) => (
        <script
          key={idx}
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
        />
      ))}
    </Head>
  )
}

// ─── Хелперы для генерации JSON-LD схем ──────────────────────────────────────

/** Organization schema для главной страницы */
export function buildOrganizationSchema() {
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: SITE_NAME,
    url: SITE_URL,
    logo: `${SITE_URL}/logo.png`,
    contactPoint: {
      '@type': 'ContactPoint',
      telephone: '+90-552-582-14-97',
      contactType: 'customer service',
      availableLanguage: ['Russian', 'English'],
    },
    sameAs: [],
  }
}

/** WebSite schema с SearchAction */
export function buildWebSiteSchema() {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: SITE_NAME,
    url: SITE_URL,
    potentialAction: {
      '@type': 'SearchAction',
      target: `${SITE_URL}/search?q={search_term_string}`,
      'query-input': 'required name=search_term_string',
    },
  }
}

/** Product schema для страницы товара */
export function buildProductSchema(product: {
  name: string
  description?: string
  image?: string
  price?: number
  currency?: string
  sku?: string
  brand?: string
  inStock?: boolean
  slug?: string
}) {
  return {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: product.name,
    description: product.description,
    image: product.image,
    sku: product.sku,
    brand: product.brand ? { '@type': 'Brand', name: product.brand } : undefined,
    offers: {
      '@type': 'Offer',
      url: product.slug ? `${SITE_URL}/product/${product.slug}` : SITE_URL,
      priceCurrency: product.currency || 'USD',
      price: product.price,
      availability: product.inStock
        ? 'https://schema.org/InStock'
        : 'https://schema.org/OutOfStock',
      seller: { '@type': 'Organization', name: SITE_NAME },
    },
  }
}

/** BreadcrumbList schema */
export function buildBreadcrumbSchema(
  items: { name: string; url: string }[]
) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, idx) => ({
      '@type': 'ListItem',
      position: idx + 1,
      name: item.name,
      item: item.url.startsWith('http') ? item.url : `${SITE_URL}${item.url}`,
    })),
  }
}
