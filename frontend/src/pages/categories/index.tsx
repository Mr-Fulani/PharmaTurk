import Head from 'next/head'
import axios from 'axios'
import Link from 'next/link'
import { useRouter } from 'next/router'
import Masonry from 'react-masonry-css'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import BannerCarousel from '../../components/BannerCarouselMedia'
import { getPlaceholderImageUrl, resolveMediaUrl } from '../../lib/media'
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
  card_media_url?: string | null
  translations?: CategoryTranslation[]
}

// @ts-ignore: нет типов для @egjs/react-grid
export default function CategoriesPage({ categories, locale: propLocale }: { categories: Category[]; locale?: string }) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const locale = router.locale || propLocale || 'ru'

  const extractYouTubeId = (url?: string | null) => {
    if (!url) return null
    const match =
      url.match(/(?:youtube\.com\/(?:[^/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|m\.youtube\.com\/watch\?v=)([^"&?/\\s]{11})/) ||
      url.match(/(?:youtube\.com\/shorts\/|m\.youtube\.com\/shorts\/)([^"&?/\\s]+)/)
    return match && match[1] ? match[1] : null
  }

  const getYouTubeThumbnail = (url?: string | null) => {
    const youtubeId = extractYouTubeId(url)
    return youtubeId ? `https://img.youtube.com/vi/${youtubeId}/hqdefault.jpg` : null
  }

  const renderMedia = (mediaUrl?: string | null, alt?: string, id?: number) => {
    const effectiveUrl = mediaUrl || getPlaceholderImageUrl({ type: 'category', id })

    const youtubeId = extractYouTubeId(effectiveUrl)
    if (youtubeId) {
      const youtubeThumb = getYouTubeThumbnail(effectiveUrl)
      const base = `https://www.youtube-nocookie.com/embed/${youtubeId}`
      const params = [
        'autoplay=1',
        'mute=1',
        'loop=1',
        `playlist=${youtubeId}`,
        'controls=0',
        'playsinline=1',
        'rel=0',
        'modestbranding=1',
        'iv_load_policy=3',
        'cc_load_policy=0',
        'fs=0',
        'disablekb=1',
        'showinfo=0',
        'autohide=1',
      ].join('&')
      const embedUrl = `${base}?${params}`
      return (
        <div className="absolute inset-0 h-full w-full overflow-hidden">
          {youtubeThumb && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={youtubeThumb}
              alt={alt || ''}
              className="absolute inset-0 h-full w-full object-cover"
            />
          )}
          <iframe
            src={embedUrl}
            title={alt || 'YouTube'}
            className="absolute inset-0 h-full w-full object-cover"
            allow="autoplay; encrypted-media; picture-in-picture"
            loading="lazy"
            style={{ opacity: 0, transition: 'opacity 0.4s ease' }}
            onLoad={(e) => {
              const el = e.currentTarget
              setTimeout(() => {
                el.style.opacity = '1'
              }, 3100) // скрываем стартовые оверлеи YouTube
            }}
            allowFullScreen={false}
          />
        </div>
      )
    }

    // Обычная обработка файла/изображения
    const src = resolveMediaUrl(effectiveUrl)
    if (!src) return null

    const normalized = src.split('?')[0].toLowerCase()
    const isVideo = /\.(mp4|mov|webm|m4v)$/i.test(normalized)

    if (isVideo) {
      return (
        <video
          className="absolute inset-0 h-full w-full object-cover"
          autoPlay
          muted
          loop
          playsInline
        >
          <source src={src} />
        </video>
      )
    }

    return (
      <img
        src={src}
        alt={alt || ''}
        className="absolute inset-0 h-full w-full object-cover"
      />
    )
  }

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
              return (
                <Link
                  key={c.id}
                  href={`/categories/${c.slug}`}
                  style={{ height: cardHeight }}
                  className="relative rounded-xl overflow-hidden block transform hover:scale-[1.02] transition-transform duration-300 shadow-md hover:shadow-xl bg-[var(--surface)]"
                >
                  {renderMedia(
                    c.card_media_url,
                    getLocalizedCategoryName(c.slug, c.name, t, c.translations, locale),
                    c.id
                  )}
                  <div className="absolute inset-0 bg-[var(--text-strong)]/20" />
                  <div className="absolute inset-0 flex items-center justify-center p-4 z-10">
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
    const res = await axios.get(getInternalApiUrl('catalog/categories'), {
      params: { top_level: true, page_size: 200 }
    })
    const all: Category[] = Array.isArray(res.data) ? res.data : (res.data.results || [])

    // Нормализуем слуги (underscores -> dash) и устраняем дубли
    const uniqueMap = new Map<string, Category>()
    all.forEach((c) => {
      const normSlug = (c.slug || '').replace(/_/g, '-')
      if (!uniqueMap.has(normSlug)) {
        uniqueMap.set(normSlug, { ...c, slug: normSlug })
      }
    })

    const categories = Array.from(uniqueMap.values())
      .sort((a, b) => {
        const sa = (a as any).sort_order ?? 0
        const sb = (b as any).sort_order ?? 0
        return sa - sb
      })

    return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), categories, locale: ctx.locale ?? 'ru' } }
  } catch (e) {
    return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), categories: [], locale: ctx.locale ?? 'ru' } }
  }
}
