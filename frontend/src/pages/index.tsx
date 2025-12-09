import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import { GetServerSideProps } from 'next'
import axios from 'axios'
import BannerCarousel from '../components/BannerCarouselMedia'
import PopularProductsCarousel from '../components/PopularProductsCarousel'
import TestimonialsCarousel from '../components/TestimonialsCarousel'

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
}

interface CategoryCard {
  id: number
  name: string
  slug: string
  description: string
  card_media_url?: string | null
  parent?: number | null
  sort_order?: number | null
}

interface HomePageProps {
  brands: Brand[]
  categories: CategoryCard[]
}

export default function Home({ brands, categories }: HomePageProps) {
  const { t } = useTranslation('common')
  const router = useRouter()

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

  const rootSlugSet = new Set([
    'medicines',
    'supplements',
    'medical_equipment',
    'medical-equipment',
    'clothing',
    'shoes',
    'electronics',
    'furniture',
    'tableware',
    'accessories',
    'jewelry',
    'underwear',
    'headwear',
  ])

  const mapCategoryToRouteSlug = (slug?: string | null) => {
    const normalized = (slug || '').trim().toLowerCase().replace(/_/g, '-')
    return normalized || 'medicines'
  }

  const resolveMediaUrl = (url?: string | null) => {
    if (!url) return ''

    // Абсолютный URL, но мог прийти с хостом backend:8000 — переписываем на публичный
    const clientApi = process.env.NEXT_PUBLIC_API_BASE
    const serverApi = process.env.INTERNAL_API_BASE

    const stripApiSuffix = (value?: string) => {
      if (!value) return ''
      return value.endsWith('/api') ? value.slice(0, -4) : value
    }

    const fallbackMediaBase =
      process.env.NEXT_PUBLIC_MEDIA_BASE ||
      'http://localhost:8000'

    const replaceBackendHost = (base: string) => {
      if (!base) return ''
      try {
        const u = new URL(base)
        if (u.hostname === 'backend') {
          if (typeof window !== 'undefined') {
            u.hostname = window.location.hostname
          } else {
            u.hostname = 'localhost'
            u.port = u.port || '8000'
          }
        }
        return u.toString().replace(/\/$/, '')
      } catch {
        return base
      }
    }

    const serverMediaBase = replaceBackendHost(stripApiSuffix(serverApi) || 'http://backend:8000')
    const clientMediaBase =
      typeof window === 'undefined'
        ? replaceBackendHost(stripApiSuffix(serverApi) || stripApiSuffix(clientApi) || fallbackMediaBase)
        : replaceBackendHost(stripApiSuffix(clientApi) || '') ||
          `${window.location.protocol}//${window.location.hostname}:8000`

    // Если абсолютный и указывает на backend/внутренний хост — заменяем на публичный
    if (/^https?:\/\//i.test(url)) {
      try {
        const u = new URL(url)
        if (serverMediaBase && url.startsWith(serverMediaBase)) {
          return url.replace(serverMediaBase, clientMediaBase || u.origin)
        }
        // если хост "backend" или "backend:8000", заменим на доступный
        if (u.hostname === 'backend') {
          const origin8000 =
            typeof window !== 'undefined'
              ? `${window.location.protocol}//${window.location.hostname}:8000`
              : fallbackMediaBase
          return `${origin8000}${u.pathname}${u.search}`
        }
        return url
      } catch {
        return url
      }
    }

    // Относительный путь
    if (clientMediaBase) {
      return url.startsWith('/') ? `${clientMediaBase}${url}` : `${clientMediaBase}/${url}`
    }

    if (typeof window !== 'undefined') {
      const origin = window.location.origin
      return url.startsWith('/') ? `${origin}${url}` : `${origin}/${url}`
    }
    return url
  }

  const renderMedia = (mediaUrl?: string | null, alt?: string) => {
    if (!mediaUrl) return null
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
      <img
        src={src}
        alt={alt || ''}
        className="absolute inset-0 h-full w-full object-cover"
      />
    )
  }

  const preparedCategories = categories
    .filter((category) => {
      const isTop = category.parent === null || typeof category.parent === 'undefined'
      if (!isTop) return false
      const raw = (category.slug || '').trim().toLowerCase().replace(/-/g, '_')
      return rootSlugSet.has(raw) || rootSlugSet.has(raw.replace(/_/g, '-'))
    })
    .map((category) => ({
      ...category,
      displaySlug: mapCategoryToRouteSlug(category.slug),
      __isTopLevel: true,
    }))
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))

  const handleBrandClick = (brand: Brand) => {
    const slug = mapCategoryToRouteSlug(brand.primary_category_slug || '')
    router.push(`/categories/${slug}?brand_id=${brand.id}`)
  }

  const handleCategoryClick = (category: CategoryCard & { displaySlug?: string }) => {
    const slugForRoute = category.displaySlug || mapCategoryToRouteSlug(category.slug)
    router.push(`/categories/${slugForRoute}`)
  }

  return (
    <>
      <Head>
        <title>PharmaTurk - Главная</title>
      </Head>
      
      <main>
      <div className="mx-auto max-w-6xl px-6 py-8">
          {/* Главный баннер */}
          <div className="mb-12">
            <BannerCarousel position="main" />
        </div>

        {/* Brands Section */}
        <section className="mb-12">
          <h2 className="text-2xl md:text-3xl font-bold text-gray-900 mb-8 text-center">
            Популярные бренды
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {brands.map((brand) => {
              return (
                <div
                  key={brand.id}
                  onClick={() => handleBrandClick(brand)}
                  className="relative h-48 rounded-xl overflow-hidden cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow-lg hover:shadow-xl bg-gray-900/10"
                >
                  {renderMedia(brand.card_media_url || brand.logo, brand.name)}
                  <div className="absolute inset-0 bg-black/35" />
                  <div className="absolute inset-0 flex items-center justify-center p-6 z-10">
                    <div className="text-center text-white drop-shadow">
                      {brand.logo && (
                        <div className="mb-3 flex justify-center">
                          <img 
                            src={brand.logo} 
                            alt={brand.name}
                            className="h-12 w-auto object-contain filter brightness-0 invert"
                            onError={(e) => {
                              e.currentTarget.style.display = 'none'
                            }}
                          />
                        </div>
                      )}
                      <h3 className="text-2xl md:text-3xl font-bold mb-2">
                        {brand.name}
                      </h3>
                      <p className="text-sm opacity-90 mb-2">
                        {brand.description}
                      </p>
                      {brand.products_count && (
                        <p className="text-xs opacity-75">
                          {brand.products_count} товаров
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>

          {/* Баннер после брендов */}
          <div className="mb-12">
            <BannerCarousel position="after_brands" />
          </div>

        {/* Categories Section */}
          <section className="mb-12">
          <h2 className="text-2xl md:text-3xl font-bold text-gray-900 mb-8 text-center">
            Категории товаров
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {preparedCategories.map((category) => {
              return (
              <div
                key={category.id}
                onClick={() => handleCategoryClick(category)}
                className="relative h-40 rounded-xl overflow-hidden cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow-lg hover:shadow-xl bg-gray-900/10"
              >
                  {renderMedia(category.card_media_url, category.name)}
                  <div className="absolute inset-0 bg-black/35" />
                  <div className="absolute inset-0 flex items-center justify-center p-4 z-10">
                    <div className="text-center text-white drop-shadow">
                    <h3 className="text-xl font-bold mb-1">
                      {category.name}
                    </h3>
                    <p className="text-sm opacity-90">
                      {category.description}
                    </p>
                  </div>
                </div>
              </div>
              )
            })}
          </div>
        </section>

          {/* Баннер перед футером */}
          <div className="mb-12">
            <BannerCarousel position="before_footer" />
          </div>

          {/* Популярные товары */}
          <PopularProductsCarousel />
          
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
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    
    // Загружаем все бренды из API с пагинацией
    let allBrands: Brand[] = []
    let nextUrl: string | null = `${base}/api/catalog/brands`
    
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
    
    // Фильтруем бренды с товарами и сортируем по количеству товаров (популярность)
    const brandsWithProducts = allBrands.filter((brand: Brand) => 
      brand.products_count && brand.products_count > 0
    )
    
    // Сортируем по количеству товаров (по убыванию) - самые популярные первыми
    brandsWithProducts.sort((a: Brand, b: Brand) => {
      const countA = a.products_count || 0
      const countB = b.products_count || 0
      return countB - countA
    })
    
    // Берем топ-6 самых популярных брендов
    const brands = brandsWithProducts.slice(0, 6)
    
    console.log('Loaded popular brands for homepage:', brands.map((b: Brand) => `${b.name} (${b.products_count} товаров)`))

    // Загружаем категории (top-level) с пагинацией
    let allCategories: CategoryCard[] = []
    let nextCategoryUrl: string | null = `${base}/api/catalog/categories?page_size=100`

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

    const categories = allCategories.filter((category) => category.parent === null || typeof category.parent === 'undefined')
    categories.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
    
    return {
      props: {
        brands,
        categories,
        ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
      },
    }
  } catch (error) {
    console.error('Error loading brands for homepage:', error)
    
    return {
      props: {
        brands: [],
        categories: [],
        ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
      },
    }
  }
}
