/**
 * Форматирование цен: Math.ceil + точка как разделитель тысяч.
 * 80987.97 → "80.988", 1234 → "1.234"
 */

function parseNumber(value: string | number | null | undefined): number | null {
  if (value === null || typeof value === 'undefined') return null
  const normalized = String(value).replace(',', '.').replace(/[^0-9.]/g, '')
  if (!normalized) return null
  const num = Number(normalized)
  return Number.isFinite(num) ? num : null
}

export function formatPrice(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined) return null
  const num = parseNumber(value)
  if (num === null) return String(value)
  return Math.ceil(num)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}
