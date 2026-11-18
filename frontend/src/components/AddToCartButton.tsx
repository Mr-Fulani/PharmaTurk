import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'next-i18next'
import api, { initCartSession } from '../lib/api'
import { getCartIssueCopy, getCartVerificationError } from '../lib/cartVerification'
import { isSoldOutCartError } from '../lib/cartStock'
import { useCartStore } from '../store/cart'
import { gtmAddToCart, type GtmEcommerceItem } from '../lib/gtm'
import { addedToRequestStore, pickAddedItem } from '../lib/addedToRequest'
import { addConflictOffer, addConflictRetryParams, askConfirm } from '../lib/confirmDialog'
import { formatMoney } from '../lib/price'
import styles from './AddToCartButton.module.css'

// Длительности синхронны с AddToCartButton.module.css: полёт товара (shirtFlight)
// и показ «Добавлено» (cartExit + labelIn).
const ADDING_ANIMATION_MS = 1600
const SUCCESS_STATE_MS = 1800

interface AddToCartButtonProps {
  productId?: number
  productType?: string
  productSlug?: string
  size?: string
  requireSize?: boolean
  className?: string
  label?: string
  quantity?: number
  showPrice?: boolean
  price?: string
  /** Товар для аналитики (как в view_item карточки): название, тип, цена */
  analyticsItem?: GtmEcommerceItem
  analyticsCurrency?: string
  /** Вызывается после успешного добавления (когда показывается «Добавлено») */
  onAdded?: () => void
  /** Товар закончился у поставщика: карточка переключается в «Нет в наличии» вместо окна с ошибкой */
  onSoldOut?: () => void
}

