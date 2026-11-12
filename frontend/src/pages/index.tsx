import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import dynamic from 'next/dynamic'
import { Fragment, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  getPlaceholderImageUrl,
  resolveMediaUrl,
  isVideoUrl,
  extractYouTubeId,
  getYouTubeCardThumbnailUrl,
  withListingImageMaxWidth,
} from '../lib/media'
import FallbackMediaImage from '../components/FallbackMediaImage'
import DeferredSection from '../components/DeferredSection'
import { getSiteOrigin } from '../lib/urls'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import { GetServerSideProps } from 'next'
import axios from 'axios'
import BannerCarousel from '../components/BannerCarouselMedia'
import { getLocalizedCategoryName, getLocalizedBrandName, getLocalizedBrandDescription, BrandTranslation } from '../lib/i18n'
import { safeJsonLd } from '../lib/sanitizeHtml'
import { getSingleFlight } from '../lib/api'
import { selectHomepageBrands } from '../lib/homepageBrands'
import { countBrandsWithProducts, countCatalogProducts, formatCount, roundDownToHundreds, roundDownToThousands } from '../lib/homeFacts'
import { defaultOgImageAlt, defaultOgImagePath } from '../lib/ogImage'
import { fallbackAppearance } from '../lib/siteAppearance'
import type { HomeBlockKey } from '../lib/siteAppearance'
import HomeFactsBlock from '../components/HomeFactsBlock'
import HomeBenefits from '../components/HomeBenefits'
import HomeCategoryWorlds, { type CategoryTile } from '../components/HomeCategoryWorlds'

// «Аптека» на главной: лекарства и БАДы; остальные разделы — «Гардероб и дом»
const PHARMACY_SLUGS = ['medicines', 'supplements']
// Ширина карточки бренда на главной: четыре в ряд, от 1024 px — шесть (промежуток 1rem).
const BRAND_TILE_BASIS = 'basis-[calc((100%_-_3rem)/4)] lg:basis-[calc((100%_-_5rem)/6)]'

// Dynamic imports для компонентов ниже fold — уменьшают initial JS bundle, добавляем fallback (Skeleton) для предотвращения CLS
const PopularProductsCarousel = dynamic(() => import('../components/PopularProductsCarousel'), { 
  ssr: false,
  loading: () => <div className="w-full min-h-[400px] animate-pulse bg-gray-100 dark:bg-gray-800 rounded-2xl mb-12" />
})
const PersonalizedRecommendations = dynamic(() => import('../components/PersonalizedRecommendations'), { 
  ssr: false,
  loading: () => <div className="w-full min-h-[400px] animate-pulse bg-gray-100 dark:bg-gray-800 rounded-2xl mb-12" />
})
const SourcingRequestForm = dynamic(() => import('../components/SourcingRequestForm'), { ssr: false })
const TestimonialsCarousel = dynamic(() => import('../components/TestimonialsCarousel'), {
  ssr: false,
  loading: () => <div className="w-full min-h-[400px] animate-pulse bg-gray-100 dark:bg-gray-800 rounded-2xl mb-12" />
})
const LazyYouTubeCard = dynamic(() => import('../components/LazyYouTubeCard'), { ssr: false })
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
  show_on_homepage?: boolean
  homepage_priority?: number | null
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
  mainBanners: any[]
  afterBrandsBanners: any[]
  beforeFooterBanners: any[]
  afterPopularBanners: any[]
  footerSettings: any
  /** Блоки главной, которые нужно показать, в порядке показа (настройка админки) */
  homeBlocks?: HomeBlockKey[]
  /** Брендов с товарами — для блока «Как работает Mudaroba» */
  brandsCount?: number
}

