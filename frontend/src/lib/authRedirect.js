export function sanitizeNextPath(next) {
  if (typeof next !== 'string') return null
  if (!next.startsWith('/')) return null
  if (next.startsWith('//')) return null
  return next
}

export function buildAuthRedirectQuery(nextPath) {
  const safeNext = sanitizeNextPath(nextPath)
  return safeNext ? { next: safeNext } : {}
}
