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