export default function Home({ brands: initialBrands, categories, mainBanners, afterBrandsBanners, beforeFooterBanners, afterPopularBanners, footerSettings, homeBlocks = fallbackAppearance().homeBlocks, brandsCount = 0 }: HomePageProps) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const [brands, setBrands] = useState<Brand[]>(initialBrands)

  useEffect(() => {
    if (initialBrands.length > 0) {
      setBrands(initialBrands)
      return
    }

    // После таймаута SSR восстанавливаем карточки, не задерживая всю страницу.
    let active = true
    getSingleFlight('catalog/brands', {
      params: { page_size: 1000 },
      headers: { 'Accept-Language': router.locale ?? 'ru' },
      timeout: 20000,
    }).then(({ data }) => {
      if (active) setBrands(selectHomepageBrands(data))
    }).catch((error) => {
      console.error('Error recovering homepage brands:', error)
    })
    return () => { active = false }
  }, [initialBrands, router.locale])

  const mobileBrandsRef = useRef<HTMLDivElement | null>(null)

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

  const renderMedia = (mediaUrl?: string | null, alt?: string, fallbackSrc?: string, sizes?: string) => {
    if (!mediaUrl && !fallbackSrc) return null

    const youtubeId = extractYouTubeId(mediaUrl || '')
    if (youtubeId) {
      const youtubeThumb = getYouTubeCardThumbnailUrl(mediaUrl)
      return <LazyYouTubeCard youtubeId={youtubeId} youtubeThumb={youtubeThumb} alt={alt} />
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

    return <FallbackMediaImage src={src} fallbackSrc={fallbackSrc || ''} alt={alt || ''} sizes={sizes} responsiveProxy />
  }

  const rootCategories = categories
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
  // Плитки — разделы с товарами (как раньше, до 14); остальные идут строкой ссылок.
  const categoryName = (category: CategoryCard) =>
    getLocalizedCategoryName(category.slug, category.name, t, category.translations, router.locale)
  const GOODS_TILE_SIZES = '(max-width: 639px) calc((100vw - 72px) / 2), (max-width: 1023px) calc((100vw - 120px) / 3), 230px'
  const PHARMACY_TILE_SIZES = '(max-width: 1023px) calc((100vw - 72px) / 2), 420px'
  const toCategoryTile = (category: typeof rootCategories[number], sizes: string): CategoryTile => {
    const placeholderUrl = getPlaceholderImageUrl({ type: 'category', id: category.id })
    return {
      id: category.id,
      href: `/categories/${category.displaySlug}`,
      name: categoryName(category),
      count: formatCount(category.products_count ?? 0, router.locale),
      media: renderMedia(
        withListingImageMaxWidth(category.card_media_url || '', 600) || placeholderUrl,
        categoryName(category),
        placeholderUrl,
        sizes
      ),
    }
  }
  const tileCategories = rootCategories.slice(0, 14)
  const isPharmacy = (category: CategoryCard) => PHARMACY_SLUGS.includes(mapCategoryToRouteSlug(category.slug))
  const pharmacyTiles = tileCategories.filter(isPharmacy).map((category) => toCategoryTile(category, PHARMACY_TILE_SIZES))
  const goodsTiles = tileCategories.filter((category) => !isPharmacy(category)).map((category) => toCategoryTile(category, GOODS_TILE_SIZES))
  const otherCategoryLinks = rootCategories.slice(14).map((category) => ({
    href: `/categories/${category.displaySlug}`,
    name: categoryName(category),
  }))

  const siteUrl = getSiteOrigin()
  const localePrefix = router.locale === router.defaultLocale ? '' : `/${router.locale}`
  const canonicalUrl = `${siteUrl}${localePrefix || '/'}`
  const ruUrl = `${siteUrl}/`
  // Главная EN живёт на /en (без слэша): /en/ отвечает 308 и не годится для hreflang
  const enUrl = `${siteUrl}/en`
  const pageTitle = t('home_meta_title', 'Товары из Турции с доставкой: лекарства, БАДы, одежда, обувь | Mudaroba')
  // Числа — из тех же ответов API, что и блок «Как работает Mudaroba»; нет чисел — описание без них
  const factsProductsCount = roundDownToThousands(countCatalogProducts(categories))
  const metaBrandsCount = roundDownToHundreds(brandsCount)
  const pageDescription = factsProductsCount > 0 && metaBrandsCount > 0
    ? t(
        'home_meta_description',
        '{{products}}+ позиций и {{brands}}+ брендов из Турции: лекарства, БАДы, косметика, одежда, обувь, мебель. Доставка в Россию, СНГ и по миру. Заявка без регистрации, связь в Telegram и WhatsApp.',
        { products: formatCount(factsProductsCount, router.locale), brands: formatCount(metaBrandsCount, router.locale) }
      )
    : t(
        'home_meta_description_short',
        'Лекарства, БАДы, косметика, одежда, обувь и мебель из Турции. Доставка в Россию, СНГ и по миру. Заявка без регистрации: менеджер проверит наличие и цену, связь в Telegram и WhatsApp.'
      )
  const ogImageUrl = `${siteUrl}${defaultOgImagePath(router.locale)}`
  const ogImageAlt = defaultOgImageAlt(router.locale)

  const sameAs = [
    footerSettings?.telegram_url,
    footerSettings?.instagram_url,
    footerSettings?.vk_url,
    footerSettings?.whatsapp_url,
  ]
    .filter(Boolean)
    // В настройках футера WhatsApp записан как http://wa.me/… — в разметке только https
    .map((url) => (url as string).replace(/^http:\/\//i, 'https://'))

  const organizationSchema = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: 'Mudaroba',
    url: siteUrl,
    // TODO(owner): черновик описания — на согласование владельцу
    description: t(
      'home_org_description',
      'Mudaroba — интернет-магазин товаров из Турции: одежда, обувь, мебель, косметика и БАДы турецких брендов, а также подбор лекарств по заявке. Заказ оформляется через менеджера, способ оплаты согласуется с менеджером. Доставка по всему миру, в первую очередь в Россию и страны СНГ.'
    ),
    // Google просит растровый логотип от 112×112; SVG остаётся в интерфейсе
    logo: `${siteUrl}/logo-512.png`,
    // Картинка-превью сайта — та же, что og:image
    image: ogImageUrl,
    // Контакты — только те, что уже есть на сайте (футер); адрес не указываем (решение владельца 09.11.2026)
    ...(footerSettings?.email && { email: footerSettings.email }),
    contactPoint: {
      '@type': 'ContactPoint',
      telephone: footerSettings?.phone || '+90-552-582-14-97',
      contactType: 'customer service',
      availableLanguage: ['Russian', 'English'],
    },
    ...(sameAs.length > 0 && { sameAs }),
  }

  const webSiteSchema = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: 'Mudaroba',
    url: siteUrl,
    potentialAction: {
      '@type': 'SearchAction',
      target: `${siteUrl}/search?q={search_term_string}`,
      'query-input': 'required name=search_term_string',
    },
  }

  useEffect(() => {
    const container = mobileBrandsRef.current
    if (!container || brands.length <= 1) return

    let isUserInteracting = false
    let interactionTimeout: ReturnType<typeof setTimeout> | null = null

    const markInteraction = () => {
      isUserInteracting = true
      if (interactionTimeout) clearTimeout(interactionTimeout)
      interactionTimeout = setTimeout(() => {
        isUserInteracting = false
      }, 2500)
    }

    const getStep = () => {
      const firstCard = container.children[0] as HTMLElement | undefined
      if (!firstCard) return 108
      const gap = 8
      return firstCard.offsetWidth + gap
    }

    const intervalId = window.setInterval(() => {
      if (window.innerWidth >= 768 || isUserInteracting) return

      const maxScrollLeft = container.scrollWidth - container.clientWidth
      if (maxScrollLeft <= 0) return

      const nextScrollLeft = container.scrollLeft + getStep()
      const target = nextScrollLeft >= maxScrollLeft - 4 ? 0 : nextScrollLeft
      container.scrollTo({ left: target, behavior: 'smooth' })
    }, 7000)

    container.addEventListener('touchstart', markInteraction, { passive: true })
    container.addEventListener('pointerdown', markInteraction)
    container.addEventListener('scroll', markInteraction, { passive: true })

    return () => {
      window.clearInterval(intervalId)
      if (interactionTimeout) clearTimeout(interactionTimeout)
      container.removeEventListener('touchstart', markInteraction)
      container.removeEventListener('pointerdown', markInteraction)
      container.removeEventListener('scroll', markInteraction)
    }
  }, [brands.length])

  // Блоки главной по ключам из админки («Главная — Блоки»): показ и порядок задаёт homeBlocks.
  const homeBlockNodes: Record<HomeBlockKey, ReactNode> = {
    // Главный баннер
    main_banner: (
      <div className="mb-12 relative">
        <BannerCarousel
          position="main"
          initialBanners={mainBanners}
        />
      </div>
    ),
    // Строка преимуществ под главным баннером
    // Ссылка на форму «Найдём товар» ниже на странице; блок выключен в админке — на ту же форму на странице «Как заказать».
    benefits: <HomeBenefits sourcingHref={homeBlocks.includes('sourcing') ? '/#sourcing-block' : '/how-to-order-medicines#sourcing'} />,
    // Brands Section — горизонтальный скролл на мобильных, сетка на десктопе
    brands: (
      <section className="mb-12">
        <h2 className="hidden md:block text-2xl md:text-3xl font-bold text-main mb-8 text-center">
          {t('popular_brands', 'Популярные бренды')}
        </h2>
        {/* Мобильные: горизонтальный скролл */}
        <div
          ref={mobileBrandsRef}
          className="flex overflow-x-auto snap-x snap-mandatory gap-2 pb-4 hide-scrollbar -mr-3 pr-3 sm:-mr-4 sm:pr-4 md:hidden"
          style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
        >
          {brands.slice(0, 10).map((brand) => {
            const mediaUrl = brand.card_media_url || brand.logo
            const placeholderUrl = getPlaceholderImageUrl({ type: 'brand', id: brand.id })
            return (
              <Link
                key={brand.id}
                href={`/brand/${brand.slug}`}
                className="relative shrink-0 w-[96px] h-[120px] snap-start rounded-[20px] overflow-hidden cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow bg-gray-900 group"
              >
                {renderMedia(withListingImageMaxWidth(mediaUrl || '', 300) || placeholderUrl, brand.name, placeholderUrl, '96px')}
                <div className="absolute inset-0 bg-black/40 hidden" />
                <div className="absolute inset-0 hidden items-center justify-center p-2 z-10">
                  <div className="text-center text-white drop-shadow w-full">
                    {brand.logo ? (
                      <div className="flex justify-center items-center w-full px-1">
                        <img
                          src={resolveMediaUrl(brand.logo)}
                          alt={brand.name}
                          className="pointer-events-none max-h-[36px] w-full object-contain filter brightness-0 invert"
                          onError={(e) => {
                            e.currentTarget.style.display = 'none'
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
              </Link>
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
        {/* Десктоп: ровный ряд одинаковых карточек; выбор и порядок брендов — из админки.
            Ряд на flex, а не на grid: последняя карточка «Все бренды» растягивается на остаток
            строки, поэтому при любом числе брендов и колонок в ряду нет пустой ячейки. */}
        <div className="hidden w-full flex-wrap gap-4 md:flex">
          {brands.map((brand) => {
            const mediaUrl = brand.card_media_url || brand.logo
            const placeholderUrl = getPlaceholderImageUrl({ type: 'brand', id: brand.id })
            return (
              <Link
                key={brand.id}
                href={`/brand/${brand.slug}`}
                className={`${BRAND_TILE_BASIS} relative isolate aspect-[4/3] shrink-0 grow-0 rounded-xl overflow-hidden cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow-lg hover:shadow-xl bg-gray-900/10 group`}
              >
                <div className="absolute inset-0 z-0 overflow-hidden">
                  {renderMedia(withListingImageMaxWidth(mediaUrl || '', 450) || placeholderUrl, brand.name, placeholderUrl, '(max-width: 1023px) calc((100vw - 96px) / 4), 180px')}
                </div>
                <div className="absolute inset-0 z-[1] bg-black/40 transition-opacity duration-300 opacity-0 md:group-hover:opacity-100" />
                <div className="absolute inset-0 z-10 flex items-center justify-center p-3 transition-opacity duration-300 opacity-0 md:group-hover:opacity-100">
                  <div className="text-center text-white drop-shadow">
                    {brand.logo && (
                      <div className="mb-1.5 flex justify-center">
                        <img
                          src={resolveMediaUrl(brand.logo)}
                          alt={brand.name}
                          className="pointer-events-none h-7 w-auto object-contain filter brightness-0 invert"
                          onError={(e) => {
                            e.currentTarget.style.display = 'none'
                          }}
                        />
                      </div>
                    )}
                    <h3 className="text-base font-bold line-clamp-1">
                      {getLocalizedBrandName(brand.slug, brand.name, t, brand.translations, router.locale)}
                    </h3>
                  </div>
                </div>
              </Link>
            )
          })}
          <Link
            href="/brands"
            className={`${BRAND_TILE_BASIS} group flex min-h-[72px] grow items-center justify-center gap-2 rounded-xl bg-[var(--accent-soft)] px-4 text-base font-semibold text-[var(--accent)] transition-colors duration-200 hover:bg-[var(--accent)] hover:text-white`}
          >
            {t('all_brands', 'Все бренды')}
            <svg aria-hidden="true" className="h-5 w-5 transition-transform duration-200 group-hover:translate-x-0.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14m-6-6 6 6-6 6" />
            </svg>
          </Link>
        </div>
      </section>
    ),
    // Баннер после брендов — SSR-данные исключают клиентский fetch и CLS
    banner_after_brands: (
      <div className="mb-12">
        <BannerCarousel position="after_brands" initialBanners={afterBrandsBanners} />
      </div>
    ),
    // Разделы: «Аптека» и «Гардероб и дом» — плитки одного размера с карточками из админки
    categories: <HomeCategoryWorlds pharmacy={pharmacyTiles} goods={goodsTiles} others={otherCategoryLinks} />,
    // Баннер перед футером — SSR-данные исключают клиентский fetch и CLS
    banner_before_footer: (
      <div className="mb-12">
        <BannerCarousel position="before_footer" initialBanners={beforeFooterBanners} />
      </div>
    ),
    // Популярные товары
    bestsellers: (
      <DeferredSection><PopularProductsCarousel /></DeferredSection>
    ),
    // «Найдём любой товар из Турции по ссылке или фото» — после хитов, выше последнего баннера
    // Якорь на обёртке: сама форма (её #sourcing) появляется в HTML только рядом с экраном.
    sourcing: (
      <div id="sourcing-block" className="scroll-mt-24">
        <DeferredSection>
          <div className="mb-12">
            <SourcingRequestForm placement="home" />
          </div>
        </DeferredSection>
      </div>
    ),
    // Вам может понравиться (RecSys)
    recommendations: (
      <DeferredSection><PersonalizedRecommendations /></DeferredSection>
    ),
    // Баннер после популярных товаров — SSR-данные исключают клиентский fetch и CLS
    banner_after_popular: (
      <div className="mb-12">
        <BannerCarousel position="after_popular_products" initialBanners={afterPopularBanners} />
      </div>
    ),
    testimonials: <DeferredSection><TestimonialsCarousel /></DeferredSection>,
    // «Как работает Mudaroba» — серверный текст для поисковиков и ИИ-ассистентов, перед футером
    facts: (
      <HomeFactsBlock
        productsCount={factsProductsCount}
        brandsCount={brandsCount}
      />
    ),
  }

  return (
    <>
      <Head>
        <title>{pageTitle}</title>
        <meta name="description" content={pageDescription} />
        <link rel="canonical" href={canonicalUrl} />
        <link rel="alternate" hrefLang="ru" href={ruUrl} />
        <link rel="alternate" hrefLang="en" href={enUrl} />
        <link rel="alternate" hrefLang="x-default" href={ruUrl} />
        <meta property="og:title" content={pageTitle} />
        <meta property="og:description" content={pageDescription} />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:type" content="website" />
        <meta property="og:locale" content={router.locale === 'en' ? 'en_US' : 'ru_RU'} />
        <meta property="og:image" content={ogImageUrl} />
        <meta property="og:image:type" content="image/jpeg" />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        <meta property="og:image:alt" content={ogImageAlt} />
        <meta name="twitter:title" content={pageTitle} />
        <meta name="twitter:description" content={pageDescription} />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:image" content={ogImageUrl} />
        <meta name="twitter:image:alt" content={ogImageAlt} />
        <script
          type="application/ld+json"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: safeJsonLd(organizationSchema) }}
        />
        <script
          type="application/ld+json"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: safeJsonLd(webSiteSchema) }}
        />
      </Head>

      <main className="bg-page text-main min-h-screen transition-colors duration-200">
        <h1 className="sr-only">{t('home_h1', 'Товары из Турции с доставкой — Mudaroba')}</h1>
        <div className="mx-auto max-w-6xl px-3 sm:px-4 md:px-6 py-4 sm:py-8">
          {homeBlocks.map((key) => (
            <Fragment key={key}>{homeBlockNodes[key]}</Fragment>
          ))}
        </div>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (context) => {
  // Кэшируем HTML-ответ главной страницы в Vercel/Cloudflare CDN на 60с
  if (context.res) {
    context.res.setHeader('Cache-Control', 'public, s-maxage=60, stale-while-revalidate=300')
  }

  try {
    const { getInternalApiUrl } = await import('../lib/urls')
    const { fetchFooterSettings } = await import('../lib/footerSettings')
    const { fetchSiteAppearance } = await import('../lib/siteAppearanceServer')

    // Запускаем бренды вместе с остальными данными страницы. API может отвечать
    // дольше 5 секунд: не отдаём заведомо пустой блок при нормальном медленном ответе.
    const brandsPromise = axios.get(getInternalApiUrl('catalog/brands?page_size=1000'), {
      timeout: 15000,
    }).then(({ data }) => ({ brands: selectHomepageBrands(data), brandsCount: countBrandsWithProducts(data) })).catch((error) => {
      context.res?.setHeader('Cache-Control', 'private, no-store')
      console.error('Error loading brands:', error)
      return { brands: [] as Brand[], brandsCount: 0 }
    })

    let firstBannerImageUrl: string | null = null
    let firstBannerTitle: string | null = null
    let mainBanners: any[] = []
    let afterBrandsBanners: any[] = []
    let beforeFooterBanners: any[] = []
    let afterPopularBanners: any[] = []

    // Загружаем все позиции баннеров параллельно — устраняет 6,530мс задержку LCP
    try {
      // Передаём язык в заголовках, чтобы бэкенд вернул переводы на нужном языке
      const locale = context.locale ?? 'ru'
      const langHeaders = { 'Accept-Language': locale, 'X-Language': locale }
      const [mainRes, afterBrandsRes, beforeFooterRes, afterPopularRes] = await Promise.all([
        axios.get(getInternalApiUrl('catalog/banners'), { params: { position: 'main' }, headers: langHeaders, timeout: 3000 }),
        axios.get(getInternalApiUrl('catalog/banners'), { params: { position: 'after_brands' }, headers: langHeaders, timeout: 3000 }),
        axios.get(getInternalApiUrl('catalog/banners'), { params: { position: 'before_footer' }, headers: langHeaders, timeout: 3000 }),
        axios.get(getInternalApiUrl('catalog/banners'), { params: { position: 'after_popular_products' }, headers: langHeaders, timeout: 3000 }),
      ])
      mainBanners = Array.isArray(mainRes.data) ? mainRes.data : []
      afterBrandsBanners = Array.isArray(afterBrandsRes.data) ? afterBrandsRes.data : []
      beforeFooterBanners = Array.isArray(beforeFooterRes.data) ? beforeFooterRes.data : []
      afterPopularBanners = Array.isArray(afterPopularRes.data) ? afterPopularRes.data : []
      const firstBanner = mainBanners.find((b) => b.media_files && b.media_files.length > 0)
      const firstMedia = firstBanner?.media_files[0]
      if (firstMedia && (firstMedia.content_type === 'image' || firstMedia.content_type === 'gif') && firstMedia.content_url) {
        firstBannerImageUrl = firstMedia.content_url
        firstBannerTitle = firstMedia.title || firstBanner?.title || null
      }
    } catch {
      // Не блокируем рендер — баннеры необязательны
    }

    // Показ и порядок блоков, включая отзывы, — настройка админки «Главная — Блоки».
    const { homeBlocks } = await fetchSiteAppearance()

    const { brands, brandsCount } = await brandsPromise

    console.log('Loaded popular brands for homepage:', brands.map((b: Brand) => `${b.name} (${b.products_count ?? 0} товаров, медиа: ${!!b.card_media_url})`))

    // Категории (top-level) одним запросом
    let allCategories: CategoryCard[] = []
    try {
      const categoriesRes = await axios.get(getInternalApiUrl('catalog/categories?top_level=true&page_size=1000'), { timeout: 5000 })
      const data = categoriesRes.data
      allCategories = Array.isArray(data) ? data : (data.results || [])
    } catch (err) {
      console.error('Error loading categories:', err)
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
        brandsCount,
        categories: uniqueCategories,
        firstBannerImageUrl,
        firstBannerTitle,
        mainBanners,
        afterBrandsBanners,
        beforeFooterBanners,
        afterPopularBanners,
        footerSettings,
        homeBlocks,
        ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
      },
    }
  } catch (error) {
    context.res?.setHeader('Cache-Control', 'private, no-store')
    console.error('Error loading brands for homepage:', error)
    const { fetchFooterSettings } = await import('../lib/footerSettings')
    const footerSettings = await fetchFooterSettings()
    return {
      props: {
        brands: [],
        categories: [],
        firstBannerImageUrl: null,
        mainBanners: [],
        afterBrandsBanners: [],
        beforeFooterBanners: [],
        afterPopularBanners: [],
        footerSettings,
        ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
      },
    }
  }
}
