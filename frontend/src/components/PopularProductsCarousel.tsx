import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import dynamic from 'next/dynamic'
import { useTranslation } from 'next-i18next'
import { ChatBubbleOvalLeftIcon, StarIcon } from '@heroicons/react/20/solid'
import { getSingleFlight } from '../lib/api'
import AddToCartButton from './AddToCartButton'
import FavoriteButton from './FavoriteButton'
import ShareButton from './ShareButton'
import {
  getPlaceholderImageUrl,
  resolveMediaUrl,
  isVideoUrl,
  getVideoEmbedUrl,
  extractYouTubeId,
  getYouTubeCardThumbnailUrl,
} from '../lib/media'
import { buildProductUrl } from '../lib/urls'
import { buildProductIdentityKey, favoriteApiProductId } from '../lib/product'
import { getLocalizedProductName, ProductTranslation } from '../lib/i18n'
import { formatPrice, getCurrencySymbol, parseMoneyNumber as parseNumber, parsePriceWithCurrency } from '../lib/price'
import ProductCardImageGallery, { normalizeProductCardImages, ProductCardGalleryImage } from './ProductCardImageGallery'
import { deduplicateFeaturedProducts } from '../lib/featuredProducts'
import InViewAutoplayVideo from './InViewAutoplayVideo'

const LazyYouTubeCard = dynamic(() => import('./LazyYouTubeCard'), { ssr: false })

interface Product {
  id: number
  base_product_id?: number | null
  name: string
  slug: string
  price: string | number | null
  currency?: string | null
  oldPrice?: string | number | null
  old_price?: string | number | null
  old_price_formatted?: string | null
  active_variant_price?: string | number | null
  active_variant_currency?: string | null
  active_variant_old_price_formatted?: string | null
  badge?: string | null
  rating?: number | null
  reviews_count?: number | null
  main_image_url?: string | null
  images?: ProductCardGalleryImage[] | null
  video_url?: string | null
  has_manual_main_image?: boolean
  brand?: {
    id: number
    name: string
    slug: string
  }
  is_new?: boolean
  product_type?: string
  translations?: ProductTranslation[]
  gender?: string | null
}

interface PopularProductsCarouselProps {
  className?: string
}


