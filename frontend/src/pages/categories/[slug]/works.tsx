import Link from 'next/link'
import axios from 'axios'
import { GetServerSideProps } from 'next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import ServicePortfolioGallery, { ServicePortfolioItem } from '../../../components/ServicePortfolioGallery'
import { buildProductUrl, getInternalApiUrl, getSiteOrigin } from '../../../lib/urls'
import SEO from '../../../components/SEO'

interface WorksPageProps {
  slug: string
  categoryName: string
  categoryDescription?: string | null
  portfolioItems: ServicePortfolioItem[]
}

export default function CategoryWorksPage({
  slug,
  categoryName,
  categoryDescription,
  portfolioItems,
}: WorksPageProps) {
  const { t } = useTranslation('common')
  const siteUrl = getSiteOrigin()
  const title = `${categoryName} — ${t('service_portfolio_title', 'Примеры оказанных услуг')}`
  const description = (categoryDescription || t('service_portfolio_page_description', 'Подборка реальных кейсов, примеров услуг и реализованных проектов по этой категории.')).trim()
  // Используется в JSON-LD схемах; canonical в <head> строит SEO-компонент с учётом локали
  const canonicalUrl = `${siteUrl}/categories/${slug}/works`
  const ogImage = portfolioItems.find((item) => item.image_url)?.image_url || `${siteUrl}/og-default.png`
  const breadcrumbs = [
    { label: t('breadcrumb_home', 'Главная'), href: '/' },
    { label: t('breadcrumb_categories', 'Категории'), href: '/categories' },
    { label: categoryName, href: `/categories/${slug}` },
    { label: t('service_portfolio_view_all', 'Смотреть все кейсы'), href: `/categories/${slug}/works` },
  ]

  const breadcrumbSchema = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: breadcrumbs.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.label,
      item: `${siteUrl}${item.href}`,
    })),
  }

  const collectionSchema = {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name: title,
    description,
    url: canonicalUrl,
    image: ogImage,
  }

  const portfolioSchema = {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    name: `${categoryName} — ${t('service_portfolio_title', 'Примеры оказанных услуг')}`,
    itemListElement: portfolioItems.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.title,
      url: item.service_slug ? `${siteUrl}${buildProductUrl('uslugi', item.service_slug)}` : canonicalUrl,
      image: item.after_image_url || item.image_url || item.before_image_url || undefined,
      description: item.description || item.result_summary || undefined,
    })),
  }
  const portfolioMediaSchema = portfolioItems.flatMap((item) => {
    const itemUrl = item.service_slug ? `${siteUrl}${buildProductUrl('uslugi', item.service_slug)}` : canonicalUrl
    const descriptionText = item.description || item.result_summary || description
    const mediaObjects: Record<string, unknown>[] = []

    if (item.before_image_url) {
      mediaObjects.push({
        '@context': 'https://schema.org',
        '@type': 'ImageObject',
        name: `${item.title} — ${t('service_portfolio_before', 'До')}`,
        contentUrl: item.before_image_url,
        description: `${t('service_portfolio_before', 'До')}: ${descriptionText}`,
        representativeOfPage: false,
        isPartOf: itemUrl,
      })
    }

    if (item.after_image_url || item.image_url) {
      const contentUrl = item.after_image_url || item.image_url
      mediaObjects.push({
        '@context': 'https://schema.org',
        '@type': 'ImageObject',
        name: `${item.title} — ${t('service_portfolio_after', 'После')}`,
        contentUrl,
        description: `${t('service_portfolio_after', 'После')}: ${descriptionText}`,
        representativeOfPage: true,
        isPartOf: itemUrl,
      })
    }

    if (item.video_url) {
      mediaObjects.push({
        '@context': 'https://schema.org',
        '@type': 'VideoObject',
        name: item.title,
        contentUrl: item.video_url,
        description: descriptionText,
        thumbnailUrl: item.after_image_url || item.image_url || item.before_image_url || ogImage,
        embedUrl: itemUrl,
      })
    }

    return mediaObjects
  })

  return (
    <>
      <SEO
        title={title}
        description={description}
        canonical={`/categories/${slug}/works`}
        ogImage={ogImage}
        structuredData={[
          breadcrumbSchema,
          collectionSchema,
          portfolioSchema,
          ...(portfolioMediaSchema.length ? [portfolioMediaSchema] : []),
        ]}
      />

      <div className="mx-auto max-w-7xl px-3 pt-5 sm:px-6 lg:px-8">
        <nav className="mb-4 flex flex-wrap items-center gap-2 text-sm text-main">
          {breadcrumbs.map((item, idx) => {
            const last = idx === breadcrumbs.length - 1
            return (
              <span key={`${item.href}-${idx}`} className="flex items-center gap-2">
                {last ? (
                  <span className="font-medium text-[var(--text-strong)]">{item.label}</span>
                ) : (
                  <Link href={item.href} className="transition-colors hover:text-[var(--accent)]">
                    {item.label}
                  </Link>
                )}
                {!last ? <span className="text-main/60">/</span> : null}
              </span>
            )
          })}
        </nav>
      </div>

      <div className="mx-auto max-w-7xl px-3 pt-8 pb-4 sm:px-6 lg:px-8">
        <h1 className="text-3xl font-extrabold tracking-tight text-[var(--text-strong)] sm:text-4xl lg:text-5xl">
          {t('service_portfolio_page_title', 'Все кейсы и примеры')}
        </h1>
        <p className="mt-4 max-w-3xl text-base leading-7 text-main sm:text-lg">
          {description}
        </p>
      </div>

      <ServicePortfolioGallery
        items={portfolioItems}
      />
    </>
  )
}

export const getServerSideProps: GetServerSideProps<WorksPageProps> = async (context) => {
  const slug = Array.isArray(context.params?.slug) ? context.params?.slug[0] : context.params?.slug
  if (!slug) {
    return { notFound: true }
  }

  try {
    const res = await axios.get(getInternalApiUrl('catalog/categories'), {
      params: {
        slug,
        include_children: false,
      },
      headers: {
        'Accept-Language': context.locale || 'ru',
        'X-Language': context.locale || 'ru',
      },
    })

    const rows = Array.isArray(res.data) ? res.data : (res.data?.results || [])
    const category = rows[0]
    if (!category) {
      return { notFound: true }
    }

    const portfolioItems = Array.isArray(category.portfolio_items) ? category.portfolio_items : []
    if (!portfolioItems.length) {
      return { notFound: true }
    }

    // Берём локализованное описание: сначала из переводов API, потом fallback на основное поле
    const locale = context.locale || 'ru'
    const translations: Array<{ locale: string; description?: string }> = Array.isArray(category.translations)
      ? category.translations
      : []
    const localizedTranslation = translations.find(
      (tr) => tr.locale === locale || tr.locale === locale.split('-')[0]
    )
    const localizedDescription =
      (localizedTranslation?.description) || category.description || ''

    return {
      props: {
        slug,
        categoryName: category.name || slug,
        categoryDescription: localizedDescription,
        portfolioItems,
        ...(await serverSideTranslations(context.locale ?? 'ru', ['common'])),
      },
    }
  } catch (err) {
    // 404 от API — категории нет; остальное (таймаут, 5xx) пробрасываем,
    // чтобы бот получил 500 и не выкинул страницу из индекса
    if (axios.isAxiosError(err) && err.response?.status === 404) {
      return { notFound: true }
    }
    throw err
  }
}
