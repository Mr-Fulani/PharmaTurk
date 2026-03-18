import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { getPlaceholderImageUrl, resolveMediaUrl } from '../lib/media'
import { getSiteOrigin } from '../lib/urls'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import { GetServerSideProps } from 'next'
import axios from 'axios'
import BannerCarousel from '../components/BannerCarouselMedia'
import PopularProductsCarousel from '../components/PopularProductsCarousel'
import PersonalizedRecommendations from '../components/PersonalizedRecommendations'
import TestimonialsCarousel from '../components/TestimonialsCarousel'
import { getLocalizedCategoryName, getLocalizedCategoryDescription, getLocalizedBrandName, getLocalizedBrandDescription, BrandTranslation } from '../lib/i18n'

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
}

// @ts-ignore: нет типов для @egjs/react-grid
import Masonry from 'react-masonry-css'

export default function Home({ brands, categories }: HomePageProps) {
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
              }, 3100) // прячем стартовые оверлеи YouTube
            }}
            allowFullScreen={false}
          />
        </div>
      )
    }

    // Если YouTube не обнаружен — обычная обработка файла/изображения
    const src = mediaUrl ? resolveMediaUrl(mediaUrl) : fallbackSrc || ''
    if (!src) return null

    // Определяем видео: по расширению в mediaUrl или в path= (proxy-media)
    const pathFromQuery = (() => {
      try {
        const u = src.includes('?') ? new URL(src, 'http://_') : null
        return u?.searchParams.get('path') || ''
      } catch {
        return ''
      }
    })()
    const pathToCheck = pathFromQuery || mediaUrl || src
    const isVideo = /\.(mp4|mov|webm|m4v)(\?|$)/i.test(pathToCheck)

    if (isVideo) {
      return (
        <video
          className="absolute inset-0 h-full w-full object-cover"
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
          onError={(e) => {
            if (fallbackSrc) {
              const wrapper = e.currentTarget.parentElement
              if (wrapper) {
                const img = document.createElement('img')
                img.src = fallbackSrc
                img.alt = alt || ''
                img.className = 'absolute inset-0 h-full w-full object-cover'
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
      <img
        src={src}
        alt={alt || ''}
        className="absolute inset-0 h-full w-full object-cover"
        onError={(e) => {
          if (fallbackSrc && e.currentTarget.src !== fallbackSrc) {
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
  const pageTitle = 'PharmaTurk — Главная'
  const pageDescription = 'PharmaTurk: турецкие товары — лекарства, одежда, обувь, электроника, аксессуары и мебель с доставкой.'

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
      
      <main className="bg-page text-main min-h-screen transition-colors duration-200">
      <div className="mx-auto max-w-6xl px-6 py-8">
          {/* Главный баннер */}
          <div className="mb-12">
            <BannerCarousel position="main" />
        </div>

        {/* Brands Section — горизонтальный скролл на мобильных, сетка на десктопе */}
        <section className="mb-12">
          <h2 className="text-2xl md:text-3xl font-bold text-main mb-8 text-center">
            {t('popular_brands', 'Популярные бренды')}
          </h2>
          {/* Мобильные: горизонтальный скролл */}
          <div
            className="flex overflow-x-auto snap-x snap-mandatory gap-4 pb-4 hide-scrollbar -mx-6 px-6 md:hidden"
            style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
          >
            {brands.map((brand) => {
              const mediaUrl = brand.card_media_url || brand.logo
              const placeholderUrl = getPlaceholderImageUrl({ type: 'brand', id: brand.id })
              return (
                <div
                  key={brand.id}
                  onClick={() => handleBrandClick(brand)}
                  className="relative shrink-0 w-44 h-44 sm:w-52 sm:h-52 snap-start rounded-xl overflow-hidden cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow-lg hover:shadow-xl bg-gray-900/10"
                >
                  {renderMedia(mediaUrl || placeholderUrl, brand.name, placeholderUrl)}
                  <div className="absolute inset-0 bg-black/35" />
                  <div className="absolute inset-0 flex items-center justify-center p-4 z-10">
                    <div className="text-center text-white drop-shadow">
                      {brand.logo && (
                        <div className="mb-2 flex justify-center">
                          <img 
                            src={resolveMediaUrl(brand.logo)} 
                            alt={brand.name}
                            className="h-8 w-auto object-contain filter brightness-0 invert"
                            onError={(e) => {
                              e.currentTarget.style.display = 'none'
                            }}
                          />
                        </div>
                      )}
                      <h3 className="text-lg font-bold mb-1 line-clamp-1">
                        {getLocalizedBrandName(brand.slug, brand.name, t, brand.translations, router.locale)}
                      </h3>
                    </div>
                  </div>
                </div>
              )
            })}
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
                  className="relative rounded-xl overflow-hidden cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow-lg hover:shadow-xl bg-gray-900/10"
                >
                  {renderMedia(mediaUrl || placeholderUrl, brand.name, placeholderUrl)}
                  <div className="absolute inset-0 bg-black/35" />
                  <div className="absolute inset-0 flex items-center justify-center p-4 md:p-6 z-10">
                    <div className="text-center text-white drop-shadow">
                      {brand.logo && (
                        <div className="mb-2 md:mb-3 flex justify-center">
                          <img 
                            src={resolveMediaUrl(brand.logo)} 
                            alt={brand.name}
                            className="h-8 md:h-12 w-auto object-contain filter brightness-0 invert"
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
          <div className="mt-6 flex justify-center">
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
                className="relative rounded-xl overflow-hidden cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow-lg hover:shadow-xl bg-gray-900/10"
              >
                  {renderMedia(
                    mediaUrl || placeholderUrl,
                    getLocalizedCategoryName(category.slug, category.name, t, category.translations, router.locale),
                    placeholderUrl
                  )}
                  <div className="absolute inset-0 bg-black/35" />
                  <div className="absolute inset-0 flex items-center justify-center p-4 z-10">
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
      return (a.name || '').localeCompare(b.name || '')
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
        footerSettings,
        ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
      },
    }
  }
}
