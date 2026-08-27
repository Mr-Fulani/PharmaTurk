import { useState } from 'react'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import api, { initCartSession } from '../lib/api'
import { getCartIssueCopy, getCartVerificationError } from '../lib/cartVerification'
import { useCartStore } from '../store/cart'
import { isBaseProductType } from '../lib/product'

interface BuyNowButtonProps {
  productId?: number
  productType?: string
  productSlug?: string
  size?: string
  requireSize?: boolean
  className?: string
  quantity?: number
}

/**
 * Кнопка "Купить в один клик" - добавляет товар в корзину и перенаправляет на checkout
 */
export default function BuyNowButton({
  productId,
  productType = 'medicines',
  productSlug,
  size,
  requireSize = false,
  className,
  quantity = 1
}: BuyNowButtonProps) {
  const [loading, setLoading] = useState(false)
  const router = useRouter()
  const { refresh, setCartSummary } = useCartStore()
  const { t } = useTranslation('common')

  const buyNow = async () => {
    setLoading(true)
    try {
      if (requireSize && !size) {
        alert(t('select_size', 'Выберите размер'))
        setLoading(false)
        return
      }
      initCartSession()
      const body = new URLSearchParams()
      body.set('quantity', String(quantity))
      if (size) {
        body.set('size', size)
      }
      const isBase = isBaseProductType(productType)
      if (isBase && productId !== undefined) {
        body.set('product_id', String(productId))
      } else {
        if (productType) {
          body.set('product_type', productType)
        }
        if (productSlug) {
          body.set('product_slug', productSlug)
        }
      }
      const postAdd = () =>
        api.post('/orders/cart/add', body, {
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        })
      let response
      try {
        response = await postAdd()
      } catch (error: any) {
        const conflict = getCartVerificationError(error)
        const price = conflict?.verification?.public_price
        const currency = conflict?.verification?.public_currency || ''
        const available = Number(conflict?.verification?.available_quantity)
        const issueCodes = new Set([
          conflict?.code,
          ...(conflict?.issues || []).map((issue) => issue.code),
        ])
        let retryResolvedConflict = false

        if (
          issueCodes.has('source_quantity_changed') &&
          Number.isInteger(available) &&
          available > 0
        ) {
          const accepted = window.confirm(
            t(
              'cart_confirm_quantity_change',
              'У поставщика доступно {{quantity}} шт. Продолжить с доступным количеством?',
              { quantity: available },
            ),
          )
          if (!accepted) return
          body.set('quantity', String(available))
          retryResolvedConflict = true
        }
        if (issueCodes.has('source_price_changed') && price != null && currency) {
          const accepted = window.confirm(
            t(
              'cart_confirm_price_change',
              'Цена изменилась на {{price}} {{currency}}. Продолжить по новой цене?',
              { price: String(price), currency },
            ),
          )
          if (!accepted) return
          body.set('acknowledged_price', String(price))
          body.set('acknowledged_currency', currency)
          retryResolvedConflict = true
        }
        if (!retryResolvedConflict) {
          throw error
        }
        response = await postAdd()
      }
      if (response?.data) {
        setCartSummary(response.data)
      } else {
        await refresh()
      }
      // Перенаправляем на страницу оформления заказа
      router.push('/checkout')
    } catch (err: any) {
      const conflict = getCartVerificationError(err)
      const copy = getCartIssueCopy(conflict?.code)
      const detail = conflict?.code
        ? t(copy.key, copy.fallback)
        : err?.response?.data?.detail || err?.message || t('buy_now_error', 'Ошибка при оформлении заказа')
      alert(String(detail))
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={buyNow}
      disabled={loading}
      className={`inline-flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60 transition-all duration-200 ${className || ''}`}
    >
      {loading ? (
        <svg className="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      ) : (
        t('buy_now', 'Купить в один клик')
      )}
    </button>
  )
}
