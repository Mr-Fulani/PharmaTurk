export function buildMaxShareText(url, title) {
  const safeUrl = typeof url === 'string' ? url.trim() : ''
  const safeTitle = typeof title === 'string' ? title.trim() : ''

  if (!safeTitle) return safeUrl
  if (!safeUrl) return safeTitle

  return `${safeTitle}\n${safeUrl}`
}

export function buildMaxShareUrl(url, title) {
  const text = buildMaxShareText(url, title)
  return `https://max.ru/:share?text=${encodeURIComponent(text)}`
}
