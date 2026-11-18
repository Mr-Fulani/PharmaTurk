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

/**
 * Позиция ждёт проверки поставщика: её только что добавили, сервер ещё не сверял цену и наличие
 * (verification_status «not_checked», is_payable false). Проверка идёт только на странице /cart;
 * из панели её не запускаем — это запросы к поставщикам. Количество у такой позиции сервер
 * менять разрешает (/orders/cart/<id>/update на статус не смотрит), это не «нет в наличии».
 */
export function isAwaitingCheck(item) {
  return item?.is_payable === false && item?.verification_status === 'not_checked'
}

/**
 * Сумма заявки для панели — только из чисел сервера. total_amount / final_amount сервера не
 * включают позиции, ждущие проверки, поэтому их серверные total прибавляются: иначе сумма не
 * сходится со списком. С промокодом так считать нельзя (скидка посчитана от неполной суммы) —
 * тогда суммы нет, пока позиции не проверены. Позиции, исключённые по настоящей причине
 * (нет в наличии и т. п.), в сумму не входят, как и у сервера.
 */
export function requestTotal(cart) {
  if (!cart?.currency) return null
  const amount = cart.final_amount ?? cart.total_amount
  const base = Number(amount)
  if (!Number.isFinite(base)) return null
  const awaiting = (Array.isArray(cart.items) ? cart.items : []).filter(isAwaitingCheck)
  if (!awaiting.length) return base > 0 ? { amount, currency: cart.currency } : null
  if (cart.promo_code) return null
  let value = base
  for (const item of awaiting) {
    const total = Number(item.total)
    if (!Number.isFinite(total)) return null
    value += total
  }
  value = Math.round(value * 100) / 100
  return value > 0 ? { amount: value, currency: cart.currency } : null
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
