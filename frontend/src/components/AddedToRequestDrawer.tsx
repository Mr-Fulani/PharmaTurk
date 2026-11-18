import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { useStore } from 'zustand'
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/solid'
import { ADDED_DRAWER_AUTO_CLOSE_MS, addedToRequestStore, drawerThumbUrl } from '../lib/addedToRequest'
import { gtmAddedDrawer } from '../lib/gtm'
import { getLocalizedProductName } from '../lib/i18n'
import { resolveMediaUrl } from '../lib/media'
import { formatMoney } from '../lib/price'
import { useCartStore } from '../store/cart'
import type { CartItem, MoneyValue } from '../types/cart'
import styles from './AddedToRequestDrawer.module.css'

interface AddedPayload {
  item?: CartItem | null
  total?: { amount: MoneyValue; currency: string } | null
  trigger?: HTMLElement | null
}

/**
 * Панель «Добавлено в заявку»: одна на всё приложение (_app.tsx), открывается из AddToCartButton.
 * Показывает только то, что пришло в ответе сервера; страницу не блокирует и не сдвигает.
 */
export default function AddedToRequestDrawer() {
  const { t, i18n } = useTranslation('common')
  const router = useRouter()
  const isOpen = useStore(addedToRequestStore, (state) => state.isOpen)
  const payload: AddedPayload | null = useStore(addedToRequestStore, (state) => state.payload)
  const close = useStore(addedToRequestStore, (state) => state.close)
  const itemsCount = useCartStore((state) => state.itemsCount)
  const panelRef = useRef<HTMLDivElement>(null)
  // shown идёт следом за isOpen: панель сначала появляется в разметке, потом выезжает
  const [shown, setShown] = useState(false)
  const [hovered, setHovered] = useState(false)
  // Касание или работа с клавиатуры: человек занят панелью, сама она уже не закроется
  const [engaged, setEngaged] = useState(false)

  useEffect(() => {
    if (!isOpen) {
      setShown(false)
      return
    }
    setHovered(false)
    setEngaged(false)
    gtmAddedDrawer('view')
    // Браузер фиксирует исходное положение за экраном — от него панель и выезжает
    panelRef.current?.getBoundingClientRect()
    setShown(true)
  }, [isOpen, payload])

  // Фокус — в панель, когда она уже видима (скрытый элемент фокус не принимает)
  useEffect(() => {
    if (shown) panelRef.current?.focus({ preventScroll: true })
  }, [shown])

  useEffect(() => {
    if (!isOpen || hovered || engaged) return
    const timer = setTimeout(close, ADDED_DRAWER_AUTO_CLOSE_MS)
    return () => clearTimeout(timer)
  }, [isOpen, hovered, engaged, payload, close])

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

  if (!payload) return null

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      close()
      return
    }
    if (event.key !== 'Tab') return
    setEngaged(true)
    const focusable = panelRef.current?.querySelectorAll<HTMLElement>('a[href], button')
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

  const { item, total } = payload
  const name = item?.product_name
    ? getLocalizedProductName(item.product_name, t, item.product_translations, i18n.language)
    : ''
  const price = item
    ? item.price_on_request
      ? t('price_on_request', 'Цена по запросу')
      : `${formatMoney(item.price, item.currency, i18n.language)} ${item.currency}`
    : ''
  const summary = itemsCount > 0
    ? t('added_drawer_summary', { count: itemsCount, defaultValue: 'В заявке товаров: {{count}}' })
    : ''
  const totalText = total ? `${formatMoney(total.amount, total.currency, i18n.language)} ${total.currency}` : ''

  return (
    <div className={styles.root} data-open={shown ? 'true' : 'false'} aria-hidden={!isOpen}>
      <div className={styles.backdrop} onClick={close} />
      <div
        ref={panelRef}
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="added-to-request-title"
        tabIndex={-1}
        onKeyDown={onKeyDown}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onTouchStart={() => setEngaged(true)}
        onFocus={(event) => {
          // Первый фокус ставит сама панель при открытии — он таймер не останавливает
          if (event.target !== panelRef.current) setEngaged(true)
        }}
      >
        <div className={styles.header}>
          <span className={styles.check} aria-hidden="true"><CheckIcon /></span>
          <h2 id="added-to-request-title" className={styles.title}>
            {t('added_drawer_title', 'Добавлено в заявку')}
          </h2>
          <button type="button" className={styles.close} onClick={close} aria-label={t('added_drawer_close', 'Закрыть')}>
            <XMarkIcon aria-hidden="true" />
          </button>
        </div>

        <div className={styles.body}>
          {item && (
            <div className={styles.item}>
              {item.product_image_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img className={styles.image} src={drawerThumbUrl(resolveMediaUrl(item.product_image_url))} alt="" width={72} height={72} />
              )}
              <div className={styles.itemText}>
                {name && <span className={styles.name}>{name}</span>}
                {item.chosen_size && <span>{t('size', 'Размер')}: {item.chosen_size}</span>}
                <span>{t('quantity', 'Количество')}: {item.quantity}</span>
                <span className={styles.price}>{price}</span>
              </div>
            </div>
          )}
          {summary && (
            <p className={styles.summary}>
              {summary}{totalText && ` · ≈ ${totalText}`}
            </p>
          )}
        </div>

        <div className={styles.footer}>
          <Link href="/cart" className={styles.primary} onClick={() => gtmAddedDrawer('checkout')}>
            {t('go_to_request', 'Оформить заявку')}
          </Link>
          <button
            type="button"
            className={styles.secondary}
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
