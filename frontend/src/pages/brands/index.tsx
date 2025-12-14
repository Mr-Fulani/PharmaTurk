import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import axios from 'axios'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import Masonry from 'react-masonry-css'
import { resolveMediaUrl } from '../../lib/media'
import { getLocalizedBrandName, getLocalizedBrandDescription, BrandTranslation } from '../../lib/i18n'

interface Brand {
  id: number
  name: string
  slug: string
  description?: string
  products_count?: number
  primary_category_slug?: string | null
  card_media_url?: string | null
  logo?: string | null
  translations?: BrandTranslation[]
}

// @ts-ignore: нет типов для @egjs/react-grid
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

const mapCategoryToRouteSlug = (slug?: string | null) => {
  const normalized = (slug || '').trim().toLowerCase().replace(/_/g, '-')
  return normalized || 'medicines'
}

const renderMedia = (mediaUrl?: string | null, alt?: string) => {
  if (!mediaUrl) return null

  const youtubeId = extractYouTubeId(mediaUrl)
  if (youtubeId) {
    const youtubeThumb = getYouTubeThumbnail(mediaUrl)
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

  const src = resolveMediaUrl(mediaUrl)
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
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt || ''}
      className="absolute inset-0 h-full w-full object-cover"
    />
  )
}

export default function BrandsPage({ brands }: { brands: Brand[] }) {
  const { t } = useTranslation('common')
  const router = useRouter()

  const siteUrl = (process.env.NEXT_PUBLIC_SITE_URL || 'https://pharmaturk.ru').replace(/\/$/, '')
  const canonicalUrl = `${siteUrl}/brands`
  const pageTitle = t('brands_page_title', 'Бренды — PharmaTurk')
  const pageDescription = t('brands_page_description', 'Популярные бренды из Турции: одежда, обувь, электроника, аксессуары и товары для здоровья.')

  return (
    <>
      <Head>
        <title>{pageTitle}</title>
        <meta name="description" content={pageDescription} />
        <link rel="canonical" href={canonicalUrl} />
        <link rel="alternate" hrefLang="ru" href={canonicalUrl} />
        <meta property="og:title" content={pageTitle} />
        <meta property="og:description" content={pageDescription} />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:type" content="website" />
        <meta property="twitter:title" content={pageTitle} />
        <meta property="twitter:description" content={pageDescription} />
        <meta property="twitter:card" content="summary_large_image" />
      </Head>

      <main className="min-h-screen bg-page text-main transition-colors duration-200">
        <section className="text-white py-12 dark:bg-[#0a1222]" style={{ backgroundColor: 'var(--accent)' }}>
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col gap-4">
            <div>
              <p className="text-sm uppercase tracking-widest opacity-80">{t('brands', 'Бренды')}</p>
              <h1 className="text-3xl md:text-4xl font-bold mt-1">{t('popular_brands', 'Популярные бренды')}</h1>
              <p className="mt-2 text-lg opacity-90">
                {t('brands_description', 'Выберите бренд, чтобы увидеть товары. Видео и внешние медиа поддерживаются.')}
              </p>
            </div>
          </div>
        </section>

        <section className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          <Masonry
            breakpointCols={{ default: 3, 1024: 3, 768: 2, 640: 1 }}
            className="flex w-full gap-6"
            columnClassName="flex flex-col gap-6"
          >
            {brands.map((brand, idx) => {
              const heights = [224, 256, 288]
              const cardHeight = heights[idx % heights.length]
              const slug = mapCategoryToRouteSlug(brand.primary_category_slug || brand.slug || '')
              const href = `/categories/${slug}?brand_id=${brand.id}`
              return (
                <Link
                  key={brand.id}
                  href={href}
                  style={{ height: cardHeight }}
                  className="relative rounded-xl overflow-hidden block transform hover:scale-[1.02] transition-transform duration-300 shadow-md hover:shadow-xl bg-gray-900/10"
                >
                  {renderMedia(brand.card_media_url || brand.logo, brand.name)}
                  <div className="absolute inset-0 bg-black/35" />
                  <div className="absolute inset-0 flex items-center justify-center p-4 z-10">
                    <div className="text-center text-white drop-shadow">
                      <h3 className="text-xl font-bold mb-1">
                        {getLocalizedBrandName(brand.slug, brand.name, t, brand.translations, router.locale)}
                      </h3>
                      {brand.description ? (
                        <p className="text-sm opacity-90 line-clamp-2">
                          {getLocalizedBrandDescription(brand.slug, brand.description, t, brand.translations, router.locale)}
                        </p>
                      ) : null}
                      {brand.products_count ? (
                        <p className="text-xs opacity-80 mt-2">{brand.products_count} {t('products_count', 'товаров')}</p>
                      ) : null}
                    </div>
                  </div>
                </Link>
              )
            })}
          </Masonry>
          <div className="mt-10 rounded-2xl p-6 text-center text-white shadow-lg dark:bg-[#0a1222]" style={{ backgroundColor: 'var(--accent)' }}>
            <h2 className="text-xl font-semibold mb-2">{t('brands_not_found_title', 'Не нашли нужный бренд?')}</h2>
            <p className="text-sm opacity-90 mb-4">
              {t('brands_not_found_description', 'Напишите нам в чат — поможем подобрать и добавить товары по запросу.')}
            </p>
            <Link
              href="/categories"
              className="inline-flex items-center rounded-lg bg-white/10 px-4 py-2 text-sm font-semibold text-white hover:bg-white/20 transition-colors"
            >
              {t('go_to_catalog', 'Перейти в каталог')}
            </Link>
          </div>
        </section>
      </main>
    </>
  )
}

