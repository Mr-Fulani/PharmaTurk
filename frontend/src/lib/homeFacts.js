/**
 * Блок «Как работает Mudaroba» на главной (ТЗ «SEO и видимость в ИИ-поиске», задача 3).
 * Числа берутся из ответов API, которые главная уже получает: категории и бренды.
 */

// Услуги — не товары каталога
const NON_PRODUCT_CATEGORY_SLUGS = new Set(['uslugi'])

/** Сколько товаров в корневых категориях (без услуг). */
export function countCatalogProducts(categories) {
  let total = 0
  for (const category of categories || []) {
    if (NON_PRODUCT_CATEGORY_SLUGS.has(category?.slug)) continue
    const count = Number(category?.products_count)
    if (Number.isFinite(count) && count > 0) total += count
  }
  return total
}

/** Сколько брендов, у которых есть товары. */
export function countBrandsWithProducts(data) {
  const brands = Array.isArray(data) ? data : (data?.results || [])
  return brands.filter((brand) => Number(brand?.products_count) > 0).length
}

/**
 * Число для текста «больше N товаров»: вниз до тысяч (27 511 → 27 000).
 * Меньше тысячи — 0: фраза «больше N» с точным маленьким числом не нужна, блок
 * тогда показывает текст без чисел.
 */
export function roundDownToThousands(value) {
  const number = Number(value)
  if (!Number.isFinite(number) || number < 1000) return 0
  return Math.floor(number / 1000) * 1000
}

/** 27000 → «27 000» (ru, неразрывный пробел) / «27,000» (en); одинаково на сервере и в браузере. */
export function formatCount(value, locale) {
  const separator = locale === 'en' ? ',' : ' '
  return String(Math.trunc(Number(value) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, separator)
}
