import Head from 'next/head'
import Link from 'next/link'
import Image from 'next/image'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import dynamic from 'next/dynamic'
import { getPlaceholderImageUrl, resolveMediaUrl, isVideoUrl } from '../lib/media'
import { getSiteOrigin } from '../lib/urls'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import { GetServerSideProps } from 'next'
import axios from 'axios'
import BannerCarousel from '../components/BannerCarouselMedia'
import { getLocalizedCategoryName, getLocalizedCategoryDescription, getLocalizedBrandName, getLocalizedBrandDescription, BrandTranslation } from '../lib/i18n'

// Dynamic imports для компонентов ниже fold — уменьшают initial JS bundle
const PopularProductsCarousel = dynamic(() => import('../components/PopularProductsCarousel'), { ssr: false })
const PersonalizedRecommendations = dynamic(() => import('../components/PersonalizedRecommendations'), { ssr: false })
const TestimonialsCarousel = dynamic(() => import('../components/TestimonialsCarousel'), { ssr: false })

interface Brand {
  id: number
  name: string
  slug: string
  description: string
  logo?: string
  website?: string
  products_count?: number
  primary_category_slug?: string | null
  card_media_url?: string | null
  translations?: BrandTranslation[]
}

interface CategoryTranslation {
  locale: string
  name: string
  description?: string
}

interface CategoryCard {
  id: number
  name: string
  slug: string
  description: string
  card_media_url?: string | null
  parent?: number | null
  sort_order?: number | null
  products_count?: number
  gender?: string | null
  clothing_type?: string | null
  device_type?: string | null
  translations?: CategoryTranslation[]
}

interface HomePageProps {
  brands: Brand[]
  categories: CategoryCard[]
  firstBannerImageUrl?: string | null
  firstBannerTitle?: string | null
}

const LazyYouTube = ({ youtubeId, youtubeThumb, title, alt }: { youtubeId: string, youtubeThumb: string | null, title?: string, alt?: string }) => {
  const [loadIframe, setLoadIframe] = useState(false)

  // Загружаем iframe с задержкой, чтобы не блокировать LCP и initial JS bundle
  useEffect(() => {
    const timer = setTimeout(() => {
      setLoadIframe(true)
    }, 2500)
    return () => clearTimeout(timer)
  }, [])

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
    <div 
      className="pointer-events-none absolute inset-0 h-full w-full overflow-hidden"
      onMouseEnter={() => setLoadIframe(true)}
      onClick={() => setLoadIframe(true)}
    >
      {youtubeThumb && (
        <Image
          src={youtubeThumb}
          alt={alt || title || 'Video thumbnail'}
          loading="lazy"
          fill
          unoptimized={false}
          className={`pointer-events-none absolute inset-0 object-cover transition-opacity duration-700 ${loadIframe ? 'opacity-0' : 'opacity-100'}`}
        />
      )}
      {loadIframe && (
        <iframe
          src={embedUrl}
          title={alt || title || 'YouTube'}
          className="pointer-events-none absolute inset-0 h-full w-full object-cover"
          allow="autoplay; encrypted-media; picture-in-picture"
          loading="lazy"
          allowFullScreen={false}
          style={{ opacity: 0, transition: 'opacity 0.7s ease' }}
          onLoad={(e) => {
            const el = e.currentTarget
            el.style.opacity = '1'
          }}
        />
      )}
    </div>
  )
}

// @ts-ignore: нет типов для @egjs/react-grid
import Masonry from 'react-masonry-css'

