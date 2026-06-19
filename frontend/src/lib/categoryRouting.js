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
