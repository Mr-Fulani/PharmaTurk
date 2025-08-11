import Head from 'next/head'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import api from '../lib/api'
import { useAuth } from '../context/AuthContext'

interface OrderItem { id: number; product_name: string; price: string; quantity: number; total: string }
interface Order { id: number; number: string; total_amount: string; currency: string; items: OrderItem[] }

export default function ProfilePage() {
  const router = useRouter()
  const { user, loading } = useAuth()
  const [orders, setOrders] = useState<Order[]>([])

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/auth/login?next=/profile')
      return
    }
    if (user) {
      api.get('/orders/orders/').then((r) => {
        setOrders(r.data || [])
      }).catch(() => {})
    }
  }, [user, loading, router])

  return (
    <>
      <Head><title>Профиль — Turk-Export</title></Head>
      <main style={{ maxWidth: 960, margin: '0 auto', padding: 24 }}>
        <h1>Профиль</h1>
        {user ? (
          <>
            <h2 style={{ marginTop: 16 }}>Мои заказы</h2>
            {orders.length === 0 ? (
              <div>Пока нет заказов</div>
            ) : (
              <div style={{ display: 'grid', gap: 12 }}>
                {orders.map((o) => (
                  <div key={o.id} style={{ border: '1px solid #eee', borderRadius: 8, padding: 12 }}>
                    <div style={{ fontWeight: 600 }}>Заказ {o.number}</div>
                    <div style={{ color: '#666' }}>Сумма: {o.total_amount} {o.currency}</div>
                    <div style={{ marginTop: 8 }}>
                      {o.items.map((it) => (
                        <div key={it.id} style={{ fontSize: 14, color: '#444' }}>
                          {it.product_name}: {it.quantity} × {it.price} = {it.total}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : null}
      </main>
    </>
  )
}


