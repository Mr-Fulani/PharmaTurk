import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import AddToCartButton from './AddToCartButton'
import FavoriteButton from './FavoriteButton'
import { getPlaceholderImageUrl, resolveMediaUrl } from '../lib/media'

interface Product {
  id: number
  name: string
  slug: string
  price: string | number | null
  currency?: string | null
  oldPrice?: string | number | null
  old_price?: string | number | null
  old_price_formatted?: string | null
  active_variant_price?: string | number | null
  active_variant_currency?: string | null
  badge?: string | null
  rating?: number | null
  main_image_url?: string | null
  brand?: {
    id: number
    name: string
    slug: string
  }
  is_new?: boolean
  product_type?: string
}

interface PopularProductsCarouselProps {
  className?: string
}

const parsePriceWithCurrency = (value?: string | number | null) => {
  if (value === null || typeof value === 'undefined') {
    return { price: null as string | number | null, currency: null as string | null }
  }
  if (typeof value === 'number') {
    return { price: value, currency: null as string | null }
  }
  const trimmed = value.trim()
  const match = trimmed.match(/^([0-9]+(?:[.,][0-9]+)?)\s*([A-Za-z]{3,5})$/)
  if (match) {
    return { price: match[1].replace(',', '.'), currency: match[2].toUpperCase() }
  }
  return { price: trimmed, currency: null as string | null }
}

const parseNumber = (value: string | number | null | undefined) => {
  if (value === null || typeof value === 'undefined') return null
  const normalized = String(value).replace(',', '.').replace(/[^0-9.]/g, '')
  if (!normalized) return null
  const num = Number(normalized)
  return Number.isFinite(num) ? num : null
}

