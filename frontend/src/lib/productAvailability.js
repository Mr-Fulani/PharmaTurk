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

// Страны доставки в разметке и Merchant Center (решение владельца 28.10.2026):
// Казахстан, Узбекистан, Азербайджан, Турция, ОАЭ, США и страны ЕС.
const EU_COUNTRIES = [
  'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE',
  'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE',
]
export const SCHEMA_SHIPPING_COUNTRIES = ['KZ', 'UZ', 'AZ', 'TR', 'AE', 'US', ...EU_COUNTRIES]

// Доставка 7–14 дней (сборка заказа 1–2 дня + в пути 6–12), 5 $ в валюте цены Offer:
// Google требует ту же валюту, что у price. Суммы по валютам — из resolve
// (shipping_rates, по курсу сайта); у мебели, лекарств и услуг их нет — без доставки.
export function buildSchemaShippingDetails(shippingRates, currency) {
  const value = shippingRates?.[String(currency || '').toUpperCase()]
  if (!value) return undefined
  const days = (minValue, maxValue) => ({ '@type': 'QuantitativeValue', minValue, maxValue, unitCode: 'DAY' })
  return {
    '@type': 'OfferShippingDetails',
    shippingRate: { '@type': 'MonetaryAmount', value: Number(value), currency: String(currency).toUpperCase() },
    shippingDestination: SCHEMA_SHIPPING_COUNTRIES.map((addressCountry) => ({ '@type': 'DefinedRegion', addressCountry })),
    deliveryTime: { '@type': 'ShippingDeliveryTime', handlingTime: days(1, 2), transitTime: days(6, 12) },
  }
}

// Все фото товара для Merchant Center (поле «изображения на предложение»): главное первым,
// без повторов, не больше 10.
export function buildSchemaImages(urls, max = 10) {
  return [...new Set((urls || []).filter(Boolean))].slice(0, max)
}

// Условия страницы /returns: 14 дней с момента получения, возврат почтой, обратную
// доставку оплачивает покупатель (магазин берёт её на себя только при браке).
// Страны — прежние и все страны доставки.
export const SCHEMA_RETURN_POLICY = {
  '@type': 'MerchantReturnPolicy',
  applicableCountry: [...new Set(['RU', 'BY', 'GE', 'TR', 'GB', 'US', ...SCHEMA_SHIPPING_COUNTRIES])],
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
