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
