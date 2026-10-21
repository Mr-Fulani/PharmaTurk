/**
 * Единый слой аналитики: GA4 (gtag) + цели Яндекс Метрики.
 * Компоненты вызывают только хелперы gtm* ниже: событие уходит в dataLayer
 * (оттуда e-commerce читает Метрика), дублируется в GA4 и, где нужно, отмечает цель Метрики.
 * Аналитика инициализируется ТОЛЬКО после cookie-согласия пользователя.
 * Список событий и целей — docs/ANALYTICS_EVENTS.md.
 */

import { ymReachGoal } from './ym'

export const GTM_ID = process.env.NEXT_PUBLIC_GTM_ID

// ─── Типы ────────────────────────────────────────────────────────────────────

export type GtmEventName =
  | 'view_item'
  | 'view_item_list'
  | 'add_to_cart'
  | 'add_to_wishlist'
  | 'remove_from_cart'
  | 'begin_checkout'
  | 'generate_lead'
  | 'purchase'
  | 'search'
  | 'contact_click'
  | 'page_view'
  | 'login'
  | 'sign_up'

export interface GtmEcommerceItem {
  item_id: string | number
  item_name: string
  /** Тип товара: medicines, supplements, clothing… */
  item_category?: string
  item_brand?: string
  /** Размер/вариант */
  item_variant?: string
  price?: number
  quantity?: number
  /** Позиция в списке (view_item_list) */
  index?: number
}

export interface GtmEcommerce {
  currency?: string
  value?: number
  transaction_id?: string
  items?: GtmEcommerceItem[]
  item_list_id?: string
  item_list_name?: string
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
  // дублируем событие в GA4.
  sendToGa4(eventData)
}

const GTAG_WAIT_MS = 5000
const GTAG_POLL_MS = 200

/**
 * window.gtag появляется только после согласия на аналитику и после гидратации
 * (next/script afterInteractive), а view_item при первом заходе на карточку срабатывает
 * раньше — ждём gtag до 5 секунд. Без согласия gtag не появится и событие не уйдёт.
 */
function sendToGa4(eventData: GtmEvent, waitedMs = 0): void {
  if (typeof window.gtag === 'function') {
    window.gtag('event', eventData.event, ga4EventParams(eventData))
    return
  }
  if (waitedMs >= GTAG_WAIT_MS) return
  window.setTimeout(() => sendToGa4(eventData, waitedMs + GTAG_POLL_MS), GTAG_POLL_MS)
}

/** Параметры события для gtag: ecommerce-поля на верхний уровень, без имени события. */
export function ga4EventParams(eventData: GtmEvent): Record<string, unknown> {
  const { event, ecommerce, ...rest } = eventData
  return { ...rest, ...(ecommerce || {}) }
}

// ─── Хелперы для e-commerce событий ─────────────────────────────────────────

/**
 * Товар каталога → позиция GA4. item_id как у view_item и корзины:
 * у базовых типов — id базового товара, у остальных — slug.
 */
export function gtmProductItem(
  product: { id?: number; base_product_id?: number | null; slug?: string; name?: string },
  productType: string,
  isBaseType: boolean,
): GtmEcommerceItem {
  return {
    item_id: (isBaseType ? product.base_product_id ?? product.id : product.slug) ?? product.slug ?? '',
    item_name: product.name || product.slug || '',
    item_category: productType,
  }
}

/** Просмотр списка товаров: категория, бренд. Один вызов на загруженную страницу списка. */
export function gtmViewItemList(list: { id: string; name: string }, items: GtmEcommerceItem[]): void {
  if (!items.length) return
  gtmEvent({
    event: 'view_item_list',
    ecommerce: {
      item_list_id: list.id,
      item_list_name: list.name,
      items: items.map((item, index) => ({ ...item, index })),
    },
  })
}

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

/** «В заявку» (корзина). ymGoal — цель Метрики: add_to_cart или buy_now. */
export function gtmAddToCart(
  item: GtmEcommerceItem,
  quantity = 1,
  currency = 'USD',
  ymGoal: 'add_to_cart' | 'buy_now' = 'add_to_cart',
): void {
  gtmEvent({
    event: 'add_to_cart',
    ecommerce: {
      currency,
      value: item.price !== undefined ? item.price * quantity : undefined,
      items: [{ ...item, quantity }],
    },
  })
  ymReachGoal(ymGoal)
}

