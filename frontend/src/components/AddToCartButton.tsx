import { useState } from 'react'
import { useTranslation } from 'next-i18next'
import api, { initCartSession } from '../lib/api'
import { useCartStore } from '../store/cart'

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
  const { refresh } = useCartStore()
  const { t } = useTranslation('common')

  const add = async () => {
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
      const baseTypes = [
        'medicines', 'supplements', 'medical-equipment', 'medical_equipment',
        'furniture', 'tableware', 'accessories', 'jewelry',
        'underwear', 'headwear'
      ]
      const isBase = baseTypes.includes(productType)
      if (isBase && productId !== undefined) {
        body.set('product_id', String(productId))
      } else {
        if (productType) {
          body.set('product_type', productType)
        }
        if (productSlug) {
          body.set('product_slug', productSlug)
        }
        if (size) {
          body.set('size', size)
        }
      }
      try {
        await api.post('/orders/cart/add', body, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
      } catch (e: any) {
        await api.post('/orders/cart/add/', body, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
      }
      await refresh()
      setDone(true)
      setTimeout(()=>setDone(false), 1500)
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || t('add_to_cart_error', 'Ошибка добавления в корзину')
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
  
  // Иконка корзины для отображения при наведении
  const cartIcon = (
    <svg 
      className="w-5 h-5" 
      fill="none" 
      stroke="currentColor" 
      viewBox="0 0 24 24"
    >
      <path 
        strokeLinecap="round" 
        strokeLinejoin="round" 
        strokeWidth={2} 
        d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" 
      />
    </svg>
  )
  
  // Если показываем цену, используем светлый стиль с границей, иначе - стандартный акцентный
  const useLightStyle = showPrice && price
  const buttonClassName = useLightStyle
    ? `inline-flex items-center justify-center gap-2 rounded-md bg-stone-50 border border-gray-900 px-4 py-2 text-sm font-medium text-gray-900 hover:bg-stone-100 disabled:opacity-60 transition-all duration-200 ${className || ''}`
    : `inline-flex items-center justify-center gap-2 rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--accent-strong)] disabled:opacity-60 transition-all duration-200 ${className || ''} ${
        isIconOnly ? 'group' : ''
      }`

  return (
    <button
      onClick={add}
      disabled={loading}
      className={buttonClassName}
    >
      {loading ? (
        <svg className="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      ) : useLightStyle ? (
        displayText
      ) : isIconOnly ? (
        <>
          <span className="group-hover:hidden transition-opacity duration-200">
            {done ? t('added', 'Добавлено') : cartIcon}
          </span>
          <span className="hidden group-hover:block transition-opacity duration-200">
            {cartIcon}
          </span>
        </>
      ) : (
        <>
          <span className="group-hover:hidden transition-opacity duration-200">
            {displayText}
          </span>
          <span className="hidden group-hover:block transition-opacity duration-200">
            {cartIcon}
          </span>
        </>
      )}
    </button>
  )
}
