export function normalizeMedicineSlug(value) {
  const raw = Array.isArray(value) ? value[0] : value
  if (typeof raw !== 'string') return ''
  const slug = raw.trim()
  if (!slug || slug.length > 500 || /[/?#\\]/.test(slug)) return ''
  return slug
}

export function buildMedicineHowToOrderHref(slug) {
  const normalized = normalizeMedicineSlug(slug)
  if (!normalized) return '/how-to-order-medicines'
  return `/how-to-order-medicines?medicine=${encodeURIComponent(normalized)}`
}

export function shouldPollMedicineMarketCheck(status) {
  return status === 'pending' || status === 'running'
}

const startRequests = new Map()

export function startMedicineMarketCheckSingleFlight(slug, starter) {
  const key = normalizeMedicineSlug(slug)
  if (!key) return Promise.reject(new Error('Invalid medicine slug'))
  const existing = startRequests.get(key)
  if (existing) return existing

  const request = Promise.resolve().then(starter)
  startRequests.set(key, request)
  const clear = () => {
    if (startRequests.get(key) === request) startRequests.delete(key)
  }
  request.then(clear, clear)
  return request
}

export function buildMedicineConsultMessage(product, marketCheck, pageUrl, locale = 'ru') {
  const details = [product?.name, product?.dosage_form, product?.volume]
    .map((value) => String(value || '').trim())
    .filter(Boolean)
    .join(', ')
  const price = marketCheck?.price
    ? `${marketCheck.price.amount} ${marketCheck.price.currency}`
    : ''
  const checkedAt = marketCheck?.last_success_at
    ? new Date(marketCheck.last_success_at).toISOString().slice(0, 10)
    : ''
  const english = String(locale || '').toLowerCase().startsWith('en')
  return [
    english
      ? `Hello! I need advice about this medicine: ${details || 'name not specified'}.`
      : `Здравствуйте! Нужна консультация по препарату: ${details || 'название не указано'}.`,
    price
      ? english
        ? `Reference price: ${price}${checkedAt ? ` (checked ${checkedAt})` : ''}.`
        : `Справочная цена: ${price}${checkedAt ? ` (проверено ${checkedAt})` : ''}.`
      : '',
    pageUrl ? `${english ? 'Product page' : 'Карточка'}: ${pageUrl}` : '',
  ].filter(Boolean).join('\n')
}

export function appendWhatsappText(baseUrl, text) {
  const rawUrl = String(baseUrl || '').trim()
  if (!rawUrl) return ''
  try {
    const url = new URL(rawUrl)
    url.searchParams.set('text', String(text || ''))
    return url.toString()
  } catch {
    return rawUrl
  }
}
