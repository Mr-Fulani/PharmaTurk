import { useState, useEffect } from 'react'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import { buildProductIdentityKey, isBaseProductType } from '../lib/product'
import ProductCard from './ProductCard'
import { ProductTranslation } from '../lib/i18n'

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
  active_variant_old_price_formatted?: string | null
  main_image_url?: string | null
  main_image?: string | null
  video_url?: string | null
  main_video_url?: string | null
  main_gif_url?: string | null
  product_type?: string
  is_featured?: boolean
  is_new?: boolean
  translations?: ProductTranslation[]
  base_product_id?: number | null
  gender?: string | null
  saving_percent?: number | null
  saving_amount?: number | null
}

interface SimilarProductResult {
  product: Product
  similarity_score?: number
  business_score?: number
  reason?: string
}

interface SimilarProductsProps {
  productType: string
  currentProductId?: number
  currentProductSlug?: string
  currentBaseProductId?: number | null
  limit?: number
  /** Use RecSys API (vector similar) when slug is available */
  useRecsys?: boolean
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

const normalizeProductType = (value?: string | null) =>
  (value || '').toString().trim().replace(/_/g, '-').toLowerCase()

/**
 * Компонент для отображения похожих товаров
 */
export default function SimilarProducts({
  productType,
  currentProductId,
  currentProductSlug,
  currentBaseProductId,
  limit = 8,
  useRecsys = false
}: SimilarProductsProps) {
  const { t, i18n } = useTranslation('common')
  const [products, setProducts] = useState<Product[]>([])
  const [reasons, setReasons] = useState<Record<number, string>>({})
  const [loading, setLoading] = useState(true)
  const [showingAnalogs, setShowingAnalogs] = useState(false)

  useEffect(() => {
    const fetchSimilarProducts = async () => {
      try {
        setLoading(true)
        setShowingAnalogs(false)
        const normalizedProductType = normalizeProductType(productType)

        if (normalizedProductType === 'medicines' && currentProductSlug) {
          const analogResponse = await api.get(
            `/catalog/medicines/products/${encodeURIComponent(currentProductSlug)}/analogs`,
            { params: { limit } }
          )
          const analogResults = analogResponse.data?.results || []
          if (analogResults.length > 0) {
            const mappedProducts: Product[] = analogResults
              .filter((analog: any) => {
                if (currentProductId && analog.id === currentProductId) return false
                if (currentProductSlug && analog.slug === currentProductSlug) return false
                return true
              })
              .slice(0, limit)
              .map((analog: any) => ({
                id: analog.id,
                name: analog.name,
                slug: analog.slug,
                price: analog.price,
                currency: analog.display_currency || analog.original_currency || 'RUB',
                old_price: analog.old_price,
                main_image_url: analog.main_image_url,
                product_type: 'medicines',
                is_new: false,
                is_featured: false,
                is_available: analog.is_available,
                saving_percent: analog.saving_percent,
                saving_amount: analog.saving_amount,
              }))

            setProducts(mappedProducts)
            const reasonMap: Record<number, string> = {}
            mappedProducts.forEach((analog) => {
              if (analog.saving_percent && analog.saving_percent > 0) {
                reasonMap[analog.id] = `Выгода -${analog.saving_percent}%`
              }
            })
            setReasons(reasonMap)
            setShowingAnalogs(true)
            return
          }
        }

        // RecSys similar только для Product; jewelry — в JewelryProductViewSet, эндпоинта /similar нет
        if (useRecsys && currentProductSlug && productType !== 'jewelry') {
          const response = await api.get(
            `/catalog/products/${encodeURIComponent(currentProductSlug)}/similar`,
            { params: { limit: limit + 1, strategy: 'balanced' } } // Берем +1 на случай если API вернет текущий товар
          )
          const results: SimilarProductResult[] = response.data.results || []
          if (results.length > 0) {
            let mappedProducts = results.map((r) => r.product)
            
            mappedProducts = mappedProducts.filter((p: Product) => {
              // Filter out the exact same product using id or slug
              if (currentProductId && p.id === currentProductId) return false
              if (currentProductSlug && p.slug === currentProductSlug) return false
              // Also filter if they share the same base_product_id
              if (currentBaseProductId && p.base_product_id === currentBaseProductId) return false
              if (p.base_product_id && p.id === currentProductId) return false
              return true
            })
            mappedProducts = mappedProducts.slice(0, limit)

            setProducts(mappedProducts)
            const reasonMap: Record<number, string> = {}
            results.forEach((r) => {
              if (r.product?.id && r.reason) reasonMap[r.product.id] = r.reason
            })
            setReasons(reasonMap)
            setShowingAnalogs(false)
            return
          }
        }

        let endpoint = ''
        if (['medicines', 'supplements', 'medical-equipment', 'furniture', 'tableware', 'accessories', 'underwear', 'headwear'].includes(productType)) {
          endpoint = '/catalog/products'
        } else if (productType === 'jewelry') {
          endpoint = '/catalog/jewelry/products'
        } else if (productType === 'clothing') {
          endpoint = '/catalog/clothing/products'
        } else if (productType === 'shoes') {
          endpoint = '/catalog/shoes/products'
        } else if (productType === 'electronics') {
          endpoint = '/catalog/electronics/products'
        } else {
          endpoint = '/catalog/products'
        }

        const response = await api.get(endpoint, {
          params: {
            limit: limit + 1,
            ordering: '-created_at'
          }
        })

        let filteredProducts = response.data.results || response.data || []
        filteredProducts = filteredProducts.filter((p: Product) => {
          if (currentProductId && p.id === currentProductId) return false
          if (currentProductSlug && p.slug === currentProductSlug) return false
          if (currentBaseProductId && p.base_product_id === currentBaseProductId) return false
          return true
        })
        setProducts(filteredProducts.slice(0, limit))
        setReasons({})
        setShowingAnalogs(false)
      } catch (error) {
        console.error('Error fetching similar products:', error)
        setProducts([])
        setReasons({})
        setShowingAnalogs(false)
      } finally {
        setLoading(false)
      }
    }

    fetchSimilarProducts()
  }, [
    useRecsys,
    currentProductSlug,
    currentProductId,
    currentBaseProductId,
    productType,
    limit,
  ])

  if (loading) {
    return (
      <div className="mt-8">
        <h2 className="text-2xl font-bold text-[var(--text-strong)] mb-6">
          {normalizeProductType(productType) === 'medicines'
            ? t('analogs_title_short', 'Аналоги')
            : t('similar_products', 'Похожие товары')}
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="animate-pulse">
              <div className="bg-gray-200 aspect-[4/3] rounded-lg mb-3"></div>
              <div className="h-4 bg-gray-200 rounded mb-2"></div>
              <div className="h-4 bg-gray-200 rounded w-2/3"></div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (products.length === 0) {
    return null
  }

  const isBaseProduct = isBaseProductType(productType)

  const translateBadge = (reason: string): string => {
    if (!reason?.trim()) return ''
    const trimmed = reason.trim()
    if (trimmed === 'Рекомендуем') return t('badge_recommend', 'Рекомендуем')
    if (trimmed === 'Очень похожий стиль') return t('badge_similar_style', 'Очень похожий стиль')
    if (trimmed === 'Похожий дизайн') return t('badge_similar_design', 'Похожий дизайн')
    const brandMatch = trimmed.match(/^Бренд\s+(.+)$/)
    if (brandMatch) return t('badge_brand', { brand: brandMatch[1], defaultValue: `Бренд ${brandMatch[1]}` })
    const parts = trimmed.split(/\s*,\s*/).map((p) => {
      const p2 = p.trim()
      if (p2 === 'Рекомендуем') return t('badge_recommend', 'Рекомендуем')
      if (p2 === 'Очень похожий стиль') return t('badge_similar_style', 'Очень похожий стиль')
      if (p2 === 'Похожий дизайн') return t('badge_similar_design', 'Похожий дизайн')
      const m = p2.match(/^Бренд\s+(.+)$/)
      if (m) return t('badge_brand', { brand: m[1], defaultValue: `Бренд ${m[1]}` })
      return p2
    })
    return parts.join(', ')
  }

  return (
    <div className="mt-8">
      <h2 className="text-2xl font-bold text-[var(--text-strong)] mb-6">
        {showingAnalogs
          ? t('analogs_title_short', 'Аналоги')
          : t('similar_products', 'Похожие товары')}
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {products.map((product) => {
          const { price: parsedVariantPrice, currency: parsedVariantCurrency } = parsePriceWithCurrency(product.active_variant_price)
          const { price: parsedBasePrice, currency: parsedBaseCurrency } = parsePriceWithCurrency(product.price)
          const displayPrice = parsedVariantPrice ?? parsedBasePrice ?? product.price
          const displayCurrency = product.active_variant_currency || parsedVariantCurrency || parsedBaseCurrency || product.currency || 'RUB'
          const oldPriceSource =
            product.active_variant_old_price_formatted ||
            product.old_price_formatted ||
            product.old_price ||
            product.oldPrice
          const { price: parsedOldPrice, currency: parsedOldCurrency } = parsePriceWithCurrency(oldPriceSource)
          const displayOldCurrency = parsedOldCurrency || displayCurrency
          const displayOldPrice = displayOldCurrency === displayCurrency ? parsedOldPrice ?? oldPriceSource : null

          return (
            <div key={buildProductIdentityKey(product, product.product_type)} className="relative">
              <ProductCard
                id={product.id}
                baseProductId={(product as { base_product_id?: number }).base_product_id}
                name={product.name}
                slug={product.slug}
                price={displayPrice ? String(displayPrice) : null}
                currency={displayCurrency}
                oldPrice={displayOldPrice ? String(displayOldPrice) : null}
                imageUrl={product.main_image_url || product.main_image}
                videoUrl={product.video_url}
                mainVideoUrl={product.main_video_url}
                mainGifUrl={product.main_gif_url}
                hasManualMainImage={(product as any).has_manual_main_image}
                badge={reasons[product.id] ? translateBadge(reasons[product.id]) : (product.is_featured ? t('product_featured', 'Хит') : null)}
                productType={product.product_type || productType}
                isBaseProduct={isBaseProduct}
                isNew={product.is_new}
                isFeatured={product.is_featured}
                translations={product.translations}
                locale={i18n.language}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
