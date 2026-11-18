import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { useStore } from 'zustand'
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/solid'
import { MinusIcon, PlusIcon, TrashIcon } from '@heroicons/react/24/outline'
import api, { initCartSession } from '../lib/api'
import {
  ADDED_DRAWER_AUTO_CLOSE_MS,
  ADDED_DRAWER_UNDO_MS,
  addedToRequestStore,
  drawerRows,
  drawerThumbUrl,
  orderDrawerItems,
  pickAddedItem,
  requestTotal,
  undoAddParams,
} from '../lib/addedToRequest'
import { getCartIssueCopy, getCartVerificationError, isBlockingCartItem, isSupplierConfirmationPending } from '../lib/cartVerification'
import { buildFavoriteProductHref } from '../lib/favoriteLinks'
import { gtmAddedDrawer } from '../lib/gtm'
import { getLocalizedProductName } from '../lib/i18n'
import { resolveMediaUrl } from '../lib/media'
import { formatMoney } from '../lib/price'
import { buildProductUrl } from '../lib/urls'
import { useCartStore } from '../store/cart'
import type { Cart, CartItem } from '../types/cart'
import styles from './AddedToRequestDrawer.module.css'

interface AddedPayload {
  cart?: Partial<Cart> | null
  addedId?: number
  trigger?: HTMLElement | null
}

interface RemovedEntry {
  key: string
  item: CartItem
  index: number
  error?: string
}

/**
 * Панель «Добавлено в заявку»: одна на всё приложение (_app.tsx), открывается из AddToCartButton.
 * Показывает все позиции заявки из ответа сервера; количество и удаление — теми же запросами,
 * что на странице /cart. Страницу под собой не сдвигает.
 */
