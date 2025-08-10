import { useState } from 'react'
import api, { initCartSession } from '../lib/api'
import { useCartStore } from '../store/cart'

export default function AddToCartButton({ productId }: { productId: number }) {
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
      await api.post('/orders/cart/add/', body, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
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
    <button onClick={add} disabled={loading} style={{ marginTop: 8 }}>
      {done ? 'Добавлено' : (loading ? 'Добавляем...' : 'В корзину')}
    </button>
  )
}
