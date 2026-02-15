import Head from 'next/head'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import Link from 'next/link'
import api from '../lib/api'
import { useEffect, useState, useCallback } from 'react'
import { useCartStore } from '../store/cart'
import { resolveMediaUrl, getPlaceholderImageUrl, isVideoUrl } from '../lib/media'
import { needsTypeInPath } from '../lib/product'

interface CartItem {
  id: number
  product: number
  product_name?: string
  product_slug?: string
  product_type?: string
  product_image_url?: string
  product_video_url?: string | null
  chosen_size?: string
  quantity: number
  price: string
  currency: string
  old_price?: string | number | null
  old_price_formatted?: string | null
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

const parseNumber = (value: string | number | null | undefined) => {
  if (value === null || typeof value === 'undefined') return null
  const normalized = String(value).replace(',', '.').replace(/[^0-9.]/g, '')
  if (!normalized) return null
  const num = Number(normalized)
  return Number.isFinite(num) ? num : null
}

export default function CartPage({ initialCart }: { initialCart: Cart }) {
  const { t } = useTranslation('common')
  const [cart, setCart] = useState<Cart>({
    ...initialCart,
    items: initialCart.items || []
  })
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cart.items_count, mounted])

  // Клиентское обновление корзины после монтирования (только один раз)
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
            const prevItems = prevCart.items || []
            const newItems = r.data.items || []
            const hasChanged = 
              prevCart.items_count !== r.data.items_count ||
              prevItems.length !== newItems.length ||
              prevCart.total_amount !== r.data.total_amount ||
              prevCart.discount_amount !== r.data.discount_amount ||
              prevCart.final_amount !== r.data.final_amount ||
              (prevCart.promo_code?.code || null) !== (r.data.promo_code?.code || null)
            
            if (hasChanged) {
              return {
                ...r.data,
                items: r.data.items || []
              }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted])

  const refreshCart = useCallback(async () => {
    try {
      const r = await api.get('/orders/cart')
      if (r.data) {
        let shouldUpdateCount = false
        setCart(prevCart => {
          const prevItems = prevCart.items || []
          const newItems = r.data.items || []
          
          // Сохраняем порядок товаров из предыдущего состояния
          const prevItemOrder = new Map(prevItems.map((item, index) => [item.id, index]))
          
          // Сортируем новые товары по старому порядку
          const sortedItems = [...newItems].sort((a, b) => {
            const aIndex = prevItemOrder.get(a.id) ?? Infinity
            const bIndex = prevItemOrder.get(b.id) ?? Infinity
            return aIndex - bIndex
          })
          
          // Обновляем только если данные изменились
          const hasChanged = 
            prevCart.items_count !== r.data.items_count ||
            prevCart.total_amount !== r.data.total_amount ||
            prevCart.discount_amount !== r.data.discount_amount ||
            prevCart.final_amount !== r.data.final_amount ||
            (prevCart.promo_code?.code || null) !== (r.data.promo_code?.code || null) ||
            prevItems.length !== newItems.length ||
            JSON.stringify(prevItems.map(i => ({ id: i.id, quantity: i.quantity }))) !== 
            JSON.stringify(newItems.map((i: CartItem) => ({ id: i.id, quantity: i.quantity })))
          
          if (hasChanged && prevCart.items_count !== r.data.items_count) {
            shouldUpdateCount = true
          }
          
          if (hasChanged) {
            return { ...r.data, items: sortedItems }
          }
          return prevCart
        })
        // Обновляем счетчик только если он изменился
        if (shouldUpdateCount) {
          setItemsCount(r.data.items_count)
        }
      }
    } catch (error) {
      console.error('Failed to refresh cart:', error)
    }
  }, [setItemsCount])

  const updateQty = async (itemId: number, qty: number) => {
    if (qty < 1) return
    setLoading(true)
    // Оптимистичное обновление - обновляем количество сразу
    setCart(prevCart => ({
      ...prevCart,
      items: (prevCart.items || []).map(item => 
        item.id === itemId ? { ...item, quantity: qty } : item
      )
    }))
    try {
      await api.post(`/orders/cart/${itemId}/update`, { quantity: qty })
      await refreshCart()
    } catch (error) {
      console.error('Failed to update quantity:', error)
      // В случае ошибки обновляем корзину с сервера
      await refreshCart()
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
      const data = error?.response?.data
      const errorMessage =
        (typeof data?.detail === 'string' && data.detail) ||
        (Array.isArray(data?.code) && data.code[0]) ||
        t('promo_code_error', 'Ошибка применения промокода')
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

  const getProductLink = (slug?: string, productId?: number, productType?: string) => {
    if (slug) {
      if (productType && needsTypeInPath(productType)) {
        return `/product/${productType}/${slug}`
      }
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
          <h1 className="text-3xl font-bold text-main">{t('menu_cart', 'Корзина')}</h1>
          {cart.items_count > 0 && (
            <p className="mt-2 text-sm text-main">
              {cart.items_count} {cart.items_count === 1 ? 'товар' : cart.items_count < 5 ? 'товара' : 'товаров'}
            </p>
          )}
        </div>

        {(!cart.items || cart.items.length === 0) ? (
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
                className="inline-block rounded-md bg-[var(--accent)] px-6 py-3 text-sm font-medium text-white hover:bg-[var(--accent-strong)] transition-colors"
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
                {(cart.items || []).map((item) => {
                  const oldPriceSource = item.old_price_formatted ?? item.old_price
                  const priceValue = parseNumber(item.price)
                  const oldPriceValue = parseNumber(oldPriceSource)
                  const discountPercent = priceValue !== null && oldPriceValue !== null && oldPriceValue > priceValue && oldPriceValue > 0
                    ? Math.round(((oldPriceValue - priceValue) / oldPriceValue) * 100)
                    : null
                  const resolvedImage = item.product_image_url
                    ? resolveMediaUrl(item.product_image_url)
                    : null
                  const resolvedVideoUrl = item.product_video_url && isVideoUrl(item.product_video_url)
                    ? resolveMediaUrl(item.product_video_url)
                    : null
                  const showVideo = Boolean(resolvedVideoUrl)
                  return (
                    <div
                      key={item.id}
                      className="group flex flex-col sm:flex-row gap-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm hover:shadow-md transition-all duration-200"
                    >
                    {/* Главное медиа товара (видео или изображение) */}
                    <Link
                      href={getProductLink(item.product_slug, item.product, item.product_type)}
                      className="relative w-full sm:w-32 h-32 flex-shrink-0 overflow-hidden rounded-lg bg-gray-100"
                    >
                      {showVideo ? (
                        <video
                          src={resolvedVideoUrl!}
                          poster={resolvedImage || undefined}
                          muted
                          loop
                          playsInline
                          autoPlay
                          preload="metadata"
                          className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105"
                        />
                      ) : resolvedImage ? (
                        <img
                          src={resolvedImage}
                          alt={item.product_name || `Товар #${item.product}`}
                          className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105"
                          onError={(e) => {
                            e.currentTarget.src = getPlaceholderImageUrl({
                              type: 'product',
                              id: item.product || item.id,
                            })
                          }}
                        />
                      ) : (
                        <img
                          src={getPlaceholderImageUrl({
                            type: 'product',
                            id: item.product || item.id,
                          })}
                          alt="No image"
                          className="h-full w-full object-cover"
                          onError={(e) => {
                            e.currentTarget.src = '/product-placeholder.svg'
                          }}
                        />
                      )}
                    </Link>

                    {/* Информация о товаре */}
                    <div className="flex-1 flex flex-col justify-between">
                      <div>
                        <Link
                          href={getProductLink(item.product_slug, item.product, item.product_type)}
                          className="block"
                        >
                          <h3 className="text-lg font-semibold text-gray-900 hover-text-warm transition-colors line-clamp-2">
                            {item.product_name || `Товар #${item.product}`}
                          </h3>
                        </Link>
                        {item.chosen_size ? (
                          <div className="mt-1 text-sm text-gray-600">
                            {t('size', 'Размер')}: <span className="font-medium text-gray-900">{item.chosen_size}</span>
                          </div>
                        ) : null}
                        <div className="mt-1 text-lg font-bold text-red-600">
                          {item.price} {item.currency}
                        </div>
                        {(item.old_price_formatted || item.old_price) && (
                          <div className="flex items-baseline gap-2">
                            <div className="text-sm text-gray-400 line-through">
                              {item.old_price_formatted || `${item.old_price} ${item.currency}`}
                            </div>
                            {discountPercent !== null && (
                              <div className="text-sm font-semibold !text-red-600">-{discountPercent}%</div>
                            )}
                          </div>
                        )}
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
                            className="rounded-md p-2 text-gray-400 transition-colors hover:bg-[var(--accent-soft)] hover:text-[var(--accent)] disabled:opacity-50"
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
                )
                })}
              </div>

              {/* Кнопка очистки корзины */}
              <div className="mt-6">
                <button
                  onClick={clearCart}
                  disabled={loading}
                  className="text-sm text-main hover-text-warm transition-colors disabled:opacity-50"
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
                    <div className="rounded-lg bg-red-50 p-3 border border-red-200">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-medium !text-red-700">
                            {t('promo_code_applied', 'Промокод применён')}: {cart.promo_code.code}
                          </div>
                          <div className="text-xs !text-red-600 mt-1">
                            {cart.promo_code.discount_type === 'percent' 
                              ? `${cart.promo_code.discount_value}%`
                              : `${cart.promo_code.discount_value} ${cart.currency || 'USD'}`}
                          </div>
                        </div>
                        <button
                          onClick={removePromoCode}
                          disabled={promoLoading}
                          className="!text-red-600 hover:!text-red-700 text-sm font-medium disabled:opacity-50"
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
                          className="flex-1 min-w-0 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
                        />
                        <button
                          onClick={applyPromoCode}
                          disabled={promoLoading || !promoCode.trim()}
                          className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white hover:bg-[var(--accent-strong)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0 whitespace-nowrap"
                        >
                          {promoLoading ? t('applying', 'Применение...') : t('apply', 'Применить')}
                        </button>
                      </div>
                      {promoError && (
                        <div className="text-sm text-[var(--text-strong)]">{promoError}</div>
                      )}
                    </div>
                  )}
                </div>

                <div className="space-y-4">
                  <div className="flex justify-between text-sm text-main">
                    <span>{t('cart_items_count', 'Товаров')}</span>
                    <span className="font-medium text-main">{cart.items_count}</span>
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
                    <div className="flex justify-between text-sm !text-red-600">
                      <span>{t('cart_discount', 'Скидка')}</span>
                      <span className="font-medium">
                        -{cart.discount_amount} {cart.currency || 'USD'}
                      </span>
                    </div>
                  )}
                  <div className="border-t border-gray-200 pt-4">
                    <div className="flex justify-between items-baseline">
                      <span className="text-lg font-semibold text-gray-900">{t('cart_total', 'Итого')}</span>
                      <span className="text-2xl font-bold text-[var(--text-strong)]">
                        {cart.final_amount || cart.total_amount} {cart.currency || 'USD'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="mt-6 space-y-3">
                  <Link
                    href="/checkout"
                    className="block w-full rounded-md bg-[var(--accent)] px-6 py-3 text-center text-sm font-medium text-white hover:bg-[var(--accent-strong)] transition-colors"
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
                <div className="mt-6 rounded-lg bg-[var(--surface)] p-4">
                  <div className="flex items-start gap-2">
                    <svg className="h-5 w-5 text-[var(--accent)] mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <div className="text-xs text-main">
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
    const { getInternalApiUrl } = await import('../lib/urls')
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

    const currencyMatch = cookieHeader.match(/(?:^|;\s*)currency=([^;]+)/)
    const currency = currencyMatch ? currencyMatch[1] : 'RUB'

    const apiRes = await fetch(getInternalApiUrl('orders/cart'), {
      headers: {
        cookie: cookieHeader,
        'Accept-Language': locale || 'en',
        ...(cartSession ? { 'X-Cart-Session': cartSession } : {}),
        ...(accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {}),
        'X-Currency': currency
      }
    })
    const data = await apiRes.json()
    return { 
      props: { 
        ...(await serverSideTranslations(locale || 'en', ['common'])), 
        initialCart: {
          ...data,
          items: data.items || []
        }
      } 
    }
  } catch (e) {
    return { 
      props: { 
        ...(await serverSideTranslations(locale || 'en', ['common'])), 
        initialCart: { 
          id: 0, 
          items: [], 
          items_count: 0, 
          total_amount: '0.00' 
        } 
      } 
    }
  }
}
