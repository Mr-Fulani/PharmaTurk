export function normalizeMedicineSlug(value) {
  const raw = Array.isArray(value) ? value[0] : value
  if (typeof raw !== 'string') return ''
  const slug = raw.trim()
  if (!slug || slug.length > 500 || /[/?#\\]/.test(slug)) return ''
  return slug
}

export function shouldPollMedicineMarketCheck(status) {
  return status === 'pending' || status === 'running'
}

export function selectMarketCheckDisplayPrice(payload) {
  const displayPrice = payload?.display_price
  if (displayPrice?.amount != null && String(displayPrice.currency || '').trim()) {
    return displayPrice
  }
  const sourcePrice = payload?.price
  if (sourcePrice?.amount != null && String(sourcePrice.currency || '').trim()) {
    return sourcePrice
  }
  return null
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