export default function Home({ brands, categories, firstBannerImageUrl, firstBannerTitle }: HomePageProps) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const tileHeights = [280, 320, 360]
  const brandTileHeights = [280, 320, 360]

  // Функция для получения цветов баннера по бренду
  const getBrandColors = (brandName: string) => {
    const colorMap: { [key: string]: { bgColor: string; textColor: string } } = {
      'Zara': { bgColor: 'from-gray-900 to-gray-700', textColor: 'text-white' },
      'LC Waikiki': { bgColor: 'from-blue-600 to-blue-400', textColor: 'text-white' },
      'Koton': { bgColor: 'from-purple-600 to-purple-400', textColor: 'text-white' },
      'DeFacto': { bgColor: 'from-green-600 to-green-400', textColor: 'text-white' },
      'Mavi': { bgColor: 'from-indigo-600 to-indigo-400', textColor: 'text-white' },
      'Boyner': { bgColor: 'from-red-600 to-red-400', textColor: 'text-white' },
    }
    return colorMap[brandName] || { bgColor: 'from-gray-600 to-gray-400', textColor: 'text-white' }
  }

  const categoryColorMap: Record<string, { bgColor: string; textColor: string }> = {
    medicines: { bgColor: 'from-green-600 to-emerald-500', textColor: 'text-white' },
    supplements: { bgColor: 'from-amber-600 to-yellow-500', textColor: 'text-white' },
    clothing: { bgColor: 'from-rose-600 to-pink-500', textColor: 'text-white' },
    underwear: { bgColor: 'from-rose-500 to-red-500', textColor: 'text-white' },
    headwear: { bgColor: 'from-blue-500 to-cyan-500', textColor: 'text-white' },
    shoes: { bgColor: 'from-blue-600 to-indigo-500', textColor: 'text-white' },
    electronics: { bgColor: 'from-slate-700 to-gray-600', textColor: 'text-white' },
    furniture: { bgColor: 'from-amber-800 to-orange-700', textColor: 'text-white' },
    tableware: { bgColor: 'from-orange-600 to-red-500', textColor: 'text-white' },
    accessories: { bgColor: 'from-purple-600 to-pink-500', textColor: 'text-white' },
    jewelry: { bgColor: 'from-amber-500 to-yellow-400', textColor: 'text-white' },
    'medical-equipment': { bgColor: 'from-teal-600 to-cyan-500', textColor: 'text-white' },
  }

  const getCategoryColors = (slug: string) => {
    return categoryColorMap[slug] || { bgColor: 'from-gray-600 to-gray-400', textColor: 'text-white' }
  }

  const mapCategoryToRouteSlug = (slug?: string | null) => {
    const normalized = (slug || '').trim().toLowerCase().replace(/_/g, '-')
    return normalized || 'medicines'
  }

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

  const renderMedia = (mediaUrl?: string | null, alt?: string, fallbackSrc?: string) => {
    if (!mediaUrl && !fallbackSrc) return null

    const youtubeId = extractYouTubeId(mediaUrl || '')
    if (youtubeId) {
      const youtubeThumb = getYouTubeThumbnail(mediaUrl)
      return <LazyYouTube youtubeId={youtubeId} youtubeThumb={youtubeThumb} alt={alt} />
    }

    // Если YouTube не обнаружен — обычная обработка файла/изображения
    const src = mediaUrl ? resolveMediaUrl(mediaUrl) : fallbackSrc || ''
    if (!src) return null

    if (isVideoUrl(mediaUrl || src)) {
      return (
        <video
          className="pointer-events-none absolute inset-0 h-full w-full object-cover"
          autoPlay
          muted
          loop
          playsInline
          preload="none"
          onError={(e) => {
            if (fallbackSrc) {
              const wrapper = e.currentTarget.parentElement
              if (wrapper) {
                const img = document.createElement('img')
                img.src = fallbackSrc
                img.alt = alt || ''
                img.width = 400
                img.height = 300
                img.loading = 'lazy'
                img.className = 'pointer-events-none absolute inset-0 h-full w-full object-cover'
                wrapper.replaceChildren(img)
              }
            }
          }}
        >
          <source src={src} />
        </video>
      )
    }

    return (
      <Image
        src={src}
        alt={alt || ''}
        fill
        sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 400px"
        className="pointer-events-none object-cover"
        onError={(e) => {
          if (fallbackSrc) {
            e.currentTarget.srcset = ''
            e.currentTarget.src = fallbackSrc
          }
        }}
      />
    )
  }

  const preparedCategories = categories
    .filter((category) => category.parent === null || typeof category.parent === 'undefined')
    .map((category) => ({
      ...category,
      displaySlug: mapCategoryToRouteSlug(category.slug),
      __isTopLevel: true,
    }))
    .sort((a, b) => {
      // Сначала категории с товарами (по убыванию количества), затем по sort_order
      const countA = a.products_count ?? 0
      const countB = b.products_count ?? 0
      if (countB !== countA) return countB - countA
      return (a.sort_order ?? 0) - (b.sort_order ?? 0)
    })
    .slice(0, 14)

  const handleBrandClick = (brand: Brand) => {
    const slug = mapCategoryToRouteSlug(brand.primary_category_slug || brand.slug || '')
    router.push(`/categories/${slug}?brand_id=${brand.id}`)
  }

  const handleCategoryClick = (category: CategoryCard & { displaySlug?: string }) => {
    const slugForRoute = category.displaySlug || mapCategoryToRouteSlug(category.slug)
    router.push(`/categories/${slugForRoute}`)
  }

  const siteUrl = getSiteOrigin()
  const canonicalUrl = `${siteUrl}/`
  const pageTitle = 'Mudaroba — Главная'
  const pageDescription = 'Mudaroba: турецкие товары — лекарства, одежда, обувь, электроника, аксессуары и мебель с доставкой.'

  return (
    <>
      <Head>
        {/* Preload первого баннера для ускорения LCP — браузер начнёт скачивать до гидрации JS */}
        {firstBannerImageUrl && (
          <link
            rel="preload"
            as="image"
            href={firstBannerImageUrl}
            // @ts-ignore
            fetchpriority="high"
          />
        )}
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

      <main className="bg-page text-main min-h-screen transition-colors duration-200">
        <div className="mx-auto max-w-6xl px-3 sm:px-4 md:px-6 py-4 sm:py-8">
          {/* Главный баннер */}
          <div className="mb-12 relative">
            {/*
              Мобайл: статичный SSR-img виден ДО загрузки JS (устраняет render delay ~5 сек).
              На десктопе скрыт — там показывается полная карусель с анимацией.
              После гидрации JS карусель подменяет статику через CSS-hidden.
            */}
            {firstBannerImageUrl && (
              <div id="mobile-banner-static" className="block md:hidden w-full relative rounded-[18px] overflow-hidden" style={{ aspectRatio: '4/3', maxHeight: '420px' }}>
                <Image
                  src={firstBannerImageUrl}
                  alt={firstBannerTitle || 'Banner'}
                  priority
                  fill
                  sizes="(max-width: 768px) 100vw, 1200px"
                  className="object-cover"
                />
              </div>
            )}
            {/* Карусель: скрыта на мобайл до гидрации, на десктопе — всегда видна */}
            <BannerCarousel
              position="main"
              firstBannerImageUrl={firstBannerImageUrl}
            />
          </div>

          {/* Brands Section — горизонтальный скролл на мобильных, сетка на десктопе */}
          <section className="mb-12">
            <h2 className="hidden md:block text-2xl md:text-3xl font-bold text-main mb-8 text-center">
              {t('popular_brands', 'Популярные бренды')}
            </h2>
            {/* Мобильные: горизонтальный скролл */}
            <div
              className="flex overflow-x-auto snap-x snap-mandatory gap-2 pb-4 hide-scrollbar -mr-3 pr-3 sm:-mr-4 sm:pr-4 md:hidden"
              style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
            >
              {brands.slice(0, 10).map((brand) => {
                const mediaUrl = brand.card_media_url || brand.logo
                const placeholderUrl = getPlaceholderImageUrl({ type: 'brand', id: brand.id })
                return (
                  <div
                    key={brand.id}
                    onClick={() => handleBrandClick(brand)}
                    className="relative shrink-0 w-[96px] h-[120px] snap-start rounded-[20px] overflow-hidden cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow bg-gray-900 group"
                  >
                    {renderMedia(mediaUrl || placeholderUrl, brand.name, placeholderUrl)}
                    <div className="absolute inset-0 bg-black/40 hidden" />
                    <div className="absolute inset-0 hidden items-center justify-center p-2 z-10">
                      <div className="text-center text-white drop-shadow w-full">
                        {brand.logo ? (
                          <div className="flex justify-center items-center w-full px-1 relative h-[36px]">
                            <Image
                              src={resolveMediaUrl(brand.logo)}
                              alt={brand.name}
                              fill
                              sizes="(max-width: 640px) 96px, 120px"
                              className="pointer-events-none object-contain filter brightness-0 invert"
                              onError={(e) => {
                                e.currentTarget.parentElement!.style.display = 'none'
                              }}
                            />
                          </div>
                        ) : (
                          <h3 className="text-xs font-bold line-clamp-2 leading-tight px-0.5">
                            {getLocalizedBrandName(brand.slug, brand.name, t, brand.translations, router.locale)}
                          </h3>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}

              {/* Кнопка "Все бренды" в конце свайпа */}
              <div
                className="relative flex flex-col items-center justify-center shrink-0 w-[96px] h-[120px] snap-start rounded-[20px] cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow bg-[var(--surface-soft)] border border-[var(--border)]"
                onClick={() => router.push('/brands')}
              >
                <div className="w-10 h-10 rounded-full bg-[var(--accent)] text-white flex items-center justify-center mb-2 shadow-md">
                  <svg className="w-5 h-5 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
                  </svg>
                </div>
                <span className="text-[11px] font-bold text-center px-1 leading-tight uppercase text-main">
                  {t('all_brands', 'Все бренды')}
                </span>
              </div>
            </div>
            {/* Десктоп: сетка как у категорий */}
            <Masonry
              breakpointCols={{ default: 3, 1024: 3, 768: 3 }}
              className="hidden md:flex w-full gap-4 md:gap-6"
              columnClassName="flex flex-col gap-4 md:gap-6"
            >
              {brands.map((brand, idx) => {
                const mediaUrl = brand.card_media_url || brand.logo
                const placeholderUrl = getPlaceholderImageUrl({ type: 'brand', id: brand.id })
                const cardHeight = brandTileHeights[idx % brandTileHeights.length]
                return (
                  <div
                    key={brand.id}
                    onClick={() => handleBrandClick(brand)}
                    style={{ height: cardHeight }}
                    className="relative isolate rounded-xl overflow-hidden cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow-lg hover:shadow-xl bg-gray-900/10 group"
                  >
                    <div className="absolute inset-0 z-0 overflow-hidden">
                      {renderMedia(mediaUrl || placeholderUrl, brand.name, placeholderUrl)}
                    </div>
                    <div className="absolute inset-0 z-[1] bg-black/40 transition-opacity duration-300 opacity-0 md:group-hover:opacity-100" />
                    <div className="absolute inset-0 z-10 flex items-center justify-center p-4 md:p-6 transition-opacity duration-300 opacity-0 md:group-hover:opacity-100">
                      <div className="text-center text-white drop-shadow">
                        {brand.logo && (
                          <div className="mb-2 md:mb-3 flex justify-center">
                            <img
                              src={resolveMediaUrl(brand.logo)}
                              alt={brand.name}
                              className="pointer-events-none h-8 md:h-12 w-auto object-contain filter brightness-0 invert"
                              onError={(e) => {
                                e.currentTarget.style.display = 'none'
                              }}
                            />
                          </div>
                        )}
                        <h3 className="text-xl md:text-3xl font-bold mb-1 md:mb-2 line-clamp-1">
                          {getLocalizedBrandName(brand.slug, brand.name, t, brand.translations, router.locale)}
                        </h3>
                      </div>
                    </div>
                  </div>
                )
              })}
            </Masonry>
            <div className="mt-6 hidden md:flex justify-center">
              <Link
                href="/brands"
                className="inline-flex items-center rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white shadow hover:bg-[var(--accent-strong)] transition-colors"
              >
                {t('all_brands', 'Все бренды')}
              </Link>
            </div>
          </section>

          {/* Баннер после брендов */}
          <div className="mb-12">
            <BannerCarousel position="after_brands" />
          </div>

          {/* Categories Section */}
          <section className="mb-12">
            <h2 className="text-2xl md:text-3xl font-bold text-main mb-8 text-center">
              {t('categories_section_title', 'Категории товаров')}
            </h2>
            <Masonry
              breakpointCols={{ default: 3, 1024: 3, 768: 3, 640: 2, 0: 2 }}
              className="flex w-full gap-4 md:gap-6"
              columnClassName="flex flex-col gap-4 md:gap-6"
            >
              {preparedCategories.map((category, idx) => {
                const cardHeight = tileHeights[idx % tileHeights.length]
                const mediaUrl = category.card_media_url
                const placeholderUrl = getPlaceholderImageUrl({ type: 'category', id: category.id })
                return (
                  <div
                    key={category.id}
                    onClick={() => handleCategoryClick(category)}
                    style={{ height: cardHeight }}
                    className="relative isolate rounded-xl overflow-hidden cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow-lg hover:shadow-xl bg-gray-900/10"
                  >
                    <div className="absolute inset-0 z-0 overflow-hidden">
                      {renderMedia(
                        mediaUrl || placeholderUrl,
                        getLocalizedCategoryName(category.slug, category.name, t, category.translations, router.locale),
                        placeholderUrl
                      )}
                    </div>
                    <div className="absolute inset-0 z-[1] bg-black/35" />
                    <div className="absolute inset-0 z-10 flex items-center justify-center p-4">
                      <div className="text-center text-white drop-shadow">
                        <h3 className="text-xl font-bold mb-1">
                          {getLocalizedCategoryName(category.slug, category.name, t, category.translations, router.locale)}
                        </h3>
                        {getLocalizedCategoryDescription(category.slug, category.description, t, category.translations, router.locale) && (
                          <p className="hidden md:block text-sm opacity-90">
                            {getLocalizedCategoryDescription(category.slug, category.description, t, category.translations, router.locale)}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </Masonry>
            <div className="mt-6 flex justify-center">
              <Link
                href="/categories"
                className="inline-flex items-center rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white shadow hover:bg-[var(--accent-strong)] transition-colors"
              >
                {t('all_categories', 'Все категории')}
              </Link>
            </div>
          </section>

          {/* Баннер перед футером */}
          <div className="mb-12">
            <BannerCarousel position="before_footer" />
          </div>

          {/* Популярные товары */}
          <PopularProductsCarousel />

          {/* Вам может понравиться (RecSys) */}
          <PersonalizedRecommendations />

          {/* Баннер после популярных товаров */}
          <div className="mb-12">
            <BannerCarousel position="after_popular_products" />
          </div>

          {/* Отзывы клиентов */}
          <TestimonialsCarousel />
        </div>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (context) => {
  try {
    const { getInternalApiUrl } = await import('../lib/urls')
    const { fetchFooterSettings } = await import('../lib/footerSettings')

    let firstBannerImageUrl: string | null = null
    let firstBannerTitle: string | null = null
    try {
      const bannersRes = await axios.get(getInternalApiUrl('catalog/banners'), {
        params: { position: 'main' },
        timeout: 3000,
      })
      const bannersData: any[] = Array.isArray(bannersRes.data) ? bannersRes.data : []
      const firstBanner = bannersData.find((b) => b.media_files && b.media_files.length > 0)
      const firstMedia = firstBanner?.media_files[0]
      if (firstMedia && (firstMedia.content_type === 'image' || firstMedia.content_type === 'gif') && firstMedia.content_url) {
        firstBannerImageUrl = firstMedia.content_url
        firstBannerTitle = firstMedia.title || firstBanner?.title || null
      }
    } catch {
      // Не блокируем рендер страницы — preload необязателен
    }

    // Загружаем все бренды из API с пагинацией
    let allBrands: Brand[] = []
    let nextUrl: string | null = getInternalApiUrl('catalog/brands')

    // Собираем все бренды (обходим пагинацию)
    while (nextUrl) {
      try {
        const brandsRes = await axios.get(nextUrl)
        const data = brandsRes.data
        const pageBrands = Array.isArray(data) ? data : (data.results || [])
        allBrands = [...allBrands, ...pageBrands]

        // Проверяем наличие следующей страницы
        nextUrl = data.next || null
      } catch (err) {
        console.error('Error loading brands page:', err)
        break
      }
    }

    // Сортировка: сначала бренды с товарами (по убыванию products_count), затем по медиа, по имени
    const sortedBrands = [...allBrands].sort((a: Brand, b: Brand) => {
      const countA = a.products_count || 0
      const countB = b.products_count || 0
      if (countB !== countA) return countB - countA
      const hasMediaA = !!(a.card_media_url && a.card_media_url.trim())
      const hasMediaB = !!(b.card_media_url && b.card_media_url.trim())
      if (hasMediaB !== hasMediaA) return hasMediaB ? 1 : -1
      return (a.name || '').localeCompare(b.name || '', 'ru')
    })

    // Показываем 11 брендов (с приоритетом у тех, у кого есть товары)
    const brands = sortedBrands.slice(0, 11)

    console.log('Loaded popular brands for homepage:', brands.map((b: Brand) => `${b.name} (${b.products_count ?? 0} товаров, медиа: ${!!b.card_media_url})`))

    // Загружаем категории (top-level) с пагинацией
    let allCategories: CategoryCard[] = []
    let nextCategoryUrl: string | null = getInternalApiUrl('catalog/categories?top_level=true&page_size=200')

    while (nextCategoryUrl) {
      try {
        const categoriesRes = await axios.get(nextCategoryUrl)
        const data = categoriesRes.data
        const pageCategories = Array.isArray(data) ? data : (data.results || [])
        allCategories = [...allCategories, ...pageCategories]
        nextCategoryUrl = data.next || null
      } catch (err) {
        console.error('Error loading categories page:', err)
        break
      }
    }

    const categories = allCategories.filter((category) => {
      // Только корневые: parent и parent_id должны быть null/undefined
      const parentVal = (category as any).parent ?? (category as any).parent_id
      const isRoot = parentVal === null || parentVal === undefined
      if (!isRoot) return false
      if (category.gender) return false
      if (category.clothing_type) return false
      if (category.device_type) return false
      return true
    })
    categories.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
    const normalizeSlug = (value: any) =>
      (value || '')
        .toString()
        .trim()
        .toLowerCase()
        .replace(/_/g, '-')
    const uniqueMap = new Map<string, CategoryCard>()
    categories.forEach((category) => {
      const key = normalizeSlug(category.slug)
      const existing = uniqueMap.get(key)
      if (!existing) {
        uniqueMap.set(key, category)
        return
      }
      const existingCount = existing.products_count ?? 0
      const nextCount = category.products_count ?? 0
      if (nextCount > existingCount) {
        uniqueMap.set(key, category)
      }
    })
    const uniqueCategories = Array.from(uniqueMap.values()).sort((a, b) => {
      const countA = a.products_count ?? 0
      const countB = b.products_count ?? 0
      if (countB !== countA) return countB - countA
      return (a.sort_order ?? 0) - (b.sort_order ?? 0)
    })
    const footerSettings = await fetchFooterSettings()

    return {
      props: {
        brands,
        categories: uniqueCategories,
        firstBannerImageUrl,
        firstBannerTitle,
        footerSettings,
        ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
      },
    }
  } catch (error) {
    console.error('Error loading brands for homepage:', error)
    const { fetchFooterSettings } = await import('../lib/footerSettings')
    const footerSettings = await fetchFooterSettings()
    return {
      props: {
        brands: [],
        categories: [],
        firstBannerImageUrl: null,
        footerSettings,
        ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
      },
    }
  }
}
