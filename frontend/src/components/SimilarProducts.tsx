import { useState, useEffect } from 'react'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import ProductCard from './ProductCard'

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
  product_type?: string
  is_featured?: boolean
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

/**
 * Компонент для отображения похожих товаров
 */
export default function SimilarProducts({
  productType,
  currentProductId,
  currentProductSlug,
  limit = 8,
  useRecsys = false
}: SimilarProductsProps) {
  const { t } = useTranslation('common')
  const [products, setProducts] = useState<Product[]>([])
  const [reasons, setReasons] = useState<Record<number, string>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchSimilarProducts = async () => {
      try {
        setLoading(true)
        if (useRecsys && currentProductSlug) {
          const response = await api.get(
            `/catalog/products/${encodeURIComponent(currentProductSlug)}/similar`,
            { params: { limit, strategy: 'balanced' } }
          )
          const results: SimilarProductResult[] = response.data.results || []
          setProducts(results.map((r) => r.product))
          const reasonMap: Record<number, string> = {}
          results.forEach((r) => {
            if (r.product?.id && r.reason) reasonMap[r.product.id] = r.reason
          })
          setReasons(reasonMap)
          return
        }

        let endpoint = ''
        if (['medicines', 'supplements', 'medical-equipment', 'furniture', 'tableware', 'accessories', 'jewelry', 'underwear', 'headwear'].includes(productType)) {
          endpoint = '/catalog/products'
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
        if (currentProductId) {
          filteredProducts = filteredProducts.filter((p: Product) => p.id !== currentProductId)
        } else if (currentProductSlug) {
          filteredProducts = filteredProducts.filter((p: Product) => p.slug !== currentProductSlug)
        }
        setProducts(filteredProducts.slice(0, limit))
        setReasons({})
      } catch (error) {
        console.error('Error fetching similar products:', error)
        setProducts([])
        setReasons({})
      } finally {
        setLoading(false)
      }
    }

    fetchSimilarProducts()
  }, [productType, currentProductId, currentProductSlug, limit, useRecsys])

  if (loading) {
    return (
      <div className="mt-8">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
          {t('similar_products', 'Похожие товары')}
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

  const isBaseProduct = ['medicines', 'supplements', 'medical-equipment', 'furniture', 'tableware', 'accessories', 'jewelry', 'underwear', 'headwear'].includes(productType)

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
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
        {t('similar_products', 'Похожие товары')}
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
            <div key={product.id} className="relative">
              <ProductCard
                id={product.id}
                name={product.name}
                slug={product.slug}
                price={displayPrice ? String(displayPrice) : null}
                currency={displayCurrency}
                oldPrice={displayOldPrice ? String(displayOldPrice) : null}
                imageUrl={product.main_image_url || product.main_image}
                badge={reasons[product.id] ? translateBadge(reasons[product.id]) : (product.is_featured ? t('product_featured', 'Хит') : null)}
                productType={product.product_type || productType}
                isBaseProduct={isBaseProduct}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
