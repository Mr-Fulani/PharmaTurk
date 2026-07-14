/** Единое отображение публичных денежных сумм без изменения их значения. */

function parseNumber(value: string | number | null | undefined): number | null {
  if (value === null || typeof value === 'undefined') return null
  const normalized = String(value).replace(',', '.').replace(/[^0-9.]/g, '')
  if (!normalized) return null
  const num = Number(normalized)
  return Number.isFinite(num) ? num : null
}

export function formatPrice(value: string | number | null | undefined): string | null {
  return formatMoney(value)
}

/** Денежные суммы корзины/заказа без округления вверх. */
export function formatMoney(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined) return null
  const num = parseNumber(value)
  if (num === null) return String(value)
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(num)
}

export function parsePriceWithCurrency(value?: string | number | null) {
  if (value === null || typeof value === 'undefined') {
    return { price: null as string | number | null, currency: null as string | null }
  }
  if (typeof value === 'number') {
    return { price: value, currency: null as string | null }
  }
  const trimmed = value.trim()
  const match = trimmed.match(/^([0-9]+(?:[.,][0-9]+)?)\s*([A-Za-z]{3,5})$/)
  if (match) {
    return { price: match[1].replace(',', '.'), currency: match[2].toUpperCase() }
  }
  return { price: trimmed, currency: null as string | null }
}
