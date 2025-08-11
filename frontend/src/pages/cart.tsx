import Head from 'next/head'
import api from '../lib/api'

interface CartItem {
  id: number
  product: number
  product_name?: string
  product_slug?: string
  quantity: number
  price: string
  currency: string
}

interface Cart {
  id: number
  items: CartItem[]
  items_count: number
  total_amount: string
  currency?: string
}

import { useEffect, useState } from 'react'
import { useCartStore } from '../store/cart'

export default function CartPage({ initialCart }: { initialCart: Cart }) {
  const [cart, setCart] = useState<Cart>(initialCart)
  const { setItemsCount } = useCartStore()

  useEffect(() => { setItemsCount(cart.items_count) }, [cart.items_count, setItemsCount])

  // Клиентское обновление корзины после монтирования (чтобы отразить результат клика по кнопке на предыдущей странице)
  useEffect(() => {
    (async () => {
      try {
        const r = await api.get('/orders/cart/')
        setCart(r.data)
      } catch {}
    })()
  }, [])

  const updateQty = async (itemId: number, qty: number) => {
    await api.post(`/orders/cart/${itemId}/update/`, { quantity: qty })
    const r = await api.get('/orders/cart/')
    setCart(r.data)
  }

  const removeItem = async (itemId: number) => {
    await api.delete(`/orders/cart/${itemId}/remove/`)
    const r = await api.get('/orders/cart/')
    setCart(r.data)
  }
  return (
    <>
      <Head>
        <title>Корзина — Turk-Export</title>
      </Head>
      <main style={{ maxWidth: 960, margin: '0 auto', padding: 24 }}>
        <h1>Корзина</h1>
        {cart.items.length === 0 ? (
          <div>Корзина пуста</div>
        ) : (
          <div style={{ display: 'grid', gap: 12 }}>
            {cart.items.map((i) => (
              <div key={i.id} style={{ border: '1px solid #eee', borderRadius: 8, padding: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{i.product_name || `Товар #${i.product}`}</div>
                  <div style={{ color: '#666' }}>{i.price} {i.currency} × {i.quantity}</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button onClick={()=>updateQty(i.id, Math.max(1, i.quantity - 1))}>-</button>
                  <span>{i.quantity}</span>
                  <button onClick={()=>updateQty(i.id, i.quantity + 1)}>+</button>
                  <button onClick={()=>removeItem(i.id)} style={{ marginLeft: 8 }}>Удалить</button>
                </div>
              </div>
            ))}
            <div style={{ textAlign: 'right', fontWeight: 700 }}>Итого: {cart.total_amount}</div>
          </div>
        )}
      </main>
      <div style={{ maxWidth: 960, margin: '0 auto', padding: '0 24px 24px' }}>
        <a href="/checkout" style={{ display: 'inline-block', marginTop: 12, border: '1px solid #ddd', padding: '8px 14px', borderRadius: 8, textDecoration: 'none' }}>
          Перейти к оформлению заказа
        </a>
      </div>
    </>
  )
}

export async function getServerSideProps({ req, res: serverRes }: any) {
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    // Извлекаем cart_session из cookies
    const cookieHeader: string = req.headers.cookie || ''
    const cartSessionMatch = cookieHeader.match(/(?:^|;\s*)cart_session=([^;]+)/)
    let cartSession = cartSessionMatch ? cartSessionMatch[1] : ''
    // Извлекаем access токен для авторизации на сервере (если пользователь залогинен)
    const accessMatch = cookieHeader.match(/(?:^|;\s*)access=([^;]+)/)
    const accessToken = accessMatch ? accessMatch[1] : ''

    // Если cart_session отсутствует, создаём и устанавливаем cookie для клиента
    if (!cartSession) {
      cartSession = Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2)
      if (serverRes && typeof serverRes.setHeader === 'function') {
        serverRes.setHeader('Set-Cookie', `cart_session=${cartSession}; Path=/; SameSite=Lax`)
      }
    }

    const apiRes = await fetch(`${base}/api/orders/cart/`, {
      headers: {
        // Прокидываем исходные cookies
        cookie: cookieHeader,
        // И явный ключ корзины для анонимных пользователей
        ...(cartSession ? { 'X-Cart-Session': cartSession } : {}),
        // Авторизация по access токену, если он есть в cookies
        ...(accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {})
      }
    })
    const data = await apiRes.json()
    return { props: { initialCart: data } }
  } catch (e) {
    return { props: { initialCart: { id: 0, items: [], items_count: 0, total_amount: '0.00' } } }
  }
}
