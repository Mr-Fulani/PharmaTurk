import { useState } from 'react'
import api from '../lib/api'

export default function AddToCartButton({ productId }: { productId: number }) {
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)

  const add = async () => {
    setLoading(true)
    try {
      await api.post('/orders/cart/add/', { product_id: productId, quantity: 1 })
      setDone(true)
      setTimeout(()=>setDone(false), 1500)
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
