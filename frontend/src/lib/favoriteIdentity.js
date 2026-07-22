const toPositiveId = (value) => {
  const id = Number(value)
  return Number.isFinite(id) && id > 0 ? id : null
}

/**
 * Public Product.id is the unambiguous ID accepted by the favorites API.
 * Domain-table primary keys can overlap with unrelated Product rows, so a
 * linked base_product_id must always win when the card exposes one.
 */
export function favoriteApiProductId(product) {
  const publicId = toPositiveId(product?.base_product_id)
  if (publicId !== null) return publicId

  return toPositiveId(product?.id) ?? Number(product?.id)
}

/** Match a refreshed favorite row to a catalog card across public/domain IDs. */
export function matchesFavoriteProductIdentity(favoriteProduct, productId, productSlug) {
  const wantedId = toPositiveId(productId)
  const favoriteId = toPositiveId(favoriteProduct?.id)
  const favoriteBaseId = toPositiveId(favoriteProduct?.base_product_id)

  if (wantedId !== null && (favoriteId === wantedId || favoriteBaseId === wantedId)) {
    return true
  }

  const wantedSlug = String(productSlug || '').trim().toLowerCase()
  if (!wantedSlug) return false

  return String(favoriteProduct?.slug || '').trim().toLowerCase() === wantedSlug
}
