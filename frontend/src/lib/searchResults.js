// Страница результатов поиска (/search): запросы товаров по страницам и склейка
// «Показать ещё». Бэкенд сортирует по точности совпадения (docs/PRODUCT_SEARCH.md).

export const SEARCH_PAGE_SIZE = 24

export function searchProductParams(query, page = 1) {
  return {
    search: query,
    page_size: SEARCH_PAGE_SIZE,
    view: 'card',
    include_facets: false,
    ...(page > 1 ? { page } : {}),
  }
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
