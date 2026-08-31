const normalizeCategorySlug = (value) =>
  (value || '').toString().trim().toLowerCase().replace(/_/g, '-')

export function isCategoryInProductTree({ categoryType, inferredType, routeSlug, ancestors }, targetType) {
  const target = normalizeCategorySlug(targetType)
  if (!target) return false

  const candidates = [categoryType, inferredType, routeSlug]
  for (const ancestor of ancestors || []) candidates.push(ancestor?.slug)

  return candidates.some((value) => normalizeCategorySlug(value) === target)
}

export function selectExactCategory(items, routeSlug) {
  const target = normalizeCategorySlug(routeSlug)
  if (!target || !Array.isArray(items)) return null
  return items.find((item) => normalizeCategorySlug(item?.slug) === target) || null
}

export function isCatalogPageOutOfRange(pageValue, totalCount, pageSize) {
  const rawPage = Array.isArray(pageValue) ? pageValue[0] : pageValue
  const requestedPage = Number(rawPage ?? 1)
  const normalizedPageSize = Number(pageSize)
  const normalizedCount = Number(totalCount)

  if (!Number.isInteger(requestedPage) || requestedPage < 1) return true
  if (!Number.isFinite(normalizedPageSize) || normalizedPageSize < 1) return true

  const safeCount = Number.isFinite(normalizedCount) && normalizedCount > 0
    ? normalizedCount
    : 0
  const lastPage = Math.max(1, Math.ceil(safeCount / normalizedPageSize))
  return requestedPage > lastPage
}

const INDEXABLE_CATEGORY_QUERY_KEYS = new Set(['slug', 'page'])

const hasQueryValue = (value) => {
  if (Array.isArray(value)) return value.some(hasQueryValue)
  return value !== undefined && value !== null && String(value).trim() !== ''
}

const withCatalogPage = (basePath, page) =>
  page > 1 ? `${basePath}?page=${page}` : basePath

/**
 * SEO state for category pagination.
 *
 * Plain page 2+ is a real slice of the catalogue and therefore gets a
 * self-canonical URL plus prev/next links. Filter/sort/search combinations are
 * crawlable for discovery but noindex and canonicalize to the clean category.
 */
export function buildCatalogSeoState(basePath, query, currentPage, totalPages) {
  const page = Number(currentPage)
  const safePage = Number.isInteger(page) && page > 0 ? page : 1
  const pages = Number(totalPages)
  const safeTotalPages = Number.isInteger(pages) && pages > 0 ? pages : 1
  const hasFilters = Object.entries(query || {}).some(([key, value]) =>
    !INDEXABLE_CATEGORY_QUERY_KEYS.has(key) && hasQueryValue(value)
  )

  if (hasFilters) {
    return {
      canonicalPath: basePath,
      hasFilters: true,
      noindex: true,
      previousPath: null,
      nextPath: null,
    }
  }

  return {
    canonicalPath: withCatalogPage(basePath, safePage),
    hasFilters: false,
    noindex: false,
    previousPath: safePage > 1 ? withCatalogPage(basePath, safePage - 1) : null,
    nextPath: safePage < safeTotalPages ? withCatalogPage(basePath, safePage + 1) : null,
  }
}
