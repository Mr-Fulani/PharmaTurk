/** Единое отображение публичных денежных сумм без изменения их значения. */

const CENT_CURRENCIES = new Set(['USD', 'EUR', 'USDT'])

export function parseMoneyNumber(value: string | number | null | undefined): number | null {
  if (value === null || typeof value === 'undefined') return null
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  let normalized = String(value).trim().replace(/[\s\u00a0\u202f]/g, '').replace(/[^0-9.,+-]/g, '')
  if (!normalized || !/[0-9]/.test(normalized)) return null

  const lastComma = normalized.lastIndexOf(',')
  const lastDot = normalized.lastIndexOf('.')
  if (lastComma >= 0 && lastDot >= 0) {
    const decimalSeparator = lastComma > lastDot ? ',' : '.'
    const thousandsSeparator = decimalSeparator === ',' ? '.' : ','
    normalized = normalized.split(thousandsSeparator).join('').replace(decimalSeparator, '.')
  } else {
    const separator = lastComma >= 0 ? ',' : lastDot >= 0 ? '.' : null
    if (separator) {
      const groups = normalized.split(separator)
      const looksLikeThousands = groups.length > 1 && groups.slice(1).every((group) => group.length === 3)
      normalized = looksLikeThousands ? groups.join('') : normalized.replace(separator, '.')
    }
  }
  const num = Number(normalized)
  return Number.isFinite(num) ? num : null
}

export function formatPrice(
  value: string | number | null | undefined,
  currency?: string | null,
  locale?: string | null,
): string | null {
  return formatMoney(value, currency, locale)
}

/** Единое отображение денег во всех публичных интерфейсах. */
export function formatMoney(
  value: string | number | null | undefined,
  currency?: string | null,
  locale?: string | null,
): string | null {
  if (value === null || value === undefined) return null
  const num = parseMoneyNumber(value)
  if (num === null) return String(value)
  const normalizedCurrency = (currency || '').toUpperCase()
  const fractionDigits = CENT_CURRENCIES.has(normalizedCurrency) ? 2 : 0
  const numberLocale = (locale || '').toLowerCase().startsWith('ru') ? 'ru-RU' : 'en-US'
  return new Intl.NumberFormat(numberLocale, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
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
  const match = trimmed.match(/^(.+?)\s*([A-Za-z]{3,5})$/)
  if (match) {
    const parsed = parseMoneyNumber(match[1])
    return { price: parsed ?? match[1], currency: match[2].toUpperCase() }
  }
  return { price: parseMoneyNumber(trimmed) ?? trimmed, currency: null as string | null }
}
