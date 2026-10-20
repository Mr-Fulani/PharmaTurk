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
    // Компактные карточки, как в категориях: без полных инструкций лекарств
    // и вложенных бренда/категории (ответ бренда лекарств 0.8 МБ → ~30 КБ).
    view: 'card',
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

// Текст описания бренда без HTML для meta description. У брендов-производителей
// лекарств описания нет (getLocalizedBrandDescription → null) — раньше здесь
// падал SSR и страница отдавала 500.
export function brandDescriptionText(description) {
  return String(description || '').replace(/<[^>]*>/g, ' ')
}

export function shouldShowGenderFilter(categorySlugs) {
  return (categorySlugs || []).some((slug) =>
    GENDER_RELEVANT_CATEGORY_SLUGS.has(String(slug || '').trim().toLowerCase().replace(/_/g, '-'))
  )
}
