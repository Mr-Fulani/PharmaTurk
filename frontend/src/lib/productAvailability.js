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

// Google требует у Product (и Drug — его подтипа) хотя бы offers, review или aggregateRating:
// без них 222 лекарства в Search Console были «недопустимым значением» (25.10.2026). Цену в
// разметку лекарств не ставим (решение владельца), поэтому такую разметку не выводим вовсе.
export function shouldPublishProductSchema({ type, hasOffer, hasRating }) {
  if (type !== 'Product' && type !== 'Drug') return true
  return Boolean(hasOffer || hasRating)
}

// Google: sku не длиннее 50 символов и без пробелов. Короткий slug не трогаем, чтобы не
// менять идентификатор уже проиндексированных товаров; длинный заменяем на тип + id.
export function resolveSchemaSku({ slug, productType, id }) {
  const value = String(slug || '')
  if (value && value.length <= 50 && !/\s/.test(value)) return value
  return `${productType}-${id}`
}

// Условия страницы /returns: 14 дней с момента получения, возврат почтой, обратную
// доставку оплачивает покупатель (магазин берёт её на себя только при браке).
export const SCHEMA_RETURN_POLICY = {
  '@type': 'MerchantReturnPolicy',
  applicableCountry: ['RU', 'BY', 'GE', 'TR', 'GB', 'US'],
  returnPolicyCategory: 'https://schema.org/MerchantReturnFiniteReturnWindow',
  merchantReturnDays: 14,
  returnMethod: 'https://schema.org/ReturnByMail',
  returnFees: 'https://schema.org/ReturnFeesCustomerResponsibility',
}

// Платный доступ к источнику (лимит Web Unlocker FLO) исчерпан или приостановлен.
// Заказ — заявка менеджеру, онлайн-оплаты нет: покупку не блокируем, цену уточнит
// менеджер.
export const MANAGER_PRICE_REFRESH_ERROR = 'paid_access_unavailable'

export function sourceRefreshNeedsManagerPrice(state) {
  return state?.status === 'failed' && state.error_code === MANAGER_PRICE_REFRESH_ERROR
}

export function sourceRefreshBlocksPurchase(state) {
  return state?.status === 'failed' && !sourceRefreshNeedsManagerPrice(state)
}
