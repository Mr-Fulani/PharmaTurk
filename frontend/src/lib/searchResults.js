// Страница результатов поиска (/search): запросы товаров по страницам и склейка
// «Показать ещё». Бэкенд сортирует по точности совпадения (docs/PRODUCT_SEARCH.md).

export const SEARCH_PAGE_SIZE = 24

export const SEARCH_SORTS = ['relevance', 'price_asc', 'price_desc', 'newest']

// Фильтры страницы поиска из адреса: ?type=shoes&brand=12&available=1&sort=price_asc.
// Неизвестная сортировка и нечисловой бренд отбрасываются.
export function readSearchFilters(query) {
  const one = (value) => (Array.isArray(value) ? value[0] : value) || ''
  const brand = Number.parseInt(one(query?.brand), 10)
  const sort = one(query?.sort)
  return {
    type: one(query?.type),
    brand: Number.isFinite(brand) && brand > 0 ? brand : null,
    available: one(query?.available) === '1',
    sort: SEARCH_SORTS.includes(sort) && sort !== 'relevance' ? sort : 'relevance',
  }
}

export function hasSearchFilters(filters) {
  return Boolean(filters && (filters.type || filters.brand || filters.available))
}

// Адрес страницы поиска с фильтрами; пустые значения в адрес не попадают.
export function searchPageQuery(query, filters) {
  return {
    query,
    ...(filters.type ? { type: filters.type } : {}),
    ...(filters.brand ? { brand: String(filters.brand) } : {}),
    ...(filters.available ? { available: '1' } : {}),
    ...(filters.sort && filters.sort !== 'relevance' ? { sort: filters.sort } : {}),
  }
}

export function searchProductParams(query, page = 1, filters = null) {
  return {
    search: query,
    page_size: SEARCH_PAGE_SIZE,
    view: 'card',
    include_facets: false,
    ...(filters?.type ? { product_type: filters.type } : {}),
    ...(filters?.brand ? { brand_id: filters.brand } : {}),
    ...(filters?.available ? { is_available: true } : {}),
    ...(filters?.sort && filters.sort !== 'relevance' ? { ordering: filters.sort } : {}),
    // С первой страницей: разделы и бренды найденного (один раз) и учёт запроса (админка
    // «Поисковые запросы») — только без фильтров, иначе в учёт попало бы суженное число.
    // Подсказки в шапке этих параметров не шлют.
    ...(page > 1
      ? { page }
      : { search_facets: 1, ...(filters?.type || filters?.brand || filters?.available ? {} : { search_source: 'page' }) }),
  }
}

// Разделы и бренды найденного (бэкенд: search_facets) → {types, brands}; мусор отбрасывается.
export function readSearchFacets(data) {
  const facets = data && !Array.isArray(data) ? data.search_facets : null
  const list = (value) => (Array.isArray(value) ? value : [])
  return {
    types: list(facets?.types).filter((row) => row && typeof row.value === 'string' && row.count > 0),
    brands: list(facets?.brands).filter((row) => row && Number.isFinite(row.id) && row.name && row.count > 0),
  }
}

export function searchServiceParams(query, page = 1) {
  return {
    search: query,
    page_size: SEARCH_PAGE_SIZE,
    view: 'card',
    ...(page > 1 ? { page } : {}),
  }
}

// Что догружает «Показать ещё»: сначала товары, потом услуги (они идут в конце списка).
export function nextSearchSource(products, services) {
  if (products.hasMore) return 'products'
  if (services.hasMore) return 'services'
  return null
}

// Ответ DRF ({count, next, results}) или старый массив → {results, count, hasMore}.
export function readSearchPage(data) {
  if (Array.isArray(data)) {
    return { results: data, count: data.length, hasMore: false }
  }
  const results = Array.isArray(data?.results) ? data.results : []
  const count = Number.isFinite(data?.count) ? data.count : results.length
  return { results, count, hasMore: Boolean(data?.next) }
}

// Следующая страница без повторов (на случай, если каталог сдвинулся между запросами).
export function appendSearchPage(existing, incoming) {
  const seen = new Set(existing.map((item) => item?.id))
  return [...existing, ...incoming.filter((item) => !seen.has(item?.id))]
}

// Нашлось не по запросу как есть (бэкенд: search_info) → {mode, query} или null.
// mode: layout — другая раскладка, translit — латиницей, typo — исправлена опечатка,
// partial — запрос целиком ничего не нашёл, часть слов убрана.
export function readSearchInfo(data) {
  const info = data && !Array.isArray(data) ? data.search_info : null
  if (!info || typeof info.query !== 'string' || !info.query) return null
  if (!['layout', 'translit', 'typo', 'partial'].includes(info.mode)) return null
  return { mode: info.mode, query: info.query }
}
