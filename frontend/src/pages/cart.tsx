import Head from 'next/head'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import Link from 'next/link'
import api from '../lib/api'
import { useEffect, useState } from 'react'
import { useCartStore } from '../store/cart'

interface CartItem {
  id: number
  product: number
  product_name?: string
  product_slug?: string
  product_image_url?: string
  quantity: number
  price: string
  currency: string
}

interface PromoCode {
  id: number
  code: string
  discount_type?: string
  discount_value: string
  description?: string
}

interface Cart {
  id: number
  items: CartItem[]
  items_count: number
  total_amount: string
  discount_amount?: string
  final_amount?: string
  currency?: string
  promo_code?: PromoCode | null
}

export default function CartPage({ initialCart }: { initialCart: Cart }) {
  const { t } = useTranslation('common')
  const [cart, setCart] = useState<Cart>(initialCart)
  const [loading, setLoading] = useState(false)
  const [mounted, setMounted] = useState(false)
  const [promoCode, setPromoCode] = useState('')
  const [promoLoading, setPromoLoading] = useState(false)
  const [promoError, setPromoError] = useState<string | null>(null)
  const { setItemsCount } = useCartStore()

  useEffect(() => {
    setMounted(true)
  }, [])

  // Обновляем счетчик товаров при изменении корзины
  useEffect(() => {
    if (mounted) {
      setItemsCount(cart.items_count)
    }
  }, [cart.items_count, setItemsCount, mounted])

  // Клиентское обновление корзины после монтирования (только если данные изменились)
  useEffect(() => {
    if (!mounted) return
    let cancelled = false
    
    const updateCart = async () => {
      try {
        const r = await api.get('/orders/cart')
        if (!cancelled && r.data) {
          // Обновляем только если данные действительно изменились
          setCart(prevCart => {
            // Сравниваем только ключевые поля для избежания лишних обновлений
            if (
              prevCart.items_count !== r.data.items_count ||
              prevCart.items.length !== r.data.items.length ||
              prevCart.total_amount !== r.data.total_amount
            ) {
              return r.data
            }
            return prevCart
          })
        }
      } catch (error) {
        // Тихий игнор ошибок при первичной загрузке
      }
    }
    
    // Задержка для избежания мерцания при первой загрузке
    const timeout = setTimeout(updateCart, 200)
    
    return () => {
      cancelled = true
      clearTimeout(timeout)
    }
  }, [mounted])

  const refreshCart = async () => {
    try {
      const r = await api.get('/orders/cart')
      if (r.data) {
        setCart(prevCart => {
          // Обновляем только если данные изменились
          if (
            prevCart.items_count !== r.data.items_count ||
            prevCart.total_amount !== r.data.total_amount ||
            JSON.stringify(prevCart.items) !== JSON.stringify(r.data.items)
          ) {
            return r.data
          }
          return prevCart
        })
        setItemsCount(r.data.items_count)
      }
    } catch (error) {
      console.error('Failed to refresh cart:', error)
    }
  }

  const updateQty = async (itemId: number, qty: number) => {
    if (qty < 1) return
    setLoading(true)
    try {
      await api.post(`/orders/cart/${itemId}/update`, { quantity: qty })
      await refreshCart()
    } catch (error) {
      console.error('Failed to update quantity:', error)
    } finally {
      setLoading(false)
    }
  }

  const removeItem = async (itemId: number) => {
    if (!confirm(t('cart_confirm_remove', 'Вы уверены, что хотите удалить этот товар из корзины?'))) {
      return
    }
    setLoading(true)
    try {
      await api.delete(`/orders/cart/${itemId}/remove`)
      await refreshCart()
    } catch (error) {
      console.error('Failed to remove item:', error)
    } finally {
      setLoading(false)
    }
  }

  const clearCart = async () => {
    if (!confirm(t('cart_confirm_clear', 'Вы уверены, что хотите очистить корзину?'))) {
      return
    }
    setLoading(true)
    try {
      await api.post('/orders/cart/clear')
      await refreshCart()
    } catch (error) {
      console.error('Failed to clear cart:', error)
    } finally {
      setLoading(false)
    }
  }

  const applyPromoCode = async () => {
    if (!promoCode.trim()) return
    setPromoLoading(true)
    setPromoError(null)
    try {
      await api.post('/orders/cart/apply-promo', { code: promoCode.trim().toUpperCase() })
      setPromoCode('')
      await refreshCart()
    } catch (error: any) {
      const errorMessage = error?.response?.data?.detail || t('promo_code_error', 'Ошибка применения промокода')
      setPromoError(errorMessage)
    } finally {
      setPromoLoading(false)
    }
  }

  const removePromoCode = async () => {
    setPromoLoading(true)
    setPromoError(null)
    try {
      await api.post('/orders/cart/remove-promo')
      await refreshCart()
    } catch (error) {
      console.error('Failed to remove promo code:', error)
    } finally {
      setPromoLoading(false)
    }
  }

  const getProductLink = (slug?: string, productId?: number) => {
    if (slug) {
      return `/product/${slug}`
    }
    return `#`
  }

  return (
    <>
      <Head>
        <title>{t('menu_cart', 'Корзина')} — Turk-Export</title>
      </Head>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">{t('menu_cart', 'Корзина')}</h1>
          {cart.items_count > 0 && (
            <p className="mt-2 text-sm text-gray-600">
              {cart.items_count} {cart.items_count === 1 ? 'товар' : cart.items_count < 5 ? 'товара' : 'товаров'}
            </p>
          )}
        </div>

        {cart.items.length === 0 ? (
          <div className="rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-12 text-center">
            <svg
              className="mx-auto h-16 w-16 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"
              />
            </svg>
            <h3 className="mt-4 text-lg font-semibold text-gray-900">{t('cart_empty', 'Корзина пуста')}</h3>
            <p className="mt-2 text-sm text-gray-600">
              {t('cart_empty_description', 'Добавьте товары в корзину, чтобы продолжить покупки')}
            </p>
            <div className="mt-6">
              <Link
                href="/"
                className="inline-block rounded-md bg-violet-600 px-6 py-3 text-sm font-medium text-white hover:bg-violet-700 transition-colors"
              >
                {t('cart_continue_shopping', 'Продолжить покупки')}
              </Link>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
            {/* Список товаров */}
            <div className="lg:col-span-2">
              <div className="space-y-4">
                {cart.items.map((item) => (
                  <div
                    key={item.id}
                    className="group flex flex-col sm:flex-row gap-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm hover:shadow-md transition-all duration-200"
                  >
                    {/* Изображение товара */}
                    <Link
                      href={getProductLink(item.product_slug, item.product)}
                      className="relative w-full sm:w-32 h-32 flex-shrink-0 overflow-hidden rounded-lg bg-gray-100"
                    >
                      {item.product_image_url ? (
                        <img
                          src={item.product_image_url}
                          alt={item.product_name || `Товар #${item.product}`}
                          className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105"
                        />
                      ) : (
                        <img
                          src="/product-placeholder.svg"
                          alt="No image"
                          className="h-full w-full object-cover"
                        />
                      )}
                    </Link>

                    {/* Информация о товаре */}
                    <div className="flex-1 flex flex-col justify-between">
                      <div>
                        <Link
                          href={getProductLink(item.product_slug, item.product)}
                          className="block"
                        >
                          <h3 className="text-lg font-semibold text-gray-900 hover:text-violet-600 transition-colors line-clamp-2">
                            {item.product_name || `Товар #${item.product}`}
                          </h3>
                        </Link>
                        <div className="mt-1 text-lg font-bold text-violet-600">
                          {item.price} {item.currency}
                        </div>
                      </div>

                      {/* Управление количеством и удалением */}
                      <div className="mt-4 flex items-center justify-between gap-4">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => updateQty(item.id, item.quantity - 1)}
                            disabled={loading || item.quantity <= 1}
                            className="flex h-9 w-9 items-center justify-center rounded-md border border-gray-300 bg-white text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                            aria-label="Уменьшить количество"
                          >
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
                            </svg>
                          </button>
                          <span className="min-w-[3rem] text-center text-base font-medium text-gray-900">
                            {item.quantity}
                          </span>
                          <button
                            onClick={() => updateQty(item.id, item.quantity + 1)}
                            disabled={loading}
                            className="flex h-9 w-9 items-center justify-center rounded-md border border-gray-300 bg-white text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                            aria-label="Увеличить количество"
                          >
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                            </svg>
                          </button>
                        </div>

                        <div className="flex items-center gap-3">
                          <div className="text-right">
                            <div className="text-sm text-gray-500">{t('cart_item_total', 'Итого')}</div>
                            <div className="text-lg font-bold text-gray-900">
                              {(parseFloat(item.price) * item.quantity).toFixed(2)} {item.currency}
                            </div>
                          </div>
                          <button
                            onClick={() => removeItem(item.id)}
                            disabled={loading}
                            className="rounded-md p-2 text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                            aria-label={t('remove', 'Удалить')}
                          >
                            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                              />
                            </svg>
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Кнопка очистки корзины */}
              <div className="mt-6">
                <button
                  onClick={clearCart}
                  disabled={loading}
                  className="text-sm text-gray-600 hover:text-red-600 transition-colors disabled:opacity-50"
                >
                  {t('cart_clear', 'Очистить корзину')}
                </button>
              </div>
            </div>

            {/* Итоговая информация */}
            <div className="lg:col-span-1">
              <div className="sticky top-20 rounded-xl border border-gray-200 bg-white p-6 shadow-sm z-10">
                <h2 className="text-xl font-bold text-gray-900 mb-4">{t('cart_summary', 'Итоги заказа')}</h2>

                {/* Промокод */}
                <div className="mb-4">
                  {cart.promo_code ? (
                    <div className="rounded-lg bg-green-50 p-3 border border-green-200">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-medium text-green-800">
                            {t('promo_code_applied', 'Промокод применён')}: {cart.promo_code.code}
                          </div>
                          <div className="text-xs text-green-600 mt-1">
                            {cart.promo_code.discount_type === 'percent' 
                              ? `${cart.promo_code.discount_value}%`
                              : `${cart.promo_code.discount_value} ${cart.currency || 'USD'}`}
                          </div>
                        </div>
                        <button
                          onClick={removePromoCode}
                          disabled={promoLoading}
                          className="text-green-600 hover:text-green-800 text-sm font-medium disabled:opacity-50"
                        >
                          {t('remove', 'Удалить')}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={promoCode}
                          onChange={(e) => {
                            setPromoCode(e.target.value.toUpperCase())
                            setPromoError(null)
                          }}
                          onKeyPress={(e) => e.key === 'Enter' && applyPromoCode()}
                          placeholder={t('promo_code_placeholder', 'Промокод')}
                          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
                        />
                        <button
                          onClick={applyPromoCode}
                          disabled={promoLoading || !promoCode.trim()}
                          className="rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {promoLoading ? t('applying', 'Применение...') : t('apply', 'Применить')}
                        </button>
                      </div>
                      {promoError && (
                        <div className="text-sm text-red-600">{promoError}</div>
                      )}
                    </div>
                  )}
                </div>

                <div className="space-y-4">
                  <div className="flex justify-between text-sm text-gray-600">
                    <span>{t('cart_items_count', 'Товаров')}</span>
                    <span className="font-medium text-gray-900">{cart.items_count}</span>
                  </div>
                  {cart.discount_amount && parseFloat(cart.discount_amount) > 0 && (
                    <div className="flex justify-between text-sm text-gray-600">
                      <span>{t('cart_subtotal', 'Сумма товаров')}</span>
                      <span className="font-medium text-gray-900">
                        {cart.total_amount} {cart.currency || 'USD'}
                      </span>
                    </div>
                  )}
                  {cart.discount_amount && parseFloat(cart.discount_amount) > 0 && (
                    <div className="flex justify-between text-sm text-green-600">
                      <span>{t('cart_discount', 'Скидка')}</span>
                      <span className="font-medium">
                        -{cart.discount_amount} {cart.currency || 'USD'}
                      </span>
                    </div>
                  )}
                  <div className="border-t border-gray-200 pt-4">
                    <div className="flex justify-between items-baseline">
                      <span className="text-lg font-semibold text-gray-900">{t('cart_total', 'Итого')}</span>
                      <span className="text-2xl font-bold text-violet-600">
                        {cart.final_amount || cart.total_amount} {cart.currency || 'USD'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="mt-6 space-y-3">
                  <Link
                    href="/checkout"
                    className="block w-full rounded-md bg-violet-600 px-6 py-3 text-center text-sm font-medium text-white hover:bg-violet-700 transition-colors"
                  >
                    {t('cart_checkout', 'Перейти к оформлению заказа')}
                  </Link>
                  <Link
                    href="/"
                    className="block w-full rounded-md border border-gray-300 px-6 py-3 text-center text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                  >
                    {t('cart_continue_shopping', 'Продолжить покупки')}
                  </Link>
                </div>

                {/* Информация о доставке */}
                <div className="mt-6 rounded-lg bg-violet-50 p-4">
                  <div className="flex items-start gap-2">
                    <svg className="h-5 w-5 text-violet-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <div className="text-xs text-violet-800">
                      <p className="font-medium">{t('cart_delivery_info_title', 'Бесплатная доставка')}</p>
                      <p className="mt-1">{t('cart_delivery_info_text', 'При заказе от определенной суммы')}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  const { req, res: serverRes, locale } = ctx
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    const cookieHeader: string = req.headers.cookie || ''
    const cartSessionMatch = cookieHeader.match(/(?:^|;\s*)cart_session=([^;]+)/)
    let cartSession = cartSessionMatch ? cartSessionMatch[1] : ''
    const accessMatch = cookieHeader.match(/(?:^|;\s*)access=([^;]+)/)
    const accessToken = accessMatch ? accessMatch[1] : ''

    if (!cartSession) {
      cartSession = Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2)
      if (serverRes && typeof serverRes.setHeader === 'function') {
        serverRes.setHeader('Set-Cookie', `cart_session=${cartSession}; Path=/; SameSite=Lax`)
      }
    }

    const apiRes = await fetch(`${base}/api/orders/cart`, {
      headers: {
        cookie: cookieHeader,
        'Accept-Language': locale || 'en',
        ...(cartSession ? { 'X-Cart-Session': cartSession } : {}),
        ...(accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {})
      }
    })
    const data = await apiRes.json()
    return { props: { ...(await serverSideTranslations(locale || 'en', ['common'])), initialCart: data } }
  } catch (e) {
    return { props: { ...(await serverSideTranslations(locale || 'en', ['common'])), initialCart: { id: 0, items: [], items_count: 0, total_amount: '0.00' } } }
  }
}
