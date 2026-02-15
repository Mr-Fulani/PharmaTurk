'use client'

import { useState, useEffect } from 'react'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import { isBaseProductType } from '../lib/product'
import ProductCard from './ProductCard'

interface Product {
  id: number
  name: string
  slug: string
  price: string | number | null
  currency?: string | null
  old_price?: string | null
  old_price_formatted?: string | null
  active_variant_price?: string | number | null
  active_variant_currency?: string | null
  active_variant_old_price_formatted?: string | null
  main_image_url?: string | null
  main_image?: string | null
  video_url?: string | null
  product_type?: string
  is_featured?: boolean
}

const parsePriceWithCurrency = (value?: string | number | null) => {
  if (value === null || typeof value === 'undefined') {
    return { price: null as string | number | null, currency: null as string | null }
  }
  if (typeof value === 'number') {
    return { price: value, currency: null as string | null }
  }
  const trimmed = String(value).trim()
  const match = trimmed.match(/^([0-9]+(?:[.,][0-9]+)?)\s*([A-Za-z]{3,5})$/)
  if (match) {
    return { price: match[1].replace(',', '.'), currency: match[2].toUpperCase() }
  }
  return { price: trimmed, currency: null as string | null }
}

/**
 * Block "Вам может понравиться" — personalized or trending from RecSys.
 */
export default function PersonalizedRecommendations() {
  const { t } = useTranslation('common')
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [basedOn, setBasedOn] = useState<string>('trending')

  useEffect(() => {
    const fetchPersonalized = async () => {
      try {
        setLoading(true)
        const res = await api.get('/recommendations/personalized/')
        const results = res.data.results || []
        setProducts(
          results.map((r: { product?: Product } & Product) =>
            r.product != null ? r.product : r
          ).filter((p: Product | undefined): p is Product => p != null && typeof p.id === 'number')
        )
        setBasedOn(res.data.based_on || 'trending')
      } catch {
        setProducts([])
        setBasedOn('trending')
      } finally {
        setLoading(false)
      }
    }
    fetchPersonalized()
  }, [])

  if (loading) {
    return (
      <section className="py-8">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-2xl md:text-3xl font-bold text-main mb-8 text-center">
            {t('recommended_for_you', 'Вам может понравиться')}
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="animate-pulse">
                <div className="bg-gray-200 dark:bg-gray-700 aspect-[4/3] rounded-lg mb-3" />
                <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded mb-2" />
                <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-2/3" />
              </div>
            ))}
          </div>
        </div>
      </section>
    )
  }

  if (products.length === 0) return null

  return (
    <section className="py-8">
      <div className="mx-auto max-w-6xl px-4">
        <h2 className="text-2xl md:text-3xl font-bold text-main mb-8 text-center">
          {basedOn === 'your_history'
            ? t('recommended_for_you', 'Вам может понравиться')
            : t('trending_now', 'Популярное сейчас')}
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
              product.old_price
            const { price: parsedOldPrice, currency: parsedOldCurrency } = parsePriceWithCurrency(oldPriceSource)
            const displayOldCurrency = parsedOldCurrency || displayCurrency
            const displayOldPrice = displayOldCurrency === displayCurrency ? (parsedOldPrice ?? oldPriceSource) : null

            const pt = product.product_type || 'medicines'
            return (
              <ProductCard
                key={product.id}
                id={product.id}
                name={product.name}
                slug={product.slug}
                price={displayPrice != null ? String(displayPrice) : null}
                currency={displayCurrency}
                oldPrice={displayOldPrice != null ? String(displayOldPrice) : null}
                imageUrl={product.main_image_url || product.main_image}
                videoUrl={product.video_url}
                productType={pt}
                isBaseProduct={isBaseProductType(pt)}
              />
            )
          })}
        </div>
      </div>
    </section>
  )
}