export default function AddToCartButton({
  productId,
  productType = 'medicines',
  productSlug,
  size,
  requireSize = false,
  className,
  label,
  quantity = 1,
  showPrice = false,
  price,
  analyticsItem,
  analyticsCurrency,
  onAdded,
  onSoldOut,
}: AddToCartButtonProps) {
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const { refresh, setCartSummary } = useCartStore()
  const { t, i18n } = useTranslation('common')

  useEffect(() => {
    return () => {
      if (resetTimerRef.current) {
        clearTimeout(resetTimerRef.current)
      }
    }
  }, [])

  const add = async () => {
    if (loading || done) return
    if (requireSize && !size) {
      alert(t('select_size', 'Выберите размер'))
      return
    }

    setDone(false)
    setLoading(true)
    const startedAt = Date.now()
    try {
      initCartSession()
      const body = new URLSearchParams()
      body.set('quantity', String(quantity))
      if (size) {
        body.set('size', size)
      }
      if (productId !== undefined) {
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
        // Поставщик сообщил другую цену или меньшее количество: спрашиваем один раз окном сайта
        const offer = addConflictOffer(getCartVerificationError(error))
        if (!offer) {
          throw error
        }
        const priceText = offer.price
          ? `${formatMoney(offer.price, offer.currency, i18n.language)} ${offer.currency}`
          : ''
        const lines = []
        if (offer.quantity) {
          lines.push(t('confirm_add_quantity_text', 'У поставщика сейчас доступно {{count}} шт.', { count: offer.quantity }))
        }
        if (offer.price) {
          lines.push(t('confirm_add_price_text', 'Новая цена — {{price}}.', { price: priceText }))
        }
        const accepted = await askConfirm({
          title: offer.quantity && offer.price
            ? t('confirm_add_both_title', 'Цена и количество изменились')
            : offer.price
              ? t('confirm_add_price_title', 'Цена изменилась')
              : t('confirm_add_quantity_title', 'Доступно меньше, чем вы выбрали'),
          lines,
          acceptLabel: offer.quantity && offer.price
            ? t('confirm_add_both_accept', 'Добавить {{count}} шт. по новой цене', { count: offer.quantity })
            : offer.price
              ? t('confirm_add_price_accept', 'Добавить по новой цене')
              : t('confirm_add_quantity_accept', 'Добавить {{count}} шт.', { count: offer.quantity }),
          declineLabel: t('confirm_add_decline', 'Не добавлять'),
        })
        if (!accepted) return
        Object.entries(addConflictRetryParams(offer)).forEach(([key, value]) => body.set(key, String(value)))
        response = await postAdd()
      }
      const itemsCount = Number(response.data?.items_count)
      if (Number.isFinite(itemsCount)) {
        setCartSummary(response.data)
      } else {
        await refresh()
      }

      gtmAddToCart(
        { ...(analyticsItem ?? { item_id: productId ?? productSlug ?? '', item_name: productSlug || String(productId ?? '') }), ...(size && { item_variant: size }) },
        quantity,
        analyticsCurrency,
      )

      // Быстрый ответ API обрывал полёт товара в корзину на середине: даём ему доиграть.
      // Таймер в resetTimerRef: при размонтировании он снимается, и дальше код не идёт.
      const remaining = ADDING_ANIMATION_MS - (Date.now() - startedAt)
      if (remaining > 0 && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        await new Promise<void>((resolve) => {
          resetTimerRef.current = setTimeout(resolve, remaining)
        })
      }

      setDone(true)
      // Панель «Добавлено в заявку»: позиции и сумма — из ответа сервера
      addedToRequestStore.getState().open(
        { cart: response.data, addedId: pickAddedItem(response.data)?.id, trigger: buttonRef.current },
        window.location.pathname,
      )
      onAdded?.()
      resetTimerRef.current = setTimeout(() => {
        setDone(false)
        resetTimerRef.current = null
      }, SUCCESS_STATE_MS)
    } catch (err: any) {
      if (onSoldOut && isSoldOutCartError(err)) {
        onSoldOut()
        return
      }
      const conflict = getCartVerificationError(err)
      const copy = getCartIssueCopy(conflict?.code)
      const detail = conflict?.code
        ? t(copy.key, copy.fallback)
        : err?.response?.data?.detail || err?.message || t('add_to_cart_error', 'Ошибка добавления в корзину')
      // Быстрый видимый фидбек пользователю
      alert(String(detail))
      // И лог для диагностики
      // eslint-disable-next-line no-console
      console.error('AddToCart error', err?.response?.status, err?.response?.data)
    } finally {
      setLoading(false)
    }
  }

  const isIconOnly = !label || label === ''
  const baseLabel = label || t('add_to_cart', 'В корзину')
  const displayText = done 
    ? t('added', 'Добавлено') 
    : (loading 
      ? t('adding', 'Добавляем...') 
      : (showPrice && price 
        ? `${baseLabel} - ${price}` 
        : baseLabel))
  
  const useLightStyle = showPrice && price
  const state = done ? 'success' : loading ? 'adding' : 'idle'
  const accessibleLabel = done
    ? t('added', 'Добавлено')
    : loading
      ? t('adding', 'Добавляем...')
      : baseLabel
  
  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={add}
      disabled={loading || done}
      aria-busy={loading}
      aria-label={accessibleLabel}
      className={`${styles.button} ${className || ''}`}
      data-state={state}
      data-variant={useLightStyle ? 'light' : 'accent'}
      data-icon-only={isIconOnly ? 'true' : 'false'}
    >
      <span className={styles.label} aria-live="polite">
        {displayText}
      </span>

      <svg className={styles.morph} viewBox="0 0 64 13" aria-hidden="true">
        <path d="M0 12C6 12 20 10 32 0C43.9 10 58 12 64 12V13H0V12Z" />
      </svg>

      <span className={styles.shirt} aria-hidden="true">
        <svg className={styles.shirtPrimary} viewBox="0 0 24 24">
          <path
            className={styles.shirtBody}
            d="M5 3 9 1.5S10.69 3 12 3s3-1.5 3-1.5L19 3l3.5 5-3 2.5-.5-1-1.82 9.11a3 3 0 0 1-.85 1.51C15.43 20.93 13.71 22.31 12 23c-1.71-.69-3.43-2.07-4.34-2.88a3 3 0 0 1-.84-1.51L5 9.5l-.5 1-3-2.5L5 3Z"
          />
          <path
            className={styles.shirtLogo}
            d="M14.2 5.7h2.3v4.1h-2.3V5.7Zm.4.4v3.3h1.5V6.1h-1.5Z"
          />
        </svg>
        <svg className={styles.shirtSecondary} viewBox="0 0 24 24">
          <path
            className={styles.shirtBody}
            d="M5 3 9 1.5S10.69 3 12 3s3-1.5 3-1.5L19 3l3.5 5-3 2.5-.5-1-1.82 9.11a3 3 0 0 1-.85 1.51C15.43 20.93 13.71 22.31 12 23c-1.71-.69-3.43-2.07-4.34-2.88a3 3 0 0 1-.84-1.51L5 9.5l-.5 1-3-2.5L5 3Z"
          />
          <path
            className={styles.shirtLogo}
            d="M14.2 5.7h2.3v4.1h-2.3V5.7Zm.4.4v3.3h1.5V6.1h-1.5Z"
          />
        </svg>
      </span>

      <span className={styles.cart} aria-hidden="true">
        <span className={styles.cartFill} />
        <svg viewBox="0 0 36 26">
          <path
            className={styles.cartShape}
            d="M1 2.5H6L10 18.5H25.5L28.5 7.5H7.5"
          />
          <path
            className={styles.cartWheel}
            d="M11.5 25C12.6046 25 13.5 24.1046 13.5 23C13.5 21.8954 12.6046 21 11.5 21C10.3954 21 9.5 21.8954 9.5 23C9.5 24.1046 10.3954 25 11.5 25Z"
          />
          <path
            className={styles.cartWheel}
            d="M24 25C25.1046 25 26 24.1046 26 23C26 21.8954 25.1046 21 24 21C22.8954 21 22 21.8954 22 23C22 24.1046 22.8954 25 24 25Z"
          />
          <path
            className={styles.cartTick}
            d="M14.5 13.5L16.5 15.5L21.5 10.5"
          />
        </svg>
      </span>
    </button>
  )
}