export default function AddedToRequestDrawer() {
  const { t, i18n } = useTranslation('common')
  const router = useRouter()
  const isOpen = useStore(addedToRequestStore, (state) => state.isOpen)
  const engaged = useStore(addedToRequestStore, (state) => state.engaged)
  const payload: AddedPayload | null = useStore(addedToRequestStore, (state) => state.payload)
  const close = useStore(addedToRequestStore, (state) => state.close)
  const engage = useStore(addedToRequestStore, (state) => state.engage)
  const itemsCount = useCartStore((state) => state.itemsCount)
  const setCartSummary = useCartStore((state) => state.setCartSummary)
  const rootRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const undoTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})
  // shown идёт следом за isOpen: панель сначала появляется в разметке, потом выезжает
  const [shown, setShown] = useState(false)
  const [cart, setCart] = useState<Partial<Cart> | null>(null)
  // Порядок строк: добавленная первой, дальше позиции не прыгают при изменениях
  const [order, setOrder] = useState<number[]>([])
  const [removed, setRemoved] = useState<RemovedEntry[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [errors, setErrors] = useState<Record<number, string>>({})

  const clearUndoTimers = () => {
    Object.values(undoTimers.current).forEach(clearTimeout)
    undoTimers.current = {}
  }

  useEffect(() => {
    if (!isOpen) {
      setShown(false)
      return
    }
    const nextCart = payload?.cart ?? null
    setCart(nextCart)
    setOrder(orderDrawerItems(nextCart?.items, payload?.addedId).map((item: CartItem) => item.id))
    setRemoved([])
    setErrors({})
    setBusy(null)
    clearUndoTimers()
    gtmAddedDrawer('view')
    // Браузер фиксирует исходное положение за экраном — от него панель и выезжает
    panelRef.current?.getBoundingClientRect()
    setShown(true)
  }, [isOpen, payload])

  useEffect(() => clearUndoTimers, [])

  // Фокус — в панель, когда она уже видима (скрытый элемент фокус не принимает)
  useEffect(() => {
    if (shown) panelRef.current?.focus({ preventScroll: true })
  }, [shown])

  // Автозакрытие — только пока человек панель не трогал
  useEffect(() => {
    if (!isOpen || engaged) return
    const timer = setTimeout(close, ADDED_DRAWER_AUTO_CLOSE_MS)
    return () => clearTimeout(timer)
  }, [isOpen, engaged, payload, close])

  // Страница под панелью не прокручивается: колесо и жест проходят только в список позиций
  useEffect(() => {
    const root = rootRef.current
    if (!isOpen || !root) return
    const keepInside = (event: Event) => {
      const list = listRef.current
      const scrollsList = list && list.contains(event.target as Node) && list.scrollHeight > list.clientHeight
      if (!scrollsList) event.preventDefault()
    }
    root.addEventListener('wheel', keepInside, { passive: false })
    root.addEventListener('touchmove', keepInside, { passive: false })
    return () => {
      root.removeEventListener('wheel', keepInside)
      root.removeEventListener('touchmove', keepInside)
    }
  }, [isOpen, payload])

  // Фокус возвращается на кнопку «В заявку», если он остался в панели
  useEffect(() => {
    if (isOpen) return
    const active = document.activeElement
    const trigger = payload?.trigger
    if (!trigger || !panelRef.current || !active || !panelRef.current.contains(active)) return
    trigger.focus({ preventScroll: true })
    if (document.activeElement === trigger) return
    // Кнопка ещё показывает «Добавлено» и выключена — фокус вернётся, когда она включится
    const timer = setTimeout(() => {
      const current = document.activeElement
      if (current === document.body || panelRef.current?.contains(current)) trigger.focus({ preventScroll: true })
    }, 2000)
    return () => clearTimeout(timer)
  }, [isOpen, payload])

  useEffect(() => {
    router.events.on('routeChangeStart', close)
    return () => router.events.off('routeChangeStart', close)
  }, [router.events, close])

  // Ответ сервера — единственный источник позиций, счётчика в шапке и суммы
  const applyCart = useCallback((nextCart: Partial<Cart>) => {
    setCart(nextCart)
    setCartSummary(nextCart)
    setOrder((previous) => orderDrawerItems(nextCart.items, undefined, previous).map((item: CartItem) => item.id))
  }, [setCartSummary])

  if (!payload) return null

  const errorText = (error: any, fallbackKey: string, fallback: string): string => {
    const conflict = getCartVerificationError(error)
    if (conflict?.code) {
      const copy = getCartIssueCopy(conflict.code)
      return t(copy.key, copy.fallback)
    }
    const detail = error?.response?.data?.detail
    if (typeof detail === 'string' && detail) return detail
    if (Array.isArray(detail) && typeof detail[0] === 'string') return detail[0]
    return t(fallbackKey, fallback)
  }

  const dropRemoved = (key: string) => {
    delete undoTimers.current[key]
    setRemoved((list) => list.filter((entry) => entry.key !== key))
  }

  const scheduleDrop = (key: string) => {
    clearTimeout(undoTimers.current[key])
    undoTimers.current[key] = setTimeout(() => dropRemoved(key), ADDED_DRAWER_UNDO_MS)
  }

  const changeQuantity = async (item: CartItem, quantity: number) => {
    if (quantity < 1 || busy) return
    const previousCart = cart
    setBusy(`item-${item.id}`)
    setErrors(({ [item.id]: _cleared, ...rest }) => rest)
    setCart((current) => current && {
      ...current,
      items: (current.items || []).map((row) => (row.id === item.id ? { ...row, quantity } : row)),
    })
    try {
      const response = await api.post(`/orders/cart/${item.id}/update`, { quantity })
      applyCart(response.data)
      gtmAddedDrawer('qty_change')
    } catch (error: any) {
      const responseCart = error?.response?.data
      if (Array.isArray(responseCart?.items)) applyCart(responseCart)
      else setCart(previousCart)
      setErrors((current) => ({
        ...current,
        [item.id]: errorText(error, 'added_drawer_error', 'Не удалось изменить заявку. Попробуйте ещё раз.'),
      }))
    } finally {
      setBusy(null)
    }
  }

  const removeItem = async (item: CartItem, index: number) => {
    if (busy) return
    setBusy(`item-${item.id}`)
    try {
      const response = await api.delete(`/orders/cart/${item.id}/remove`)
      const key = `removed-${item.id}`
      setRemoved((list) => [...list, { key, item, index }])
      scheduleDrop(key)
      applyCart(response.data)
      gtmAddedDrawer('remove')
      // Кнопка удаления исчезла вместе со строкой — фокус остаётся в панели
      panelRef.current?.focus({ preventScroll: true })
    } catch (error: any) {
      setErrors((current) => ({
        ...current,
        [item.id]: errorText(error, 'added_drawer_error', 'Не удалось изменить заявку. Попробуйте ещё раз.'),
      }))
    } finally {
      setBusy(null)
    }
  }

  // «Вернуть» = добавить тот же товар, размер и количество; позиция встаёт на прежнее место
  const undoRemove = async (entry: RemovedEntry) => {
    if (busy) return
    clearTimeout(undoTimers.current[entry.key])
    setBusy(entry.key)
    try {
      initCartSession()
      const response = await api.post('/orders/cart/add', new URLSearchParams(undoAddParams(entry.item)), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      const restoredId = pickAddedItem(response.data)?.id
      setCart(response.data)
      setCartSummary(response.data)
      setOrder((previous) => {
        const ids = previous.filter((id) => id !== restoredId)
        if (restoredId !== undefined) ids.splice(Math.min(entry.index, ids.length), 0, restoredId)
        return ids
      })
      dropRemoved(entry.key)
    } catch (error: any) {
      const message = errorText(error, 'added_drawer_undo_error', 'Не удалось вернуть товар.')
      setRemoved((list) => list.map((row) => (row.key === entry.key ? { ...row, error: message } : row)))
      scheduleDrop(entry.key)
    } finally {
      setBusy(null)
    }
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      close()
      return
    }
    if (event.key !== 'Tab') return
    engage()
    const focusable = panelRef.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled)')
    if (!focusable?.length) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    const active = document.activeElement
    if (event.shiftKey && (active === first || active === panelRef.current)) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && active === last) {
      event.preventDefault()
      first.focus()
    }
  }

  const itemName = (item: CartItem) => (item.product_name
    ? getLocalizedProductName(item.product_name, t, item.product_translations, i18n.language)
    : '')

  const itemHref = (item: CartItem) => {
    const slug = item.product_parent_slug || item.product_slug
    if (!slug) return ''
    return buildFavoriteProductHref(buildProductUrl(item.product_type || 'medicines', slug), item.product_variant_slug, item.chosen_size)
  }

  const hasList = Array.isArray(cart?.items)
  const rows = drawerRows(orderDrawerItems(cart?.items, undefined, order), removed)
  const isEmpty = hasList && (cart?.items || []).length === 0
  const total = requestTotal(cart)
  const summary = itemsCount > 0
    ? t('added_drawer_summary', { count: itemsCount, defaultValue: 'В заявке товаров: {{count}}' })
    : ''
  const totalText = total ? `${formatMoney(total.amount, total.currency, i18n.language)} ${total.currency}` : ''

  return (
    <div ref={rootRef} className={styles.root} data-open={shown ? 'true' : 'false'} aria-hidden={!isOpen}>
      <div className={styles.backdrop} onClick={close} />
      <div
        ref={panelRef}
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="added-to-request-title"
        tabIndex={-1}
        onKeyDown={onKeyDown}
        onMouseEnter={engage}
        onTouchStart={engage}
        onFocus={(event) => {
          // Первый фокус ставит сама панель при открытии — он таймер не останавливает
          if (event.target !== panelRef.current) engage()
        }}
      >
        <div className={styles.header}>
          {!isEmpty && <span className={styles.check} aria-hidden="true"><CheckIcon /></span>}
          <h2 id="added-to-request-title" className={styles.title}>
            {isEmpty ? t('cart_empty', 'Заявка пуста') : t('added_drawer_title', 'Добавлено в заявку')}
          </h2>
          <button type="button" className={styles.close} onClick={close} aria-label={t('added_drawer_close', 'Закрыть')}>
            <XMarkIcon aria-hidden="true" />
          </button>
        </div>

        <div ref={listRef} className={styles.body} onScroll={engage}>
          {rows.length > 0 && (
            <ul className={styles.list}>
              {rows.map((row, index) => {
                const item: CartItem = row.item
                const name = itemName(item)
                const removedEntry: RemovedEntry | null = row.entry
                if (removedEntry) {
                  return (
                    <li key={row.key} className={styles.removedRow}>
                      <span className={styles.removedText}>
                        {t('added_drawer_removed', 'Удалено')}{name && ` · ${name}`}
                      </span>
                      <button
                        type="button"
                        className={styles.undo}
                        disabled={Boolean(busy)}
                        onClick={() => undoRemove(removedEntry)}
                      >
                        {t('added_drawer_undo', 'Вернуть')}
                      </button>
                      {removedEntry.error && <p className={styles.rowError} role="alert">{removedEntry.error}</p>}
                    </li>
                  )
                }
                const href = itemHref(item)
                const rowBusy = busy === row.key
                // Как на /cart: заблокированную позицию (кроме ожидающей подтверждения) менять нельзя
                const quantityLocked = isBlockingCartItem(item) && !isSupplierConfirmationPending(item)
                return (
                  <li
                    key={row.key}
                    className={styles.row}
                    data-added={item.id === payload.addedId ? 'true' : undefined}
                    data-busy={rowBusy ? 'true' : undefined}
                    aria-busy={rowBusy}
                  >
                    {item.product_image_url && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img className={styles.image} src={drawerThumbUrl(resolveMediaUrl(item.product_image_url))} alt="" width={72} height={72} />
                    )}
                    <div className={styles.itemText}>
                      {name && (href
                        ? <Link href={href} className={styles.name}>{name}</Link>
                        : <span className={styles.name}>{name}</span>)}
                      {item.chosen_size && <span>{t('size', 'Размер')}: {item.chosen_size}</span>}
                      <span className={styles.price}>
                        {item.price_on_request
                          ? t('price_on_request', 'Цена по запросу')
                          : `${formatMoney(item.price, item.currency, i18n.language)} ${item.currency}`}
                      </span>
                      <div className={styles.controls}>
                        <div className={styles.stepper}>
                          <button
                            type="button"
                            className={styles.step}
                            disabled={Boolean(busy) || quantityLocked || item.quantity <= 1}
                            onClick={() => changeQuantity(item, item.quantity - 1)}
                            aria-label={t('cart_decrease_quantity', 'Уменьшить количество')}
                          >
                            <MinusIcon aria-hidden="true" />
                          </button>
                          <span className={styles.quantity} aria-live="polite">{item.quantity}</span>
                          <button
                            type="button"
                            className={styles.step}
                            disabled={Boolean(busy) || quantityLocked}
                            onClick={() => changeQuantity(item, item.quantity + 1)}
                            aria-label={t('cart_increase_quantity', 'Увеличить количество')}
                          >
                            <PlusIcon aria-hidden="true" />
                          </button>
                        </div>
                        <button
                          type="button"
                          className={styles.remove}
                          disabled={Boolean(busy)}
                          onClick={() => removeItem(item, index)}
                          aria-label={name ? `${t('remove', 'Удалить')}: ${name}` : t('remove', 'Удалить')}
                        >
                          <TrashIcon aria-hidden="true" />
                        </button>
                      </div>
                      {errors[item.id] && <p className={styles.rowError} role="alert">{errors[item.id]}</p>}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
          {isEmpty && (
            <p className={styles.empty}>
              {t('cart_empty_description', 'Добавьте товары в заявку, чтобы отправить её менеджеру')}
            </p>
          )}
        </div>

        <div className={styles.footer}>
          {summary && !isEmpty && (
            <p className={styles.summary}>
              <span>{summary}</span>
              {totalText && <span>≈ {totalText}</span>}
            </p>
          )}
          {!isEmpty && (
            <Link href="/cart" className={styles.primary} onClick={() => gtmAddedDrawer('checkout')}>
              {t('go_to_request', 'Оформить заявку')}
            </Link>
          )}
          <button
            type="button"
            className={isEmpty ? styles.primary : styles.secondary}
            onClick={() => {
              gtmAddedDrawer('continue')
              close()
            }}
          >
            {t('added_drawer_continue', 'Продолжить выбор')}
          </button>
          <p className={styles.note}>
            {t('added_drawer_note', 'Оплаты на сайте нет. Менеджер проверит наличие и назовёт итоговую цену с доставкой.')}
          </p>
        </div>
      </div>
    </div>
  )
}
