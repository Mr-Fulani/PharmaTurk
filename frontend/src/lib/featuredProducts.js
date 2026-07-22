function normalizeProductType(productType) {
  return String(productType || 'medicines').trim().toLowerCase().replace(/_/g, '-')
}

function normalizeSlug(slug) {
  return String(slug || '').trim().toLowerCase().replace(/_/g, '-')
}

/**
 * Removes duplicate logical products from mixed API responses.
 *
 * A domain row can have a different local id than its canonical Product row.
 * Slug is the public identity fallback; base_product_id connects rows even when
 * a legacy slug collision caused their slugs to differ.
 */
export function deduplicateFeaturedProducts(products) {
  const result = []
  const seenSlugs = new Set()
  const seenCanonicalIds = new Set()
  const seenUnlinkedIds = new Set()

  for (const product of products || []) {
    if (!product) continue

    const productType = normalizeProductType(product.product_type)
    const slug = normalizeSlug(product.slug)
    const slugKey = slug ? `${productType}:slug:${slug}` : null
    const baseProductId = product.base_product_id
    const rawId = product.id
    const canonicalKey = baseProductId != null
      ? `${productType}:id:${baseProductId}`
      : null
    const rawKey = rawId != null ? `${productType}:id:${rawId}` : null

    const duplicatesBySlug = slugKey != null && seenSlugs.has(slugKey)
    const duplicatesByBase = canonicalKey != null && (
      seenCanonicalIds.has(canonicalKey) || seenUnlinkedIds.has(canonicalKey)
    )
    const duplicatesByLinkedRow = canonicalKey == null && rawKey != null && seenCanonicalIds.has(rawKey)

    if (duplicatesBySlug || duplicatesByBase || duplicatesByLinkedRow) continue

    result.push(product)
    if (slugKey) seenSlugs.add(slugKey)
    if (canonicalKey) seenCanonicalIds.add(canonicalKey)
    else if (rawKey) seenUnlinkedIds.add(rawKey)
  }

  return result
}
