/**
 * Базовые типы товаров (base product types).
 *
 * Синхронизировать с backend: apps/catalog/models.TOP_CATEGORY_SLUG_CHOICES
 * (исключая clothing, shoes, electronics — у них отдельные модели и эндпоинты).
 *
 * Логика:
 * - Базовые типы: товары через /api/catalog/products/, короткий URL /product/slug.
 * - Небазовые: clothing, shoes, electronics — полный URL /product/{type}/slug.
 *
 * Используется для:
 * - isBaseProductType() — нужен ли type в пути, как передавать в API (productId vs variant).
 * - ProductCard, cart getProductLink, favorites и т.д.
 *
 * При добавлении нового типа в backend — добавить сюда, если он идёт через generic Product.
 */
export const BASE_PRODUCT_TYPES = [
  'medicines',
  'supplements',
  'medical-equipment',
  'furniture',
  'tableware',
  'accessories',
  'underwear',
  'headwear',
  'books',
  'perfumery',
  'uslugi',
  'sports',
  'auto-parts',
  'islamic-clothing',
  'incense',
  'bags',
  'watches',
  'cosmetics',
  'toys',
  'home-textiles',
  'stationery',
  'pet-supplies',
] as const

export type BaseProductType = (typeof BASE_PRODUCT_TYPES)[number]

/** Типы с отдельными моделями — всегда требуют type в URL. */
export const TYPES_NEEDING_PATH = ['clothing', 'shoes', 'electronics', 'jewelry'] as const

export function isBaseProductType(productType?: string | null): boolean {
  return Boolean(productType && BASE_PRODUCT_TYPES.includes(productType as BaseProductType))
}

/** Нужен ли type в URL (clothing, shoes, electronics). */
export function needsTypeInPath(productType?: string | null): boolean {
  return Boolean(productType && TYPES_NEEDING_PATH.includes(productType as (typeof TYPES_NEEDING_PATH)[number]))
}
