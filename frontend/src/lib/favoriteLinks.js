export function buildFavoriteProductHref(baseHref, variantSlug) {
  const normalizedVariantSlug = String(variantSlug || '').trim()
  if (!normalizedVariantSlug) return baseHref

  const separator = baseHref.includes('?') ? '&' : '?'
  return `${baseHref}${separator}active_variant_slug=${encodeURIComponent(normalizedVariantSlug)}`
}