export const getServerSideProps = async (ctx: any) => {
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'

    let allBrands: Brand[] = []
    let nextUrl: string | null = `${base}/api/catalog/brands?page_size=200`

    while (nextUrl) {
      const res = await axios.get(nextUrl)
      const data = res.data
      const pageBrands = Array.isArray(data) ? data : data.results || []
      allBrands = [...allBrands, ...pageBrands]
      nextUrl = data.next || null
    }

    // Определяем количество товаров для брендов без products_count (или с 0),
    // пробуя подходящий эндпоинт по типу категории.
    const fetchProductCount = async (brand: Brand) => {
      const slug = (brand.primary_category_slug || brand.slug || '').toLowerCase().replace(/_/g, '-')
      const endpoints: string[] = []
      if (slug.startsWith('clothing')) endpoints.push('/api/catalog/clothing/products')
      else if (slug.startsWith('shoes')) endpoints.push('/api/catalog/shoes/products')
      else if (slug.startsWith('electronics')) endpoints.push('/api/catalog/electronics/products')
      // Общий каталог — всегда в конце как fallback
      endpoints.push('/api/catalog/products')

      for (const ep of endpoints) {
        try {
          const res = await axios.get(`${base}${ep}`, {
            params: { brand_id: brand.id, page_size: 1 },
          })
          const data = res.data
          const count = typeof data?.count === 'number' ? data.count : (Array.isArray(data) ? data.length : 0)
          if (count > 0) {
            return count
          }
        } catch {
          // игнорируем и пробуем следующий эндпоинт
        }
      }
      return 0
    }

    const brandsNeedingCount = allBrands.filter((b) => (b.products_count ?? 0) <= 0)
    if (brandsNeedingCount.length) {
      await Promise.all(
        brandsNeedingCount.map(async (b) => {
          const cnt = await fetchProductCount(b)
          b.products_count = cnt
        })
      )
    }

    // Оставляем бренды с товарами (>0), затем сортируем по количеству и имени
    allBrands = allBrands
      .filter((b) => (b.products_count ?? 0) > 0)
      .sort((a, b) => {
      const ca = a.products_count ?? 0
      const cb = b.products_count ?? 0
      if (cb !== ca) return cb - ca
      return (a.name || '').localeCompare(b.name || '')
    })

    return {
      props: {
        brands: allBrands,
        ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
      },
    }
  } catch (e) {
    return {
      props: {
        brands: [],
        ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
      },
    }
  }
}

