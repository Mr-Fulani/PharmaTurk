/**
 * Панель «Добавлено в заявку» (components/AddedToRequestDrawer.tsx): состояние и правила показа.
 * Открывает её AddToCartButton после успешного добавления; BuyNowButton сам ведёт в Список заявки.
 */
import { createStore } from 'zustand/vanilla'

/** Автозакрытие панели, мс. */
export const ADDED_DRAWER_AUTO_CLOSE_MS = 7000

/** Страница «Список заявки» (/cart, /en/cart): товар и так виден в списке, панель не нужна. */
export function isCartPath(pathname) {
  return /^\/(en\/)?cart\/?$/.test(String(pathname || '').split(/[?#]/)[0])
}

/**
 * Только что добавленная позиция в ответе /orders/cart/add: сервер при добавлении
 * сохраняет именно её, поэтому у неё самый свежий updated_at. Нет позиций — null.
 */
export function pickAddedItem(cart) {
  const items = Array.isArray(cart?.items) ? cart.items : []
  let added = null
  for (const item of items) {
    if (!added || String(item.updated_at || '') > String(added.updated_at || '')) added = item
  }
  return added
}

/** Сумма заявки для плашки: только если сервер прислал положительное число. */
export function requestTotal(cart) {
  const amount = cart?.final_amount ?? cart?.total_amount
  const value = Number(amount)
  if (!Number.isFinite(value) || value <= 0 || !cart?.currency) return null
  return { amount, currency: cart.currency }
}

/**
 * Миниатюра позиции (72 px): корзина отдаёт фото из нашего CDN через proxy-image в полном
 * размере (до 2000 px, ~160 КБ), а proxy-media по тому же пути умеет уменьшать (max_width).
 * Чужие и уже уменьшаемые адреса не трогаем.
 */
export function drawerThumbUrl(url) {
  try {
    const parsed = new URL(url, 'https://mudaroba.com')
    if (!/\/proxy-image\/?$/.test(parsed.pathname)) return url
    const source = new URL(parsed.searchParams.get('url') || '')
    if (source.hostname !== 'cdn.mudaroba.com') return url
    const path = decodeURIComponent(source.pathname.replace(/^\/+/, ''))
    if (!path) return url
    return `/api/catalog/proxy-media/?path=${encodeURIComponent(path)}&max_width=192`
  } catch {
    return url
  }
}

/**
 * open(payload, pathname): payload = { item, total, trigger } — позиция и сумма из ответа сервера
 * (чего в ответе нет, того нет и в панели), trigger — кнопка, на которую вернётся фокус.
 */
export const addedToRequestStore = createStore((set) => ({
  isOpen: false,
  payload: null,
  open: (payload, pathname) => {
    if (isCartPath(pathname)) return
    set({ isOpen: true, payload: payload || {} })
  },
  // payload остаётся: панель доигрывает уход с прежним содержимым
  close: () => set({ isOpen: false }),
}))
