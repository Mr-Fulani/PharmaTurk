/**
 * Окно подтверждения в стиле сайта вместо системного confirm() браузера
 * (components/ConfirmDialog.tsx, смонтировано один раз в _app.tsx).
 * askConfirm({ title, lines, acceptLabel, declineLabel }) → Promise<boolean>.
 */
import { createStore } from 'zustand/vanilla'

export const confirmDialogStore = createStore((set, get) => ({
  request: null,
  ask: (request) =>
    new Promise((resolve) => {
      // Новый вопрос поверх неотвеченного: прежний считается отказом
      get().request?.resolve(false)
      set({ request: { ...request, resolve } })
    }),
  answer: (accepted) => {
    const request = get().request
    if (!request) return
    set({ request: null })
    request.resolve(Boolean(accepted))
  },
}))

export const askConfirm = (request) => confirmDialogStore.getState().ask(request)

/**
 * Что спросить у покупателя, когда поставщик при добавлении сообщил другую цену или меньшее
 * количество (ответ 409 от /orders/cart/add). Оба факта — в одном вопросе.
 * null — спрашивать нечего, ошибка показывается как есть.
 */
export function addConflictOffer(conflict) {
  const codes = new Set([conflict?.code, ...(conflict?.issues || []).map((issue) => issue.code)])
  const available = Number(conflict?.verification?.available_quantity)
  const price = conflict?.verification?.public_price
  const currency = conflict?.verification?.public_currency || ''
  const offer = {}
  if (codes.has('source_quantity_changed') && Number.isInteger(available) && available > 0) {
    offer.quantity = available
  }
  if (codes.has('source_price_changed') && price != null && currency) {
    offer.price = String(price)
    offer.currency = currency
  }
  return Object.keys(offer).length ? offer : null
}

/** Поля повторного запроса /orders/cart/add после согласия покупателя. */
export function addConflictRetryParams(offer) {
  const params = {}
  if (offer.quantity) params.quantity = String(offer.quantity)
  if (offer.price) {
    params.acknowledged_price = offer.price
    params.acknowledged_currency = offer.currency
  }
  return params
}
