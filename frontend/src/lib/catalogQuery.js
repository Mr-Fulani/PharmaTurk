export function parseBrandIds(value) {
  return parseNumberList(value)
}

function queryValues(value) {
  const rawValues = Array.isArray(value) ? value : value == null ? [] : [value]
  return rawValues
    .flatMap((item) => String(item).split(','))
    .map((item) => item.trim())
    .filter(Boolean)
}

function parseNumberList(value) {
  const ids = queryValues(value)
    .map((item) => Number(item))
    .filter((item) => Number.isInteger(item) && item >= 0)

  return [...new Set(ids)]
}

function firstQueryValue(value) {
  return queryValues(value)[0]
}

function setList(query, key, values) {
  delete query[key]
  if (!values || values.length === 0) return
  query[key] = values.length === 1 ? String(values[0]) : values.map(String)
}

const FILTER_QUERY_KEYS = [
  'brand_id',
  'filter_category_id',
  'filter_category_slug',
  'subcategory_id',
  'subcategory_slug',
  'gender',
  'fragrance_type',
  'author_id',
  'genre_id',
  'publisher',
  'language',
  'price_min',
  'price_max',
  'in_stock',
  'is_new',
  'ordering',
]

export function parseCatalogFiltersQuery(query, defaults) {
  const attributes = {}
  for (const [key, value] of Object.entries(query)) {
    if (key.startsWith('attr_')) {
      const values = queryValues(value)
      if (values.length > 0) attributes[key.slice(5)] = values
    }
  }

  const priceMin = Number(firstQueryValue(query.price_min))
  const priceMax = Number(firstQueryValue(query.price_max))

  return {
    ...defaults,
    categories: parseNumberList(query.filter_category_id),
    categorySlugs: queryValues(query.filter_category_slug),
    brands: parseBrandIds(query.brand_id),
    brandSlugs: [],
    subcategories: parseNumberList(query.subcategory_id),
    subcategorySlugs: queryValues(query.subcategory_slug),
    genders: queryValues(query.gender),
    fragranceTypes: queryValues(query.fragrance_type),
    authorIds: parseNumberList(query.author_id),
    genreIds: parseNumberList(query.genre_id),
    publishers: queryValues(query.publisher),
    languages: queryValues(query.language),
    priceMin: Number.isFinite(priceMin) ? priceMin : undefined,
    priceMax: Number.isFinite(priceMax) ? priceMax : undefined,
    inStock: firstQueryValue(query.in_stock) === '1',
    isNew: firstQueryValue(query.is_new) === '1',
    sortBy: firstQueryValue(query.ordering) || defaults.sortBy,
    attributes,
  }
}

export function buildCatalogPageQuery(currentQuery, page, options = {}) {
  const nextQuery = { ...currentQuery }

  if (page <= 1) {
    delete nextQuery.page
  } else {
    nextQuery.page = String(page)
  }

  if (options.filters) {
    for (const key of FILTER_QUERY_KEYS) delete nextQuery[key]
    for (const key of Object.keys(nextQuery)) {
      if (key.startsWith('attr_')) delete nextQuery[key]
    }
    delete nextQuery.brand

    const filters = options.filters
    setList(nextQuery, 'brand_id', filters.brands)
    setList(nextQuery, 'filter_category_id', filters.categories)
    setList(nextQuery, 'filter_category_slug', filters.categorySlugs)
    setList(nextQuery, 'subcategory_id', filters.subcategories)
    setList(nextQuery, 'subcategory_slug', filters.subcategorySlugs)
    setList(nextQuery, 'gender', filters.genders)
    setList(nextQuery, 'fragrance_type', filters.fragranceTypes)
    setList(nextQuery, 'author_id', filters.authorIds)
    setList(nextQuery, 'genre_id', filters.genreIds)
    setList(nextQuery, 'publisher', filters.publishers)
    setList(nextQuery, 'language', filters.languages)

    if (Number.isFinite(filters.priceMin)) nextQuery.price_min = String(filters.priceMin)
    if (Number.isFinite(filters.priceMax)) nextQuery.price_max = String(filters.priceMax)
    if (filters.inStock) nextQuery.in_stock = '1'
    if (filters.isNew) nextQuery.is_new = '1'
    if (filters.sortBy && filters.sortBy !== 'name_asc') nextQuery.ordering = filters.sortBy

    for (const [key, values] of Object.entries(filters.attributes || {})) {
      setList(nextQuery, `attr_${key}`, values)
    }
  }

  return nextQuery
}
