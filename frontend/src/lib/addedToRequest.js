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

/** Сколько секунд на месте удалённой позиции стоит «Удалено · Вернуть», мс. */
export const ADDED_DRAWER_UNDO_MS = 6000

/**
 * Порядок позиций в панели: только что добавленная — первой, остальные — как стояли
 * (previousIds), новые — в порядке сервера. Сервер при смене количества обновляет updated_at,
 * поэтому «добавленную» помним по id с момента открытия, а не ищем заново.
 */
export function orderDrawerItems(items, addedId, previousIds = []) {
  const rank = (item) => {
    if (item.id === addedId) return -1
    const index = previousIds.indexOf(item.id)
    return index === -1 ? Infinity : index
  }
  return (Array.isArray(items) ? items : [])
    .map((item, index) => ({ item, index }))
    .sort((left, right) => (rank(left.item) - rank(right.item)) || (left.index - right.index))
    .map((entry) => entry.item)
}

/**
 * Строки списка: позиции заявки и, на прежних местах, только что удалённые («Удалено · Вернуть»).
 * removed = [{ key, item, index }] — index строки в момент удаления; у такой строки entry — эта запись.
 */
export function drawerRows(items, removed = []) {
  const rows = (Array.isArray(items) ? items : []).map((item) => ({ key: `item-${item.id}`, item, entry: null }))
  for (const entry of [...removed].sort((left, right) => left.index - right.index)) {
    rows.splice(Math.min(entry.index, rows.length), 0, { key: entry.key, item: entry.item, entry })
  }
  return rows
}

/** «Вернуть» удалённую позицию = добавить тот же товар, размер и количество (тело /orders/cart/add). */
export function undoAddParams(item) {
  const params = { product_id: String(item.product), quantity: String(item.quantity) }
  if (item.chosen_size) params.size = item.chosen_size
  return params
}

/**
 * open(payload, pathname): payload = { cart, addedId, trigger } — заявка из ответа сервера
 * (чего в ответе нет, того нет и в панели), id добавленной позиции и кнопка, на которую вернётся фокус.
 * engaged — человек занялся панелью (навёл, коснулся, прокрутил, перешёл с клавиатуры):
 * автозакрытие больше не срабатывает до следующего открытия.
 */
export const addedToRequestStore = createStore((set) => ({
  isOpen: false,
  engaged: false,
  payload: null,
  open: (payload, pathname) => {
    if (isCartPath(pathname)) return
    set({ isOpen: true, engaged: false, payload: payload || {} })
  },
  engage: () => set({ engaged: true }),
  // payload остаётся: панель доигрывает уход с прежним содержимым
  close: () => set({ isOpen: false }),
}))
