export function buildFavoriteProductHref(baseHref, variantSlug, chosenSize) {
  const normalizedVariantSlug = String(variantSlug || '').trim()
  const normalizedChosenSize = String(chosenSize || '').trim()
  if (!normalizedVariantSlug && !normalizedChosenSize) return baseHref

  const separator = baseHref.includes('?') ? '&' : '?'
  const params = new URLSearchParams()
  if (normalizedVariantSlug) params.set('active_variant_slug', normalizedVariantSlug)
  if (normalizedChosenSize) params.set('favorite_size', normalizedChosenSize)
  return `${baseHref}${separator}${params.toString()}`
}

export function matchesFavoriteSlug(storedVariantSlug, storedProductSlug, requestedSlug) {
  const requested = String(requestedSlug || '').trim().toLowerCase()
  if (!requested) return false

  const storedVariant = String(storedVariantSlug || '').trim().toLowerCase()
  if (storedVariant) return storedVariant === requested

  return String(storedProductSlug || '').trim().toLowerCase() === requested
}
