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
