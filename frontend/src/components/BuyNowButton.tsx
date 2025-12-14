import { useState } from 'react'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import api, { initCartSession } from '../lib/api'
import { useCartStore } from '../store/cart'

interface BuyNowButtonProps {
  productId?: number
  productType?: string
  productSlug?: string
  size?: string
  requireSize?: boolean
  className?: string
  quantity?: number
}

/**
 * Кнопка "Купить в один клик" - добавляет товар в корзину и перенаправляет на checkout
 */
export default function BuyNowButton({
  productId,
  productType = 'medicines',
  productSlug,
  size,
  requireSize = false,
  className,
  quantity = 1
}: BuyNowButtonProps) {
  const [loading, setLoading] = useState(false)
  const router = useRouter()
  const { refresh } = useCartStore()
  const { t } = useTranslation('common')

  const buyNow = async () => {
    setLoading(true)
    try {
      if (requireSize && !size) {
        alert(t('select_size', 'Выберите размер'))
        setLoading(false)
        return
      }
      initCartSession()
      const body = new URLSearchParams()
      body.set('quantity', String(quantity))
      const baseTypes = [
        'medicines', 'supplements', 'medical-equipment', 'medical_equipment',
        'furniture', 'tableware', 'accessories', 'jewelry',
        'underwear', 'headwear'
      ]
      const isBase = baseTypes.includes(productType)
      if (isBase && productId !== undefined) {
        body.set('product_id', String(productId))
      } else {
        if (productType) {
          body.set('product_type', productType)
        }
        if (productSlug) {
          body.set('product_slug', productSlug)
        }
        if (size) {
          body.set('size', size)
        }
      }
      try {
        await api.post('/orders/cart/add', body, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
      } catch (e: any) {
        await api.post('/orders/cart/add/', body, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
      }
      await refresh()
      // Перенаправляем на страницу оформления заказа
      router.push('/checkout')
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || t('buy_now_error', 'Ошибка при оформлении заказа')
      alert(String(detail))
      setLoading(false)
    }
  }

  return (
    <button
      onClick={buyNow}
      disabled={loading}
      className={`inline-flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60 transition-all duration-200 ${className || ''}`}
    >
      {loading ? (
        <svg className="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      ) : (
        t('buy_now', 'Купить в один клик')
      )}
    </button>
  )
}

