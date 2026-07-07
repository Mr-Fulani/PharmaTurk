// Хелперы страницы бренда: единая сборка параметров запроса товаров
// для gSSP и клиента (одинаковые параметры = одинаковый ключ запроса,
// что позволяет не дублировать SSR-загрузку на клиенте).

const GENDER_RELEVANT_CATEGORY_SLUGS = new Set([
  'clothing',
  'shoes',
  'underwear',
  'headwear',
  'islamic-clothing',
  'perfumery',
  'accessories',
  'jewelry',
])

export function buildBrandProductsParams(filters, page, pageSize) {
  const params = {
    page,
    page_size: pageSize,
  }
  if (filters.categorySlugs?.length > 0) params.category_slug = filters.categorySlugs.join(',')
  else if (filters.categories?.length > 0) params.category_id = filters.categories
  if (filters.genders?.length > 0) params.gender = filters.genders.join(',')
  if (filters.priceMin !== undefined) params.price_min = filters.priceMin
  if (filters.priceMax !== undefined) params.price_max = filters.priceMax
  if (filters.inStock) params.in_stock = true
  if (filters.isNew) params.is_new = true
  if (filters.sortBy) params.ordering = filters.sortBy
  return params
}

export function brandProductsRequestKey(slug, params) {
  return JSON.stringify([slug, params])
}

export function shouldShowGenderFilter(categorySlugs) {
  return (categorySlugs || []).some((slug) =>
    GENDER_RELEVANT_CATEGORY_SLUGS.has(String(slug || '').trim().toLowerCase().replace(/_/g, '-'))
  )
}
