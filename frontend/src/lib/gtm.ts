/**
 * Google Tag Manager / GA4 — утилита для e-commerce событий.
 * Аналитика инициализируется ТОЛЬКО после cookie-согласия пользователя.
 */

export const GTM_ID = process.env.NEXT_PUBLIC_GTM_ID

// ─── Типы ────────────────────────────────────────────────────────────────────

export type GtmEventName =
  | 'view_item'
  | 'view_item_list'
  | 'add_to_cart'
  | 'remove_from_cart'
  | 'begin_checkout'
  | 'purchase'
  | 'search'
  | 'page_view'
  | 'login'
  | 'sign_up'

export interface GtmEcommerceItem {
  item_id: string | number
  item_name: string
  item_category?: string
  item_brand?: string
  price?: number
  quantity?: number
}

export interface GtmEcommerce {
  currency?: string
  value?: number
  transaction_id?: string
  items?: GtmEcommerceItem[]
  search_term?: string
}

export interface GtmEvent {
  event: GtmEventName | string
  ecommerce?: GtmEcommerce
  [key: string]: unknown
}

// ─── Функции ─────────────────────────────────────────────────────────────────

/**
 * Инициализирует dataLayer. Вызывается при загрузке страницы.
 */
export function initDataLayer(): void {
  if (typeof window === 'undefined') return
  window.dataLayer = window.dataLayer || []
}

/**
 * Consent Mode: снимает запрет, выставленный по умолчанию в _document,
 * и пушит событие согласия для триггеров GTM.
 */
export function gtmConsentGranted(): void {
  if (typeof window === 'undefined') return
  window.dataLayer = window.dataLayer || []
  // Команды Consent Mode GTM принимает только в формате gtag — как объект arguments
  function gtag(..._args: unknown[]): void {
    // eslint-disable-next-line prefer-rest-params
    window.dataLayer.push(arguments as unknown as Record<string, unknown>)
  }
  gtag('consent', 'update', {
    analytics_storage: 'granted',
    ad_storage: 'granted',
    ad_user_data: 'granted',
    ad_personalization: 'granted',
  })
  window.dataLayer.push({
    event: 'cookie_consent_granted',
    analytics_storage: 'granted',
    ad_storage: 'granted',
  })
}

/**
 * Отправляет событие просмотра страницы.
 * Вызывается при каждом routeChangeComplete в _app.tsx.
 */
export function gtmPageView(url: string): void {
  if (typeof window === 'undefined' || !window.dataLayer) return
  window.dataLayer.push({
    event: 'page_view',
    page_path: url,
  })
}

/**
 * Отправляет произвольное GTM-событие (включая e-commerce).
 * Перед каждым ecommerce событием очищает предыдущие данные.
 */
export function gtmEvent(eventData: GtmEvent): void {
  if (typeof window === 'undefined' || !window.dataLayer) return

  if (eventData.ecommerce) {
    // Очистка предыдущего ecommerce объекта (обязательное требование GA4)
    window.dataLayer.push({ ecommerce: null })
  }

  window.dataLayer.push(eventData)

  // GA4 подключён напрямую (gtag), а объектные push в dataLayer gtag не обрабатывает —
  // дублируем событие в GA4. window.gtag есть только после согласия на аналитику.
  if (typeof window.gtag === 'function') {
    window.gtag('event', eventData.event, ga4EventParams(eventData))
  }
}

/** Параметры события для gtag: ecommerce-поля на верхний уровень, без имени события. */
export function ga4EventParams(eventData: GtmEvent): Record<string, unknown> {
  const { event, ecommerce, ...rest } = eventData
  return { ...rest, ...(ecommerce || {}) }
}

// ─── Хелперы для e-commerce событий ─────────────────────────────────────────

export function gtmViewItem(item: GtmEcommerceItem, currency = 'USD'): void {
  gtmEvent({
    event: 'view_item',
    ecommerce: {
      currency,
      value: item.price,
      items: [{ ...item, quantity: 1 }],
    },
  })
}

export function gtmAddToCart(item: GtmEcommerceItem, quantity = 1, currency = 'USD'): void {
  gtmEvent({
    event: 'add_to_cart',
    ecommerce: {
      currency,
      value: item.price !== undefined ? item.price * quantity : undefined,
      items: [{ ...item, quantity }],
    },
  })
}

export function gtmRemoveFromCart(item: GtmEcommerceItem, quantity = 1, currency = 'USD'): void {
  gtmEvent({
    event: 'remove_from_cart',
    ecommerce: {
      currency,
      value: (item.price ?? 0) * quantity,
      items: [{ ...item, quantity }],
    },
  })
}

export function gtmBeginCheckout(items: GtmEcommerceItem[], value: number, currency = 'USD'): void {
  gtmEvent({
    event: 'begin_checkout',
    ecommerce: { currency, value, items },
  })
}

export function gtmPurchase(
  transactionId: string,
  items: GtmEcommerceItem[],
  value: number,
  currency = 'USD'
): void {
  gtmEvent({
    event: 'purchase',
    ecommerce: { currency, value, transaction_id: transactionId, items },
  })
}

export function gtmSearch(searchTerm: string): void {
  gtmEvent({
    event: 'search',
    ecommerce: { search_term: searchTerm },
  })
}

// ─── Типы window ─────────────────────────────────────────────────────────────

declare global {
  interface Window {
    dataLayer: Record<string, unknown>[]
  }
}
