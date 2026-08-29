export function normalizeSimilarProductType(value) {
  return String(value || '').trim().replace(/_/g, '-').toLowerCase()
}

export function sameSimilarProductType(candidateType, expectedType) {
  if (!candidateType) return true
  return normalizeSimilarProductType(candidateType) === normalizeSimilarProductType(expectedType)
}

export function getSimilarFallbackEndpoint(productType) {
  const normalized = normalizeSimilarProductType(productType)
  if (normalized === 'supplements') return '/catalog/supplements/products'
  if (normalized === 'jewelry') return '/catalog/jewelry/products'
  if (normalized === 'clothing') return '/catalog/clothing/products'
  if (normalized === 'shoes') return '/catalog/shoes/products'
  if (normalized === 'electronics') return '/catalog/electronics/products'
  return '/catalog/products'
}

export function buildSimilarFallbackParams({ productType, categoryId, limit }) {
  const normalized = normalizeSimilarProductType(productType)
  return {
    limit: Number(limit) + 1,
    ordering: '-created_at',
    view: 'card',
    product_type: normalized.replace(/-/g, '_'),
    ...(categoryId ? { category_id: categoryId } : {}),
  }
}