export default function PopularProductsCarousel({ className = '' }: PopularProductsCarouselProps) {
  const { t } = useTranslation('common')
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [currentPage, setCurrentPage] = useState(0)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const autoPlayRef = useRef<NodeJS.Timeout | null>(null)
  const itemsPerPage = 4 // A "page" for pagination dots is 4 items

  useEffect(() => {
    const fetchProducts = async () => {
      try {
        console.log('[PopularProducts] Fetching products...')
        const [medicinesRes, clothingRes, shoesRes, electronicsRes] = await Promise.allSettled([
          api.get('/catalog/products/featured'),
          api.get('/catalog/clothing/products/featured'),
          api.get('/catalog/shoes/products/featured'),
          api.get('/catalog/electronics/products/featured'),
        ])
        console.log('[PopularProducts] Fetched, processing responses...')

        const allProducts: Product[] = []
        const processResponse = (res: PromiseSettledResult<any>, product_type: string) => {
          if (res.status === 'fulfilled' && res.value.data) {
            const data = res.value.data
            const items = Array.isArray(data) ? data : data.results || []
            return items.map((p: any) => ({ ...p, product_type }))
          }
          return []
        }
        allProducts.push(...processResponse(medicinesRes, 'medicines'))
        allProducts.push(...processResponse(clothingRes, 'clothing'))
        allProducts.push(...processResponse(shoesRes, 'shoes'))
        allProducts.push(...processResponse(electronicsRes, 'electronics'))

        if (allProducts.length === 0) {
          try {
            const response = await api.get('/catalog/products', {
              params: { ordering: '-created_at', limit: 20 },
            })
            const data = response.data
            const productsList = Array.isArray(data) ? data : data.results || []
            allProducts.push(...productsList.map((p: any) => ({ ...p, product_type: 'medicines' })))
          } catch (error) {
            console.error('Failed to fetch latest products:', error)
          }
        }

        const shuffled = allProducts.sort(() => Math.random() - 0.5).slice(0, 20)
        console.log('[PopularProducts] Sample product prices:', shuffled.slice(0, 3).map(p => ({ name: p.name, price: p.price, currency: p.currency })))
        setProducts(shuffled)
      } catch (error) {
        console.error('Failed to fetch popular products:', error)
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
              const oldPriceSource = product.old_price_formatted ?? product.old_price ?? product.oldPrice
              const { price: parsedOldPrice, currency: parsedOldCurrency } = parsePriceWithCurrency(oldPriceSource)
              const displayOldCurrency = parsedOldCurrency || displayCurrency || product.currency
              const displayOldPrice = displayOldCurrency === displayCurrency ? parsedOldPrice ?? oldPriceSource : null
              const displayPriceLabel = displayPrice ? String(displayPrice) : null
              const displayOldPriceLabel = displayOldPrice ? String(displayOldPrice) : null
              const displayCurrencyLabel = displayCurrency ? String(displayCurrency) : null
              const displayOldCurrencyLabel = displayOldCurrency ? String(displayOldCurrency) : null
              const priceValue = parseNumber(displayPrice)
              const oldPriceValue = parseNumber(displayOldPrice)
              const discountPercent = priceValue !== null && oldPriceValue !== null && oldPriceValue > priceValue && oldPriceValue > 0
                ? Math.round(((oldPriceValue - priceValue) / oldPriceValue) * 100)
                : null

              return (
                <div
                  key={product.id}
                  className="flex-shrink-0 w-64 bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-lg transition-all duration-200 overflow-hidden group"
                >
                <Link
                  href={`/product/${product.product_type || 'medicines'}/${product.slug}`}
                  className="relative block w-full h-80 overflow-hidden bg-gray-100"
                >
                  <img
                    src={
                      (product.main_image_url ? resolveMediaUrl(product.main_image_url) : null) ||
                      getPlaceholderImageUrl({ type: 'product', id: product.id })
                    }
                    alt={product.name}
                    className="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
                    onError={(e) => {
                      e.currentTarget.src = getPlaceholderImageUrl({
                        type: 'product',
                        id: `${product.id}-fallback`,
                      })
                    }}
                  />
                  {product.is_new && (
                    <span className="absolute left-2 top-2 rounded-md bg-pink-100 px-2 py-0.5 text-xs font-medium text-pink-700 ring-1 ring-pink-200">
                      {t('product_new', 'Новинка')}
                    </span>
                  )}
                  <div
                    className="absolute top-2 right-2 z-20"
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                    }}
                  >
                    <FavoriteButton
                      productId={product.id}
                      productType={product.product_type || 'medicines'}
                      iconOnly={true}
                      className="!p-2 !rounded-full w-10 h-10 bg-white/90 hover:bg-white shadow-md hover:shadow-lg flex items-center justify-center hover:scale-110 transition-transform"
                    />
                  </div>
                </Link>
                <div className="p-4">
                  {product.brand && (
                    <div className="text-xs text-gray-500 mb-1">{product.brand.name}</div>
                  )}
                  <Link
                    href={`/product/${product.product_type || 'medicines'}/${product.slug}`}
                    className="block mb-2"
                  >
                  <h3 className="text-sm font-semibold text-gray-900 line-clamp-2 hover-text-warm transition-colors">
                      {product.name}
                    </h3>
                  </Link>
                  <div className="mb-3">
                    <div className="flex items-baseline gap-2">
                      <div className="text-lg font-bold text-[var(--text-strong)]">
                        {displayPriceLabel
                          ? displayCurrencyLabel
                            ? `${displayPriceLabel} ${displayCurrencyLabel}`
                            : displayPriceLabel
                          : t('price_on_request', 'Цена по запросу')}
                      </div>
                      {displayOldPriceLabel && (
                        <div className="text-sm text-gray-400 line-through">
                          {displayOldCurrencyLabel
                            ? `${displayOldPriceLabel} ${displayOldCurrencyLabel}`
                            : displayOldPriceLabel}
                        </div>
                      )}
                      {displayOldPriceLabel && discountPercent !== null && (
                        <div className="text-sm font-semibold !text-red-600">-{discountPercent}%</div>
                      )}
                    </div>
                  </div>
                  <AddToCartButton
                    productId={product.id}
                    productType={product.product_type || 'medicines'}
                    productSlug={product.slug}
                    className="w-full"
                    label={t('add_to_cart', 'В корзину')}
                  />
                </div>
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
