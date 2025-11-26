import { useState } from 'react'
import { useTranslation } from 'next-i18next'
import api, { initCartSession } from '../lib/api'
import { useCartStore } from '../store/cart'

interface AddToCartButtonProps {
  productId?: number
  productType?: string
  productSlug?: string
  className?: string
  label?: string
}

export default function AddToCartButton({
  productId,
  productType = 'medicines',
  productSlug,
  className,
  label
}: AddToCartButtonProps) {
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const { refresh } = useCartStore()
  const { t } = useTranslation('common')

  const add = async () => {
    setLoading(true)
    try {
      initCartSession()
      const body = new URLSearchParams()
      body.set('quantity', String(1))
      if (productId !== undefined) {
        body.set('product_id', String(productId))
      }
      if (productType) {
        body.set('product_type', productType)
      }
      if (productSlug) {
        body.set('product_slug', productSlug)
      }
      try {
        await api.post('/orders/cart/add', body, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
      } catch (e: any) {
        await api.post('/orders/cart/add/', body, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
      }
      await refresh()
      setDone(true)
      setTimeout(()=>setDone(false), 1500)
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Ошибка добавления в корзину'
      // Быстрый видимый фидбек пользователю
      alert(String(detail))
      // И лог для диагностики
      // eslint-disable-next-line no-console
      console.error('AddToCart error', err?.response?.status, err?.response?.data)
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={add}
      disabled={loading}
      className={
        `inline-flex items-center rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-60 ${className || ''}`
      }
    >
      {done ? t('added', 'Добавлено') : (loading ? t('adding', 'Добавляем...') : (label || t('add_to_cart', 'В корзину')))}
    </button>
  )
}
