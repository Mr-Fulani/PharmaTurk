const SCHEMA_AVAILABILITY_BY_STATUS = {
  backorder: 'https://schema.org/BackOrder',
  preorder: 'https://schema.org/PreOrder',
  out_of_stock: 'https://schema.org/OutOfStock',
  discontinued: 'https://schema.org/Discontinued',
}

export function resolveSchemaAvailability({
  availabilityStatus,
  isAvailable,
  variantAvailable,
  variantStockQuantity,
}) {
  const explicit = SCHEMA_AVAILABILITY_BY_STATUS[String(availabilityStatus || '')]
  if (explicit) return explicit
  if (
    isAvailable === false ||
    variantAvailable === false ||
    variantStockQuantity === 0
  ) {
    return 'https://schema.org/OutOfStock'
  }
  return 'https://schema.org/InStock'
}

// Offer (цена + наличие) в JSON-LD только там, где товар реально можно купить.
// Медикаменты сайт не продаёт (дисклеймер на карточке, кнопки корзины нет) —
// Offer противоречил бы контенту страницы (YMYL).
export function canPublishSchemaOffer({ price, isMedicine, isSupplement, canAddToCart }) {
  if (!price || isMedicine) return false
  if (isSupplement && canAddToCart !== true) return false
  return true
}
