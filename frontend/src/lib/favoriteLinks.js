export function buildFavoriteProductHref(baseHref, variantSlug) {
  const normalizedVariantSlug = String(variantSlug || '').trim()
  if (!normalizedVariantSlug) return baseHref

  const separator = baseHref.includes('?') ? '&' : '?'
  return `${baseHref}${separator}active_variant_slug=${encodeURIComponent(normalizedVariantSlug)}`
}

export function matchesFavoriteSlug(storedVariantSlug, storedProductSlug, requestedSlug) {
  const requested = String(requestedSlug || '').trim().toLowerCase()
  if (!requested) return false

  const storedVariant = String(storedVariantSlug || '').trim().toLowerCase()
  if (storedVariant) return storedVariant === requested

  return String(storedProductSlug || '').trim().toLowerCase() === requested
}