export default function PopularProductsCarousel({ className = '' }: PopularProductsCarouselProps) {
  const { t, i18n } = useTranslation('common')
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [currentPage, setCurrentPage] = useState(0)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const autoPlayRef = useRef<NodeJS.Timeout | null>(null)
  const itemsPerPage = 4 // A "page" for pagination dots is 4 items

  useEffect(() => {
    const fetchProducts = async () => {
      let uniqueAllProducts: Product[] = []

      try {
        const featuredResponse = await getSingleFlight('/catalog/products/featured', {
          params: { limit: 20, view: 'card' },
        })
        const featuredData = featuredResponse.data
        const featuredItems = Array.isArray(featuredData)
          ? featuredData
          : featuredData?.results || []
        uniqueAllProducts = deduplicateFeaturedProducts(
          featuredItems.map((product: Product) => ({
            ...product,
            product_type: product.product_type || 'medicines',
          }))
        ) as Product[]
      } catch (error) {
        console.error('Failed to fetch featured products:', error)
      }

      if (uniqueAllProducts.length < 8) {
        try {
          const response = await getSingleFlight('/catalog/products', {
            params: { ordering: '-created_at', limit: 20, view: 'card' },
          })
          const data = response.data
          const productsList = Array.isArray(data) ? data : data.results || []

          uniqueAllProducts = deduplicateFeaturedProducts([
            ...uniqueAllProducts,
            ...productsList.map((product: Product) => ({
              ...product,
              product_type: product.product_type || 'medicines',
            })),
          ]) as Product[]
        } catch (error) {
          console.error('Failed to fetch latest products:', error)
        }
      }

      try {
        const shuffled = [...uniqueAllProducts].sort(() => Math.random() - 0.5).slice(0, 20)
        setProducts(shuffled)
      } catch (error) {
        console.error('Failed to prepare popular products:', error)
        setProducts([])
      } finally {
        setLoading(false)
      }
    }
    fetchProducts()
  }, [])

  const totalPages = Math.ceil(products.length / itemsPerPage)

  const goToPage = (page: number) => {
    if (scrollContainerRef.current) {
      const card = scrollContainerRef.current.children[0] as HTMLElement
      if (card) {
        const cardWidth = card.offsetWidth
        const gap = 16 // Corresponds to `gap-4`
        const targetIndex = page * itemsPerPage
        // Ensure we don't scroll past the last possible position
        const maxScrollLeft = scrollContainerRef.current.scrollWidth - scrollContainerRef.current.clientWidth
        const scrollAmount = Math.min(targetIndex * (cardWidth + gap), maxScrollLeft)

        scrollContainerRef.current.scrollTo({
          left: scrollAmount,
          behavior: 'smooth',
        })
      }
    }
  }

  // Auto-scroll by one card at a time
  useEffect(() => {
    if (products.length <= itemsPerPage) return

    const startAutoPlay = () => {
      autoPlayRef.current = setInterval(() => {
        if (scrollContainerRef.current) {
          const container = scrollContainerRef.current
          const card = container.children[0] as HTMLElement
          if (!card) return

          const cardWidth = card.offsetWidth
          const gap = 16
          const scrollAmount = cardWidth + gap
          const nextScrollLeft = container.scrollLeft + scrollAmount

          // If the next scroll position would go into the empty space at the end, rewind smoothly.
          if (nextScrollLeft + container.clientWidth > container.scrollWidth) {
            container.scrollTo({ left: 0, behavior: 'smooth' })
          } else {
            container.scrollBy({ left: scrollAmount, behavior: 'smooth' })
          }
        }
      }, 5000)
    }

    startAutoPlay()

    return () => {
      if (autoPlayRef.current) {
        clearInterval(autoPlayRef.current)
      }
    }
  }, [products.length])

  // Update active dot based on scroll position
  useEffect(() => {
    const container = scrollContainerRef.current
    let scrollTimeout: NodeJS.Timeout

    const handleScroll = () => {
      if (container) {
        const card = container.children[0] as HTMLElement
        if (!card) return

        const cardWidth = card.offsetWidth
        const gap = 16
        const pageWidth = itemsPerPage * (cardWidth + gap)

        // Use Math.floor to be more precise about which page we're on
        const newPage = Math.floor((container.scrollLeft + pageWidth / 2) / pageWidth)

        if (newPage < totalPages && newPage !== currentPage) {
          setCurrentPage(newPage)
        }
      }
    }

    const debouncedHandleScroll = () => {
      clearTimeout(scrollTimeout)
      scrollTimeout = setTimeout(handleScroll, 150)
    }

    container?.addEventListener('scroll', debouncedHandleScroll)
    return () => container?.removeEventListener('scroll', debouncedHandleScroll)
  }, [currentPage, totalPages])


  if (loading) {
    return (
      <div className={`py-12 ${className}`}>
        <div className="flex items-center justify-center">
          <svg
            className="h-8 w-8 animate-spin text-red-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </div>
      </div>
    )
  }

  if (products.length === 0) {
    return null
  }

  const getPaginationDots = () => {
    const maxDots = 3
    if (totalPages <= maxDots) {
      return Array.from({ length: totalPages }, (_, i) => i) // e.g., [0, 1, 2]
    }
    if (currentPage === 0) {
      return [0, 1, 2]
    }
    if (currentPage === totalPages - 1) {
      return [totalPages - 3, totalPages - 2, totalPages - 1]
    }
    return [currentPage - 1, currentPage, currentPage + 1]
  }

  return (
    <section className={`py-12 ${className}`}>
      <div className="mx-auto max-w-6xl px-4">
        <h2 className="text-3xl font-bold text-main mb-8 text-center">
          {t('section_best_sellers', 'Хиты продаж')}
        </h2>
        <div className="relative mb-8">
          <div
            ref={scrollContainerRef}
            className="flex gap-4 overflow-x-auto scrollbar-hide scroll-smooth"
            style={{
              scrollbarWidth: 'none',
              msOverflowStyle: 'none',
            }}
          >
            {products.map((product) => {
              const { price: parsedVariantPrice, currency: parsedVariantCurrency } = parsePriceWithCurrency(product.active_variant_price)
              const { price: parsedBasePrice, currency: parsedBaseCurrency } = parsePriceWithCurrency(product.price)
              const displayPrice = parsedVariantPrice ?? parsedBasePrice ?? product.price
              const displayCurrency = product.active_variant_currency || parsedVariantCurrency || parsedBaseCurrency || product.currency
              const oldPriceSource =
                product.active_variant_old_price_formatted ||
                product.old_price_formatted ||
                product.old_price ||
                product.oldPrice
              const { price: parsedOldPrice, currency: parsedOldCurrency } = parsePriceWithCurrency(oldPriceSource)
              const displayOldCurrency = parsedOldCurrency || displayCurrency || product.currency

              // Форматируем старую цену, убирая лишние нули
              let displayOldPrice = displayOldCurrency === displayCurrency ? parsedOldPrice ?? oldPriceSource : null
              if (displayOldPrice && typeof displayOldPrice === 'string') {
                // Убираем лишние нули после запятой
                displayOldPrice = displayOldPrice.replace(/(\.\d*?[1-9])0+$/, '$1').replace(/\.0+$/, '')
              }

              const displayPriceLabel = displayPrice ? formatPrice(displayPrice, displayCurrency, i18n.language) : null
              const displayOldPriceLabel = displayOldPrice ? formatPrice(displayOldPrice, displayCurrency, i18n.language) : null
              const displayCurrencyLabel = displayCurrency ? String(displayCurrency) : null
              const displayOldCurrencyLabel = displayOldCurrency ? String(displayOldCurrency) : null
              const priceValue = parseNumber(displayPrice)
              const oldPriceValue = parseNumber(displayOldPrice)
              const discountPercent = priceValue !== null && oldPriceValue !== null && oldPriceValue > priceValue && oldPriceValue > 0
                ? Math.round(((oldPriceValue - priceValue) / oldPriceValue) * 100)
                : null
              const ratingValue = product.rating == null ? null : Number(product.rating)
              const displayRating = ratingValue !== null && Number.isFinite(ratingValue) && ratingValue > 0
                ? Math.min(5, ratingValue)
                : null
              const displayReviewsCount = typeof product.reviews_count === 'number' && product.reviews_count > 0
                ? product.reviews_count
                : null
              const reviewsLabel = displayReviewsCount !== null
                ? t('product_reviews_count', {
                    count: displayReviewsCount,
                    formattedCount: new Intl.NumberFormat(i18n.language).format(displayReviewsCount),
                  })
                : t('product_reviews_title', 'Отзывы')

              const localizedName = getLocalizedProductName(product.name, t, product.translations, i18n.language)
              const carouselRawVideo =
                (product as { main_video_url?: string }).main_video_url || product.video_url
              const carouselVideoSrc =
                carouselRawVideo && isVideoUrl(carouselRawVideo)
                  ? resolveMediaUrl(carouselRawVideo)
                  : null
              const carouselYtId =
                carouselVideoSrc && carouselRawVideo && isVideoUrl(carouselRawVideo)
                  ? extractYouTubeId(carouselVideoSrc)
                  : null
              const carouselNonYoutubeEmbed =
                carouselVideoSrc && !carouselYtId ? getVideoEmbedUrl(carouselVideoSrc, 'player') : null
              const carouselHasGallery = normalizeProductCardImages(
                product.main_image_url,
                product.images
              ).length > 1
              return (
                <div
                  key={buildProductIdentityKey(product, product.product_type)}
                  className="group relative flex h-full w-44 flex-shrink-0 snap-start flex-col gap-2 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-2 shadow-[0_2px_10px_rgba(15,23,42,0.08)] transition-all duration-300 hover:-translate-y-1 hover:border-gray-300 hover:shadow-[0_12px_28px_rgba(15,23,42,0.16)] dark:hover:border-gray-600 md:w-60"
                >
                  <Link
                    href={buildProductUrl(product.product_type || 'medicines', product.slug)}
                    className="relative block w-full aspect-[4/5] overflow-hidden bg-gray-100/50 rounded-xl"
                  >
                    {carouselHasGallery ? (
                      <ProductCardImageGallery
                        productId={product.id}
                        name={localizedName}
                        mainImageUrl={product.main_image_url}
                        images={product.images}
                        imageFitClass="object-cover"
                      />
                    ) : carouselYtId ? (
                      <LazyYouTubeCard
                        youtubeId={carouselYtId}
                        youtubeThumb={getYouTubeCardThumbnailUrl(carouselRawVideo || carouselVideoSrc)}
                        alt={localizedName}
                        className="transition-transform duration-500 group-hover:scale-105"
                      />
                    ) : carouselNonYoutubeEmbed ? (
                      <iframe
                        src={carouselNonYoutubeEmbed}
                        title=""
                        className="pointer-events-none h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowFullScreen
                      />
                    ) : carouselVideoSrc ? (
                      <InViewAutoplayVideo
                        src={carouselVideoSrc}
                        poster={
                          (product.main_image_url ? resolveMediaUrl(product.main_image_url) : null) ||
                          getPlaceholderImageUrl({ type: 'product', id: product.id })
                        }
                        videoClassName="transition-transform duration-500 group-hover:scale-105"
                        alt={localizedName}
                      />
                    ) : (
                      <ProductCardImageGallery
                        productId={product.id}
                        name={localizedName}
                        mainImageUrl={product.main_image_url}
                        images={product.images}
                        imageFitClass="object-cover"
                      />
                    )}

                    {product.is_new && (
                      <div className="absolute left-2 top-2 flex flex-col gap-1 z-10">
                        <span className="rounded-md bg-green-100/90 backdrop-blur-sm px-2 py-0.5 text-xs font-medium text-green-700 ring-1 ring-green-200">
                          {t('product_new', 'Новинка')}
                        </span>
                      </div>
                    )}
                    
                    <div
                      className="absolute top-2 right-2 z-20 flex flex-col gap-1.5"
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                      }}
                    >
                      <FavoriteButton
                        productId={favoriteApiProductId(product, product.product_type)}
                        productType={product.product_type || 'medicines'}
                        cornerIcon={true}
                      />
                      <ShareButton
                        title={localizedName}
                        imageUrl={
                          product.main_image_url
                            ? resolveMediaUrl(product.main_image_url)
                            : null
                        }
                        slug={product.slug}
                        productType={product.product_type || 'medicines'}
                        cornerIcon={true}
                      />
                    </div>
                  </Link>

                  <Link 
                    href={buildProductUrl(product.product_type || 'medicines', product.slug)}
                    className="flex flex-1 flex-col px-1 pb-1"
                  >
                    <div className="mb-1 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                      <span
                        className={`inline-flex items-center gap-1 text-base md:text-lg font-bold leading-tight tracking-tight ${
                          discountPercent !== null
                            ? 'text-green-600 dark:text-green-400'
                            : 'text-[var(--accent)]'
                        }`}
                      >
                        {displayPriceLabel ? (
                          <>
                            {displayPriceLabel}
                            {displayCurrencyLabel && (
                              <span>{getCurrencySymbol(displayCurrencyLabel)}</span>
                            )}
                          </>
                        ) : t('price_on_request', 'Цена по запросу')}
                      </span>
                      {displayOldPriceLabel && (
                        <span className="inline-flex items-center gap-1 text-xs md:text-sm text-gray-400">
                          <span className="line-through">{displayOldPriceLabel}</span>
                          {displayOldCurrencyLabel && (
                            <span>{getCurrencySymbol(displayOldCurrencyLabel)}</span>
                          )}
                        </span>
                      )}
                      {displayOldPriceLabel && discountPercent !== null && (
                        <span className="text-xs font-semibold !text-red-500">-{discountPercent}%</span>
                      )}
                    </div>
                    {product.brand && (
                      <div className="text-[10px] md:text-xs text-gray-400 uppercase tracking-widest leading-none mb-1">
                        {product.brand.name}
                      </div>
                    )}
                    <h3 className="line-clamp-2 min-h-[2.5rem] text-sm font-medium leading-5 text-[var(--text-strong)]">
                      {localizedName}
                    </h3>
                    <div className="mt-auto flex min-h-5 items-center gap-1.5 pt-2 text-xs">
                      {displayRating !== null && (
                        <>
                          <StarIcon className="h-4 w-4 flex-none text-amber-400" aria-hidden="true" />
                          <span className="font-semibold text-[var(--text-strong)]">{displayRating.toFixed(1)}</span>
                        </>
                      )}
                      <span className={`${displayRating !== null ? 'ml-1' : ''} inline-flex items-center gap-1 text-[var(--text-weak)]`}>
                        <ChatBubbleOvalLeftIcon className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" aria-hidden="true" />
                        {reviewsLabel}
                      </span>
                    </div>
                  </Link>
                </div>
              )
            })}
          </div>
        </div>

        {totalPages > 1 && (
          <div className="w-full flex justify-center items-center py-4">
            <div className="flex justify-center items-center gap-2.5 px-4 py-2">
              {getPaginationDots().map((pageIndex) => (
                <button
                  key={pageIndex}
                  onClick={() => goToPage(pageIndex)}
                  className="transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 rounded-full"
                  style={{
                    width: pageIndex === currentPage ? '14px' : '10px',
                    height: pageIndex === currentPage ? '14px' : '10px',
                    borderRadius: '50%',
                    border: pageIndex === currentPage ? 'none' : '2px solid #9ca3af',
                    backgroundColor: pageIndex === currentPage ? '#111827' : '#ffffff',
                    cursor: 'pointer',
                    boxShadow:
                      pageIndex === currentPage
                        ? '0 2px 8px rgba(0,0,0,0.4), 0 0 0 2px rgba(255,255,255,0.5)'
                        : '0 1px 3px rgba(0,0,0,0.2)',
                  }}
                  aria-label={`Перейти на страницу ${pageIndex + 1}`}
                />
              ))}
            </div>
          </div>
        )}
      </div>
      <style jsx>{`
        .scrollbar-hide::-webkit-scrollbar {
          display: none;
        }
      `}</style>
    </section>
  )
}
