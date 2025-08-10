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

export default function CartPage({ initialCart }: { initialCart: Cart }) {
  const cart = initialCart
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
              <div key={i.id} style={{ border: '1px solid #eee', borderRadius: 8, padding: 12, display: 'flex', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{i.product_name || `Товар #${i.product}`}</div>
                  <div style={{ color: '#666' }}>{i.price} {i.currency} × {i.quantity}</div>
                </div>
              </div>
            ))}
            <div style={{ textAlign: 'right', fontWeight: 700 }}>Итого: {cart.total_amount}</div>
          </div>
        )}
      </main>
    </>
  )
}

export async function getServerSideProps({ req }: any) {
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    const res = await fetch(`${base}/api/orders/cart/`)
    const data = await res.json()
    return { props: { initialCart: data } }
  } catch (e) {
    return { props: { initialCart: { id: 0, items: [], items_count: 0, total_amount: '0.00' } } }
  }
}