export function gtmAddToWishlist(item: GtmEcommerceItem, currency = 'USD'): void {
  gtmEvent({
    event: 'add_to_wishlist',
    ecommerce: {
      currency,
      value: item.price,
      items: [{ ...item, quantity: 1 }],
    },
  })
  ymReachGoal('add_to_wishlist')
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
  ymReachGoal('begin_checkout')
}

export interface GtmLead {
  /** order — заявка из корзины, sourcing — заявка на подбор товара */
  source: 'order' | 'sourcing'
  /** Где стоит форма подбора: home, category, search, how_to_order */
  placement?: string
  value?: number
  currency?: string
  /** Номер заявки */
  transactionId?: string
  paymentMethod?: string
}

/**
 * Отправленная заявка менеджеру. Онлайн-оплаты нет, поэтому это лид (generate_lead),
 * а не покупка: purchase с выручкой исказил бы отчёты GA4.
 * В Метрике — общая цель generate_lead и цель по типу заявки (order_request / sourcing_request).
 */
export function gtmGenerateLead(lead: GtmLead): void {
  const params: Record<string, unknown> = { lead_source: lead.source }
  if (lead.placement) params.placement = lead.placement
  if (lead.value !== undefined) params.value = lead.value
  if (lead.currency) params.currency = lead.currency
  if (lead.transactionId) params.transaction_id = lead.transactionId
  if (lead.paymentMethod) params.payment_method = lead.paymentMethod
  gtmEvent({ event: 'generate_lead', ...params })

  // order_price + currency — доход по цели в Метрике
  const ymParams: Record<string, unknown> = { lead_source: lead.source }
  if (lead.placement) ymParams.placement = lead.placement
  if (lead.value !== undefined) ymParams.order_price = lead.value
  if (lead.currency) ymParams.currency = lead.currency
  ymReachGoal('generate_lead', ymParams)
  ymReachGoal(`${lead.source}_request`, ymParams)
}

export function gtmSearch(searchTerm: string): void {
  gtmEvent({
    event: 'search',
    ecommerce: { search_term: searchTerm },
  })
  ymReachGoal('search', { query: searchTerm })
}

// ─── Клики по контактам ─────────────────────────────────────────────────────

export type ContactChannel = 'whatsapp' | 'telegram' | 'phone' | 'email' | 'vk'

// Ссылки «поделиться» (wa.me/?text=, t.me/share, vk.com/share.php) — не контакт
const CONTACT_LINK_RULES: Array<[ContactChannel, RegExp]> = [
  ['phone', /^tel:/i],
  ['email', /^mailto:/i],
  ['whatsapp', /^whatsapp:|^(https?:\/\/)?(wa\.me\/\+?\d|api\.whatsapp\.com\/send\?(.*&)?phone=)/i],
  ['telegram', /^tg:|^(https?:\/\/)?(t\.me|telegram\.me)\/(?!share\/)[\w+]/i],
  ['vk', /^(https?:\/\/)?((m\.)?vk\.com\/(?!share\.php)\w|vk\.me\/\w)/i],
]

/** Канал связи по href ссылки или null, если это не контакт. */
export function contactChannelFromHref(href: string | null | undefined): ContactChannel | null {
  const value = (href || '').trim()
  if (!value) return null
  const rule = CONTACT_LINK_RULES.find(([, pattern]) => pattern.test(value))
  return rule ? rule[0] : null
}

/** Клик по WhatsApp/Telegram/телефону/email/VK. placement — виджет, футер, страница. */
export function gtmContactClick(channel: ContactChannel, placement: string): void {
  gtmEvent({ event: 'contact_click', contact_channel: channel, placement })
  ymReachGoal(`click_${channel}`, { placement })
}

/**
 * Делегированный обработчик click на document (вешается в _app): ловит контактные ссылки
 * в любом месте сайта. placement берётся из ближайшего data-analytics-placement, иначе page.
 */
export function handleContactLinkClick(event: Event): void {
  const link = (event.target as Element | null)?.closest?.('a[href]')
  if (!link) return
  const channel = contactChannelFromHref(link.getAttribute('href'))
  if (!channel) return
  // Контакты пользователей в профилях — не обращение к нам
  if (/^\/(en\/)?(profile|user)(\/|$)/.test(window.location.pathname)) return
  const placement = link.closest('[data-analytics-placement]')?.getAttribute('data-analytics-placement') || 'page'
  gtmContactClick(channel, placement)
}

// ─── Типы window ─────────────────────────────────────────────────────────────

declare global {
  interface Window {
    dataLayer: Record<string, unknown>[]
    /** gtag.js (GA4) — подключается в _app только после cookie-согласия */
    gtag?: (...args: unknown[]) => void
  }
}
