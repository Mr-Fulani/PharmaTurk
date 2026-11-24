// Применимость автозапчасти: подписи периода выпуска и мощности для блока карточки.

const pad = (month) => String(month).padStart(2, '0')

const point = (year, month) => (year ? (month ? `${pad(month)}.${year}` : String(year)) : '')

/**
 * Период выпуска: «03.2012 – 10.2018», «с 07.2012» (выпускается или год окончания неизвестен), «».
 */
export function formatFitmentPeriod(row, locale = 'ru') {
  const start = point(row?.year_from, row?.month_from)
  const end = point(row?.year_to, row?.month_to)
  if (start && end) return `${start} – ${end}`
  if (start) return locale === 'en' ? `from ${start}` : `с ${start}`
  if (end) return locale === 'en' ? `until ${end}` : `до ${end}`
  return ''
}

/** Мощность: «135 кВт / 184 л. с.», «135 kW / 184 hp», «». */
export function formatFitmentPower(row, locale = 'ru') {
  const kw = row?.power_kw ? `${row.power_kw} ${locale === 'en' ? 'kW' : 'кВт'}` : ''
  const hp = row?.power_hp ? `${row.power_hp} ${locale === 'en' ? 'hp' : 'л. с.'}` : ''
  return [kw, hp].filter(Boolean).join(' / ')
}

/** Модели марки одной строкой: первые `limit`, остальные — «и ещё N». */
export function summarizeModels(models, limit = 6, locale = 'ru') {
  const list = Array.isArray(models) ? models.filter(Boolean) : []
  if (list.length <= limit) return list.join(', ')
  const rest = list.length - limit
  return `${list.slice(0, limit).join(', ')} ${locale === 'en' ? `and ${rest} more` : `и ещё ${rest}`}`
}
