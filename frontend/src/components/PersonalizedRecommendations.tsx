'use client'

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
  old_price?: string | null
  main_image_url?: string | null
  main_image?: string | null
  product_type?: string
  is_featured?: boolean
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
        <h2 className="text-2xl font-bold mb-6 text-gray-900 dark:text-white">
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
      </section>
    )
  }

  if (products.length === 0) return null

  return (
    <section className="py-8">
      <h2 className="text-2xl font-bold mb-6 text-gray-900 dark:text-white">
        {basedOn === 'your_history'
          ? t('recommended_for_you', 'Вам может понравиться')
          : t('trending_now', 'Популярное сейчас')}
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {products.map((product) => (
          <ProductCard
            key={product.id}
            id={product.id}
            name={product.name}
            slug={product.slug}
            price={product.price != null ? String(product.price) : null}
            currency={product.currency || 'RUB'}
            oldPrice={product.old_price != null ? String(product.old_price) : null}
            imageUrl={product.main_image_url || product.main_image}
            productType={product.product_type || 'medicines'}
            isBaseProduct={true}
          />
        ))}
      </div>
    </section>
  )
}
