import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('./i18n.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const i18n = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

const sidebarLocales = Object.fromEntries(await Promise.all(['ru', 'en'].map(async (locale) => [
  locale,
  JSON.parse(await readFile(new URL(`../../public/locales/${locale}/common.json`, import.meta.url), 'utf8')),
])))

test('medicine sidebar uses a short localized label without changing the full API name', () => {
  const translations = [
    { locale: 'ru', name: 'Другие противоинфекционные средства и вакцины' },
    { locale: 'en', name: 'Other Antiinfectives & Vaccines' },
  ]
  for (const locale of ['ru', 'en']) {
    const t = (key, fallback) => sidebarLocales[locale][key] || fallback || key
    const expected = locale === 'ru' ? 'Противоинфекционные и вакцины' : 'Antiinfectives & vaccines'
    assert.equal(i18n.getSidebarCategoryName('medicines', 'antiinfectives-vaccines', '', t, translations, locale), expected)
    assert.equal(i18n.getLocalizedCategoryName('antiinfectives-vaccines', '', t, translations, locale), translations.find((item) => item.locale === locale).name)
  }
})

test('sidebar abbreviations never override other product types or custom category names', () => {
  const t = (key, fallback) => sidebarLocales.ru[key] || fallback || key
  const translations = [{ locale: 'ru', name: 'Полное имя из админки' }]
  assert.equal(i18n.getSidebarCategoryName('supplements', 'painkillers', '', t, translations, 'ru'), 'Полное имя из админки')
  assert.equal(i18n.getSidebarCategoryName('medicines', 'custom-medicine', '', t, translations, 'ru'), 'Полное имя из админки')
  assert.equal(i18n.getSidebarCategoryName('medicines', 'custom-medicine', 'Название без перевода', t), 'Название без перевода')
})

test('all seeded medicine navigation groups have concise RU/EN sidebar labels', async () => {
  const taxonomy = await readFile(new URL('../../../backend/apps/catalog/medicine_taxonomy.py', import.meta.url), 'utf8')
  const tree = taxonomy.split('MEDICINES_SUBCATEGORIES = [')[1].split('\n]')[0]
  const slugs = [...tree.matchAll(/^\s*\("[^"]+", "[^"]+", "([^"]+)"/gm)].map((match) => match[1])
  assert.equal(slugs.length, 16)
  for (const locale of ['ru', 'en']) {
    const labels = slugs.map((slug) => sidebarLocales[locale][`sidebar_medicine_${slug}`])
    assert.equal(new Set(labels).size, slugs.length)
    for (const label of labels) {
      assert.ok(label && label.length <= 30, `${locale}: ${label}`)
      assert.doesNotMatch(label, /другие|прочие|\bother\b/i)
    }
  }
})

const translateFromLegacyJson = (key) => ({
  'category-medicines': 'Legacy value',
  'category_medicines_name': 'Legacy medicines',
  'category_medicines_description': 'Legacy description',
}[key] || key)

test('CategoryTranslation name has priority over legacy JSON localization', () => {
  assert.equal(
    i18n.getLocalizedCategoryName(
      'medicines',
      'Медикаменты',
      translateFromLegacyJson,
      [{ locale: 'en', name: 'API medicines' }],
      'en'
    ),
    'API medicines'
  )
})

test('category API description is used when the base description is empty', () => {
  assert.equal(
    i18n.getLocalizedCategoryDescription(
      'medicines',
      '',
      translateFromLegacyJson,
      [{ locale: 'en', name: 'API medicines', description: 'API description' }],
      'en'
    ),
    'API description'
  )
})

test('category API description is used when the base description is absent', () => {
  assert.equal(
    i18n.getLocalizedCategoryDescription(
      'medicines',
      undefined,
      translateFromLegacyJson,
      [{ locale: 'en', name: 'API medicines', description: 'API description' }],
      'en-US'
    ),
    'API description'
  )
})

test('exact locale wins over a base-language CategoryTranslation', () => {
  const translations = [
    { locale: 'en', name: 'English' },
    { locale: 'en-US', name: 'American English' },
  ]

  assert.deepEqual(
    i18n.findCategoryTranslation(translations, 'en_US'),
    translations[1]
  )
})

test('legacy description remains a fallback when API translation has no description', () => {
  assert.equal(
    i18n.getLocalizedCategoryDescription(
      'medicines',
      null,
      translateFromLegacyJson,
      [{ locale: 'en', name: 'API medicines' }],
      'en'
    ),
    'Legacy description'
  )
})
