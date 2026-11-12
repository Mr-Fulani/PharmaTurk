// Тема оформления и блоки главной из админки (docs/DESIGN_THEMES.md, docs/HOME_BLOCKS.md).
// Здесь только разбор ответа GET /api/settings/appearance: модуль общий для сервера,
// браузера и тестов.

export const THEMES = /** @type {const} */ (['cream', 'iznik', 'green'])
export const DEFAULT_THEME = 'cream'

// Шрифт, который страница темы показывает первым: его предзагрузка убирает сдвиг
// вёрстки при подмене системного шрифта. Пути совпадают с @font-face в globals.css.
export const THEME_FONT_PRELOAD = /** @type {const} */ ({
  cream: '/fonts/InkVerse-v2.woff2',
  iznik: '/fonts/Onest-v1.woff2',
  green: '/fonts/GolosText-v1.woff2',
})

// Порядок по умолчанию — порядок главной до появления настройки (миграция settings.0005).
export const HOME_BLOCK_KEYS = /** @type {const} */ ([
  'main_banner',
  'brands',
  'banner_after_brands',
  'categories',
  'banner_before_footer',
  'bestsellers',
  'sourcing',
  'recommendations',
  'banner_after_popular',
  'testimonials',
  'facts',
])

/** @typedef {typeof THEMES[number]} Theme */
/** @typedef {typeof HOME_BLOCK_KEYS[number]} HomeBlockKey */
/** @typedef {{ theme: Theme, homeBlocks: HomeBlockKey[] }} SiteAppearance */

/** @returns {Theme} */
export function normalizeTheme(value) {
  return THEMES.includes(value) ? value : DEFAULT_THEME
}

/**
 * Ключи блоков главной, которые нужно показать, в порядке показа.
 * Неизвестные ключи отбрасываются; блок, которого нет в ответе (ещё без записи
 * в админке), показывается после перечисленных.
 * @returns {HomeBlockKey[]}
 */
export function visibleHomeBlocks(blocks) {
  if (!Array.isArray(blocks)) return fallbackAppearance().homeBlocks
  /** @type {Map<HomeBlockKey, boolean>} */
  const listed = new Map()
  for (const block of blocks) {
    if (block && HOME_BLOCK_KEYS.includes(block.key) && !listed.has(block.key)) {
      listed.set(block.key, block.is_enabled !== false)
    }
  }
  const order = [...listed.keys(), ...HOME_BLOCK_KEYS.filter((key) => !listed.has(key))]
  return order.filter((key) => listed.get(key) !== false)
}

/** @returns {SiteAppearance} */
export function normalizeAppearance(data) {
  return {
    theme: normalizeTheme(data?.theme),
    homeBlocks: visibleHomeBlocks(data?.home_blocks),
  }
}

/**
 * Вид сайта, когда настройки получить не удалось: прежняя главная без блока
 * отзывов (он и раньше скрывался, если его настройка не отвечала).
 * @returns {SiteAppearance}
 */
export function fallbackAppearance() {
  return {
    theme: DEFAULT_THEME,
    homeBlocks: HOME_BLOCK_KEYS.filter((key) => key !== 'testimonials'),
  }
}
