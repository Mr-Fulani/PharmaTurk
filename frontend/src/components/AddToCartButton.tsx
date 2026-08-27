import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'next-i18next'
import api, { initCartSession } from '../lib/api'
import { getCartIssueCopy, getCartVerificationError } from '../lib/cartVerification'
import { useCartStore } from '../store/cart'
import styles from './AddToCartButton.module.css'

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
  price
}: AddToCartButtonProps) {
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { refresh, setCartSummary } = useCartStore()
  const { t } = useTranslation('common')

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
              'У поставщика доступно {{quantity}} шт. Добавить доступное количество?',
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
              'Цена изменилась на {{price}} {{currency}}. Добавить товар по новой цене?',
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
      const itemsCount = Number(response.data?.items_count)
      if (Number.isFinite(itemsCount)) {
        setCartSummary(response.data)
      } else {
        await refresh()
      }

      setDone(true)
      resetTimerRef.current = setTimeout(() => {
        setDone(false)
        resetTimerRef.current = null
      }, 1450)
    } catch (err: any) {
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
