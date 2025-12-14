import { useState, useEffect } from 'react'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import ProductCard from './ProductCard'

interface Product {
  id: number
  name: string
  slug: string
  price: string | null
  currency: string
  oldPrice?: string | null
  main_image_url?: string | null
  main_image?: string | null
  product_type?: string
  is_featured?: boolean
}

interface SimilarProductsProps {
  productType: string
  currentProductId?: number
  currentProductSlug?: string
  limit?: number
}

/**
 * Компонент для отображения похожих товаров
 */
export default function SimilarProducts({
  productType,
  currentProductId,
  currentProductSlug,
  limit = 8
}: SimilarProductsProps) {
  const { t } = useTranslation('common')
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchSimilarProducts = async () => {
      try {
        setLoading(true)
        let endpoint = ''
        
        // Определяем endpoint в зависимости от типа товара
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
            limit: limit + 1, // Получаем на 1 больше, чтобы исключить текущий товар
            ordering: '-created_at'
          }
        })

        // Фильтруем текущий товар из списка
        let filteredProducts = response.data.results || response.data || []
        if (currentProductId) {
          filteredProducts = filteredProducts.filter((p: Product) => p.id !== currentProductId)
        } else if (currentProductSlug) {
          filteredProducts = filteredProducts.filter((p: Product) => p.slug !== currentProductSlug)
        }
        
        // Берем только нужное количество
        setProducts(filteredProducts.slice(0, limit))
      } catch (error) {
        console.error('Error fetching similar products:', error)
        setProducts([])
      } finally {
        setLoading(false)
      }
    }

    fetchSimilarProducts()
  }, [productType, currentProductId, currentProductSlug, limit])

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

  return (
    <div className="mt-8">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
        {t('similar_products', 'Похожие товары')}
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {products.map((product) => (
          <ProductCard
            key={product.id}
            id={product.id}
            name={product.name}
            slug={product.slug}
            price={product.price}
            currency={product.currency}
            oldPrice={product.oldPrice}
            imageUrl={product.main_image_url || product.main_image}
            badge={product.is_featured ? t('product_featured', 'Хит') : null}
            productType={product.product_type || productType}
            isBaseProduct={isBaseProduct}
          />
        ))}
      </div>
    </div>
  )
}

