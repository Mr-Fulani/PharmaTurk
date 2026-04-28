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
 *
 * Синхронизация с серверным canonical resolve: `backend/apps/catalog/services/product_resolve.py`
 * (константы BASE_PRODUCT_TYPES и TYPES_NEEDING_PATH).
 */
export const BASE_PRODUCT_TYPES = [
  'medicines',
  'supplements',
  'medical-equipment',
  'furniture',
  'tableware',
  'accessories',
  'books',
  'perfumery',
  'sports',
  'auto-parts',
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
export const TYPES_NEEDING_PATH = ['clothing', 'shoes', 'electronics', 'jewelry', 'uslugi', 'headwear', 'underwear', 'islamic-clothing'] as const

const normalizeProductType = (productType?: string | null) =>
  (productType || '').toString().trim().replace(/_/g, '-')

export function isBaseProductType(productType?: string | null): boolean {
  const normalized = normalizeProductType(productType)
  return Boolean(normalized && BASE_PRODUCT_TYPES.includes(normalized as BaseProductType))
}

/** Нужен ли type в URL (clothing, shoes, electronics). */
export function needsTypeInPath(productType?: string | null): boolean {
  const normalized = normalizeProductType(productType)
  return Boolean(normalized && TYPES_NEEDING_PATH.includes(normalized as (typeof TYPES_NEEDING_PATH)[number]))
}

/**
 * ID для API избранного (add/remove/check и сопоставление со списком /favorites).
 * Для headwear / underwear / islamic-clothing / books в ответе избранного id = shadow Product,
 * а в листингах карточка часто несёт доменный id — без base совпадение ломается.
 */
const FAVORITE_API_USES_BASE_PRODUCT_ID = new Set([
  'headwear',
  'underwear',
  'islamic-clothing',
  'books',
])

type ProductIdentityLike = {
  id: number | string
  base_product_id?: number | null
  slug?: string | null
}

export function favoriteApiProductId(
  product: { id: number; base_product_id?: number | null },
  productType?: string | null
): number {
  const norm = normalizeProductType(productType)
  const base = product.base_product_id
  if (base != null && FAVORITE_API_USES_BASE_PRODUCT_ID.has(norm)) {
    return base
  }
  return product.id
}

/**
 * Стабильный ключ товара для mixed-списков на фронте.
 * Одного product.id недостаточно: id могут пересекаться между разными категориями/моделями.
 */
export function buildProductIdentityKey(
  product: ProductIdentityLike,
  productType?: string | null
): string {
  const norm = normalizeProductType(productType) || 'medicines'
  const safeId = favoriteApiProductId(
    {
      id: Number(product.id),
      base_product_id: product.base_product_id,
    },
    norm
  )
  const slug = (product.slug || '').toString().trim().toLowerCase()
  return slug ? `${norm}:${safeId}:${slug}` : `${norm}:${safeId}`
}
