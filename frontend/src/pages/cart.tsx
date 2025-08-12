import Head from 'next/head'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
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
  const { t } = useTranslation('common')
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
        <title>{t('menu_cart', 'Корзина')} — Turk-Export</title>
      </Head>
      <main className="mx-auto max-w-6xl p-6">
        <h1 className="text-2xl font-bold">{t('menu_cart', 'Корзина')}</h1>
        {cart.items.length === 0 ? (
          <div className="mt-6 rounded-lg border border-dashed border-gray-300 p-8 text-center text-gray-600">{t('cart_empty', 'Корзина пуста')}</div>
        ) : (
          <div className="mt-6 grid gap-3">
            {cart.items.map((i) => (
              <div key={i.id} className="flex items-center justify-between rounded-xl border border-gray-200 bg-white p-4">
                <div>
                  <div className="font-semibold text-gray-900">{i.product_name || `Товар #${i.product}`}</div>
                  <div className="text-sm text-gray-600">{i.price} {i.currency} × {i.quantity}</div>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={()=>updateQty(i.id, Math.max(1, i.quantity - 1))} className="rounded-md border border-gray-300 px-2 py-1">-</button>
                  <span className="w-6 text-center">{i.quantity}</span>
                  <button onClick={()=>updateQty(i.id, i.quantity + 1)} className="rounded-md border border-gray-300 px-2 py-1">+</button>
                  <button onClick={()=>removeItem(i.id)} className="ml-2 rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-800 hover:bg-gray-50">{t('remove', 'Удалить')}</button>
                </div>
              </div>
            ))}
            <div className="text-right text-lg font-bold">{t('cart_total', 'Итого')}: {cart.total_amount}</div>
          </div>
        )}
        <div className="mt-4">
          <a href="/checkout" className="inline-block rounded-md bg-gray-900 px-4 py-2 text-white hover:bg-black">{t('cart_checkout', 'Перейти к оформлению заказа')}</a>
        </div>
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  const { req, res: serverRes, locale } = ctx
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
        // Для локализации ответов бэка
        'Accept-Language': locale || 'en',
        // И явный ключ корзины для анонимных пользователей
        ...(cartSession ? { 'X-Cart-Session': cartSession } : {}),
        // Авторизация по access токену, если он есть в cookies
        ...(accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {})
      }
    })
    const data = await apiRes.json()
    return { props: { ...(await serverSideTranslations(locale || 'en', ['common'])), initialCart: data } }
  } catch (e) {
    return { props: { ...(await serverSideTranslations(locale || 'en', ['common'])), initialCart: { id: 0, items: [], items_count: 0, total_amount: '0.00' } } }
  }
}
