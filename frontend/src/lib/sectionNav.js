// Строка разделов под шапкой (components/SectionNav.tsx): разделы каталога,
// в которые посетитель попадает в один клик с любой страницы. Порядок — от
// лекарств к товарам для дома; остальные разделы открывает «Все разделы».
export const NAV_SECTIONS = /** @type {const} */ ([
  { slug: 'medicines', labelKey: 'section_nav_medicines', label: 'Лекарства' },
  { slug: 'supplements', labelKey: 'section_nav_supplements', label: 'БАДы и витамины' },
  { slug: 'clothing', labelKey: 'section_nav_clothing', label: 'Одежда' },
  { slug: 'shoes', labelKey: 'section_nav_shoes', label: 'Обувь' },
  { slug: 'islamic-clothing', labelKey: 'section_nav_islamic_clothing', label: 'Исламская одежда' },
  { slug: 'furniture', labelKey: 'section_nav_furniture', label: 'Мебель' },
  { slug: 'perfumery', labelKey: 'section_nav_perfumery', label: 'Парфюмерия' },
  { slug: 'accessories', labelKey: 'section_nav_accessories', label: 'Аксессуары' },
])

/** Раздел, открытый сейчас: страница раздела или его подборка. */
export function currentNavSection(pathname, query) {
  if (!String(pathname || '').startsWith('/categories/[slug]')) return ''
  const slug = String(query?.slug || '')
  return NAV_SECTIONS.some((section) => section.slug === slug) ? slug : ''
}
