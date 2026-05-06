/**
 * Тест buildProductPath из sitemap.xml.tsx
 * Запуск: node test-buildProductPath.mjs
 *
 * Проверяет что URL в сайтмапе совпадает с canonical-URL страницы
 * (логика buildProductUrl из src/lib/urls.ts).
 */

// ─── Копия функций из sitemap.xml.tsx ───────────────────────────────────────

const BASE_PRODUCT_TYPES = new Set([
  '', 'product', 'products',
  'medicine', 'medicines',
  'supplement', 'supplements',
  'medical_equipment', 'medical-equipment',
  'furniture', 'tableware',
  'accessory', 'accessories',
  'books', 'perfumery', 'incense', 'sports',
  'auto_parts', 'auto-parts',
])

function buildProductPath(slug, productType) {
  const normalizedType = (productType || '').trim().replace(/_/g, '-')

  const rawSlug = (slug || '').trim().replace(/_/g, '-')
  const parts = rawSlug.split('-')
  let deduplicatedSlug = rawSlug
  if (parts.length >= 4 && parts.length % 2 === 0) {
    const half = parts.length / 2
    if (parts.slice(0, half).join('-') === parts.slice(half).join('-')) {
      deduplicatedSlug = parts.slice(0, half).join('-')
    }
  }

  if (!normalizedType || BASE_PRODUCT_TYPES.has(normalizedType)) {
    return `/product/${deduplicatedSlug}`
  }

  const prefix = `${normalizedType}-`
  let cleanedSlug = deduplicatedSlug
  while (cleanedSlug.startsWith(prefix)) {
    cleanedSlug = cleanedSlug.slice(prefix.length)
  }

  return `/product/${normalizedType}/${cleanedSlug || deduplicatedSlug}`
}

// ─── Копия функций из src/lib/urls.ts (эталон) ──────────────────────────────

const TYPES_NEEDING_PATH = new Set(['clothing', 'shoes', 'electronics', 'jewelry', 'uslugi', 'headwear', 'underwear', 'islamic-clothing'])

function deduplicateSlug(slug) {
  if (!slug) return ''
  const normalized = slug.toString().trim().replace(/_/g, '-')
  const parts = normalized.split('-')
  if (parts.length >= 4 && parts.length % 2 === 0) {
    const half = parts.length / 2
    if (parts.slice(0, half).join('-') === parts.slice(half).join('-')) return parts.slice(0, half).join('-')
  }
  return normalized
}

function buildProductUrl(productType, slug) {
  const normalizedType = (productType || 'medicines').toString().trim().replace(/_/g, '-')
  let deduplicatedSlug = deduplicateSlug((slug || '').toString().trim())
  if (normalizedType === 'uslugi') return `/product/uslugi/${deduplicatedSlug}`
  if (!TYPES_NEEDING_PATH.has(normalizedType)) return `/product/${deduplicatedSlug}`
  const prefix = `${normalizedType}-`
  let cleanedSlug = deduplicatedSlug
  while (cleanedSlug.startsWith(prefix)) cleanedSlug = cleanedSlug.slice(prefix.length)
  return `/product/${normalizedType}/${cleanedSlug || deduplicatedSlug}`
}

// ─── Тест-кейсы ─────────────────────────────────────────────────────────────

