import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('./i18n.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const i18n = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

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
