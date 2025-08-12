import { useState } from 'react'
import api, { initCartSession } from '../lib/api'
import { useCartStore } from '../store/cart'

export default function AddToCartButton({ productId, className, label }: { productId: number, className?: string, label?: string }) {
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const { refresh } = useCartStore()

  const add = async () => {
    setLoading(true)
    try {
      initCartSession()
      const body = new URLSearchParams()
      body.set('product_id', String(productId))
      body.set('quantity', String(1))
      try {
        await api.post('/orders/cart/add', body, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
      } catch (e: any) {
        // fallback на вариант со слэшем, если роут сконфигурирован иначе
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
      {done ? 'Добавлено' : (loading ? 'Добавляем...' : (label || 'В корзину'))}
    </button>
  )
}