const cases = [
  // [slug из API, productType, ожидаемый URL]

  // БАЗОВЫЕ типы — /product/{slug}
  ['aspirin-500mg',               'medicines',         '/product/aspirin-500mg'],
  ['vitamin-c',                   'supplements',       '/product/vitamin-c'],
  ['sofa-ikea',                   'furniture',         '/product/sofa-ikea'],
  ['pots-set',                    'tableware',         '/product/pots-set'],
  ['ring-silver',                 'accessories',       '/product/ring-silver'],
  ['quran-arabic',                'books',             '/product/quran-arabic'],
  ['oud-wood',                    'perfumery',         '/product/oud-wood'],
  ['incense-stick',               'incense',           '/product/incense-stick'],
  ['yoga-mat',                    'sports',            '/product/yoga-mat'],
  ['oil-filter',                  'auto-parts',        '/product/oil-filter'],
  ['oil-filter',                  'auto_parts',        '/product/oil-filter'],  // underscore
  ['medical-mask',                'medical_equipment', '/product/medical-mask'],
  ['medical-mask',                'medical-equipment', '/product/medical-mask'],
  [null,                          'medicines',         '/product/'],             // пустой slug

  // ТИПЫ С ПУТЁМ — /product/{type}/{clean-slug}

  // Headwear: slug БЕЗ префикса (норма)
  ['carhartt-wip-icon-cap',       'headwear',          '/product/headwear/carhartt-wip-icon-cap'],
  // Headwear: slug С префиксом (баг который мы чиним)
  ['headwear-carhartt-wip-cap',   'headwear',          '/product/headwear/carhartt-wip-cap'],
  // Headwear: двойной префикс
  ['headwear-headwear-cap',       'headwear',          '/product/headwear/cap'],

  // Clothing
  ['classic-tshirt',              'clothing',          '/product/clothing/classic-tshirt'],
  ['clothing-classic-tshirt',     'clothing',          '/product/clothing/classic-tshirt'],
  ['clothing-clothing-tshirt',    'clothing',          '/product/clothing/tshirt'],

  // Shoes
  ['nike-air-max',                'shoes',             '/product/shoes/nike-air-max'],
  ['shoes-nike-air-max',          'shoes',             '/product/shoes/nike-air-max'],

  // Electronics
  ['samsung-galaxy-s24',         'electronics',        '/product/electronics/samsung-galaxy-s24'],
  ['electronics-samsung',        'electronics',        '/product/electronics/samsung'],

  // Jewelry
  ['gold-ring-18k',              'jewelry',            '/product/jewelry/gold-ring-18k'],
  ['jewelry-gold-ring',          'jewelry',            '/product/jewelry/gold-ring'],

  // Underwear
  ['cotton-brief',               'underwear',          '/product/underwear/cotton-brief'],
  ['underwear-cotton-brief',     'underwear',          '/product/underwear/cotton-brief'],

  // Islamic clothing
  ['abaya-black',                'islamic-clothing',   '/product/islamic-clothing/abaya-black'],
  ['islamic-clothing-abaya',     'islamic-clothing',   '/product/islamic-clothing/abaya'],

  // Услуги
  ['remont-santexniki',          'uslugi',             '/product/uslugi/remont-santexniki'],

  // Дедупликация slug-половин (name-name → name) — срабатывает только при >= 4 частях
  ['cap-cap',                    'headwear',           '/product/headwear/cap-cap'], // 2 части — НЕ дедупл.
  ['nike-air-nike-air',          'shoes',              '/product/shoes/nike-air'],
  ['aspirin-aspirin',            'medicines',          '/product/aspirin-aspirin'], // только 2 части — не дедупл.
  ['ab-cd-ab-cd',                'clothing',           '/product/clothing/ab-cd'],

  // Неизвестный/пустой тип — fallback к базовому
  ['some-product',               '',                   '/product/some-product'],
  ['some-product',               null,                 '/product/some-product'],
  ['some-product',               undefined,            '/product/some-product'],
]

// ─── Прогон тестов ───────────────────────────────────────────────────────────

let passed = 0
let failed = 0

for (const [slug, type, expected] of cases) {
  const got = buildProductPath(slug, type)
  const ref = (type === 'uslugi' || TYPES_NEEDING_PATH.has((type || '').replace(/_/g, '-')))
    ? buildProductUrl(type, slug)
    : buildProductPath(slug, type) // для базовых — просто проверяем совпадение с собой

  const ok = got === expected
  if (ok) {
    passed++
  } else {
    failed++
    console.error(`FAIL  slug="${slug}"  type="${type}"`)
    console.error(`      expected: ${expected}`)
    console.error(`      got:      ${got}`)
  }
}

// Дополнительная проверка: buildProductPath === buildProductUrl для TYPES_NEEDING_PATH
const syncCases = [
  ['headwear-carhartt-wip-cap',  'headwear'],
  ['clothing-classic-tshirt',    'clothing'],
  ['shoes-nike-air-max',         'shoes'],
  ['electronics-samsung',        'electronics'],
  ['jewelry-gold-ring',          'jewelry'],
  ['underwear-cotton-brief',     'underwear'],
  ['islamic-clothing-abaya',     'islamic-clothing'],
  ['carhartt-wip-icon-cap',      'headwear'],
  ['classic-tshirt',             'clothing'],
]

console.log('\nПроверка совпадения с buildProductUrl (эталон из urls.ts):')
for (const [slug, type] of syncCases) {
  const fromSitemap = buildProductPath(slug, type)
  const fromUrls    = buildProductUrl(type, slug)
  const ok = fromSitemap === fromUrls
  if (ok) {
    passed++
    console.log(`  OK  /product/${type}/... slug="${slug}"  → ${fromSitemap}`)
  } else {
    failed++
    console.error(`  FAIL slug="${slug}" type="${type}"`)
    console.error(`    sitemap: ${fromSitemap}`)
    console.error(`    urls.ts: ${fromUrls}`)
  }
}

console.log(`\n${'─'.repeat(50)}`)
console.log(`Итого: ${passed} passed, ${failed} failed`)
if (failed > 0) process.exit(1)
