import Head from 'next/head'
import axios from 'axios'
import Link from 'next/link'
import { useRouter } from 'next/router'
import Masonry from 'react-masonry-css'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import BannerCarousel from '../../components/BannerCarouselMedia'
import CardMasonryMedia from '../../components/CardMasonryMedia'
import { getLocalizedCategoryName, getLocalizedCategoryDescription } from '../../lib/i18n'

interface CategoryTranslation {
  locale: string
  name: string
  description?: string
}

interface Category {
  id: number
  name: string
  slug: string
  description?: string
  products_count?: number
  parent?: number | null
  gender?: string | null
  clothing_type?: string | null
  device_type?: string | null
  card_media_url?: string | null
  translations?: CategoryTranslation[]
  displaySlug?: string
}

// @ts-ignore: нет типов для @egjs/react-grid
export default function CategoriesPage({ categories, locale: propLocale }: { categories: Category[]; locale?: string }) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const locale = router.locale || propLocale || 'ru'

  return (
    <>
      <Head>
        <title>{t('menu_categories', 'Категории')} — Turk-Export</title>
      </Head>
      <main className="min-h-screen bg-page text-main transition-colors duration-200">
        {/* Hero banner */}
        <section className="text-white py-12 dark:bg-[#0a1222]" style={{ backgroundColor: 'var(--accent)' }}>
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col gap-4">
            <div>
              <p className="text-sm uppercase tracking-widest opacity-80">{t('categories_catalog', 'Каталог')}</p>
              <h1 className="text-3xl md:text-4xl font-bold mt-1">{t('categories_title', 'Категории товаров')}</h1>
              <p className="mt-2 text-lg opacity-90">
                {t('categories_description', 'Выберите основную категорию — карточки и баннеры как на главной.')}
              </p>
            </div>
          </div>
        </section>

        {/* Main banner from CMS */}
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 mt-8 mb-8">
          <BannerCarousel position="main" />
              </div>

        {/* Cards grid */}
        <section className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pb-12">
          <Masonry
            breakpointCols={{ default: 3, 1024: 3, 768: 2, 640: 1 }}
            className="flex w-full gap-6"
            columnClassName="flex flex-col gap-6"
          >
            {categories.map((c, idx) => {
              const heights = [224, 256, 288]
              const cardHeight = heights[idx % heights.length]
              const hrefSlug = c.displaySlug || c.slug
              return (
                <Link
                  key={c.id}
                  href={`/categories/${hrefSlug}`}
                  style={{ height: cardHeight }}
                  className="relative isolate rounded-xl overflow-hidden block transform hover:scale-[1.02] transition-transform duration-300 shadow-md hover:shadow-xl bg-[var(--surface)]"
                >
                  <div className="absolute inset-0 z-0 overflow-hidden">
                    <CardMasonryMedia
                      mediaUrl={c.card_media_url}
                      alt={getLocalizedCategoryName(c.slug, c.name, t, c.translations, locale)}
                      placeholderType="category"
                      id={c.id}
                    />
                  </div>
                  <div className="absolute inset-0 z-[1] bg-[var(--text-strong)]/20" />
                  <div className="absolute inset-0 z-10 flex items-center justify-center p-4">
                    <div className="text-center text-white drop-shadow">
                      <h3 className="text-xl font-bold mb-1">{getLocalizedCategoryName(c.slug, c.name, t, c.translations, locale)}</h3>
                      {getLocalizedCategoryDescription(c.slug, c.description, t, c.translations, locale) ? (
                        <p className="text-sm opacity-90 line-clamp-2">{getLocalizedCategoryDescription(c.slug, c.description, t, c.translations, locale)}</p>
                      ) : null}
                      {c.products_count ? (
                        <p className="text-xs opacity-80 mt-2">{c.products_count} {t('products_count', 'товаров')}</p>
                      ) : null}
                    </div>
                  </div>
                </Link>
              )
            })}
          </Masonry>
          <div className="mt-10 rounded-2xl p-6 text-center text-white shadow-lg dark:bg-[#0a1222]" style={{ backgroundColor: 'var(--accent)' }}>
            <h2 className="text-xl font-semibold mb-2">{t('categories_not_found_title', 'Не нашли нужную категорию?')}</h2>
            <p className="text-sm opacity-90 mb-4">
              {t('categories_not_found_description', 'Напишите нам в чат — подскажем и подберём товары под ваш запрос.')}
            </p>
            <Link
              href="/brands"
              className="inline-flex items-center rounded-lg bg-white/10 px-4 py-2 text-sm font-semibold text-white hover:bg-white/20 transition-colors"
            >
              {t('view_brands', 'Посмотреть бренды')}
            </Link>
          </div>
        </section>
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  try {
    const { getInternalApiUrl } = await import('../../lib/urls')
    const { fetchFooterSettings } = await import('../../lib/footerSettings')
    const res = await axios.get(getInternalApiUrl('catalog/categories'), {
      params: { top_level: true, page_size: 200 }
    })
    const all: Category[] = Array.isArray(res.data) ? res.data : (res.data.results || [])

    // Нормализуем слуги и устраняем дубли
    const normalizeSlug = (value: any) =>
      (value || '')
        .toString()
        .trim()
        .toLowerCase()
        .replace(/_/g, '-')
    // Only exact slug matches for canonical types — no partial matching
    // (partial matching caused e.g. "islamic-clothing" to merge with "clothing")
    const resolveCanonicalSlug = (slug: string) => {
      return normalizeSlug(slug)
    }
    const uniqueMap = new Map<string, Category>()
    all.forEach((c) => {
      const normSlug = normalizeSlug(c.slug)
      const canonicalSlug = resolveCanonicalSlug(normSlug)
      const next = { ...c, slug: normSlug, displaySlug: canonicalSlug }
      const existing = uniqueMap.get(canonicalSlug)
      if (!existing) {
        uniqueMap.set(canonicalSlug, next)
        return
      }
      const existingCount = (existing as any).products_count ?? 0
      const nextCount = (next as any).products_count ?? 0
      if (nextCount > existingCount) {
        uniqueMap.set(canonicalSlug, next)
      }
    })

    const categories = Array.from(uniqueMap.values())
      .filter((c) => {
        const isRoot = c.parent === null || typeof c.parent === 'undefined'
        if (!isRoot) return false
        if (c.gender) return false
        if (c.clothing_type) return false
        if (c.device_type) return false
        return true
      })
      .sort((a, b) => {
        const sa = (a as any).sort_order ?? 0
        const sb = (b as any).sort_order ?? 0
        return sa - sb
      })

    const footerSettings = await fetchFooterSettings()
    return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), categories, footerSettings, locale: ctx.locale ?? 'ru' } }
  } catch (e) {
    const { fetchFooterSettings } = await import('../../lib/footerSettings')
    const footerSettings = await fetchFooterSettings()
    return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), categories: [], footerSettings, locale: ctx.locale ?? 'ru' } }
  }
}
