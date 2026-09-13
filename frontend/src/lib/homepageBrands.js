// Одинаковый порядок карточек при SSR и восстановлении в браузере.
export function selectHomepageBrands(data) {
  const allBrands = Array.isArray(data) ? data : (data?.results || [])
  const sortedBrands = [...allBrands].sort((a, b) => {
    const manualA = Boolean(a.show_on_homepage)
    const manualB = Boolean(b.show_on_homepage)
    if (manualA !== manualB) return manualA ? -1 : 1
    if (manualA && manualB) {
      const priorityA = a.homepage_priority ?? 100
      const priorityB = b.homepage_priority ?? 100
      if (priorityA !== priorityB) return priorityA - priorityB
    }
    const countA = a.products_count || 0
    const countB = b.products_count || 0
    if (countB !== countA) return countB - countA
    const hasMediaA = !!(a.card_media_url && a.card_media_url.trim())
    const hasMediaB = !!(b.card_media_url && b.card_media_url.trim())
    if (hasMediaB !== hasMediaA) return hasMediaB ? 1 : -1
    return (a.name || '').localeCompare(b.name || '', 'ru')
  })

  return sortedBrands.slice(0, 11)
}
