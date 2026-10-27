/**
 * Ответ «В заявку», когда товар закончился у поставщика: 400 с `available` ≤ 0
 * (orders/views.py, CartViewSet.add). Карточка могла показывать старое «в наличии»
 * до сверки с поставщиком — вместо окна с ошибкой переключаем её в «Нет в наличии».
 * Ответы проверки поставщика (с `code`) сюда не относятся.
 */
export function isSoldOutCartError(err) {
  const response = err && err.response
  if (!response || response.status !== 400) return false
  const data = response.data
  if (!data || typeof data !== 'object' || data.code) return false
  if (data.available === undefined || data.available === null) return false
  const available = Number(data.available)
  return Number.isFinite(available) && available <= 0
}
