import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const sources = await Promise.all([
  readFile(new URL('./i18n.ts', import.meta.url), 'utf8'),
  readFile(new URL('../components/CategorySidebar.tsx', import.meta.url), 'utf8'),
])
const locales = Object.fromEntries(await Promise.all(['ru', 'en'].map(async (locale) => [
  locale,
  JSON.parse(await readFile(new URL(`../../public/locales/${locale}/common.json`, import.meta.url), 'utf8')),
])))

function compile(source, overrides = {}) {
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  })
  const module = { exports: {} }
  const localRequire = (id) => overrides[id] || require(id)
  new Function('require', 'module', 'exports', outputText)(localRequire, module, module.exports)
  return module.exports
}

const i18n = compile(sources[0])
const category = {
  id: 42,
  slug: 'antiinfectives-vaccines',
  name: 'Другие противоинфекционные средства и вакцины',
  product_count: 1234567,
  translations: [
    { locale: 'ru', name: 'Другие противоинфекционные средства и вакцины' },
    { locale: 'en', name: 'Other Antiinfectives & Vaccines' },
  ],
}

for (const locale of ['ru', 'en']) {
  for (const mode of ['categories', 'subcategories', 'tree']) {
    test(`medicine sidebar renders compact ${locale} names and preserves full tooltips (${mode})`, () => {
      const Sidebar = compile(sources[1], {
        '../lib/i18n': i18n,
        'next/router': { useRouter: () => ({ locale }) },
        'next-i18next': { useTranslation: () => ({ t: (key, fallback) => locales[locale][key] || fallback || key }) },
      }).default
      const props = { categoryType: 'medicines', onFilterChange() {}, onToggle() {} }
      if (mode === 'tree') {
        props.categoryGroups = [{ title: 'Medicines', items: [{ ...category, id: 'category-42', dataId: 42, type: 'category', count: 1234567 }] }]
      } else {
        props[mode] = [category]
        props.showSubcategories = mode === 'subcategories'
      }
      const html = renderToStaticMarkup(React.createElement(Sidebar, props))
      const escape = (value) => value.replaceAll('&', '&amp;')
      assert.ok(html.includes(escape(locales[locale]['sidebar_medicine_antiinfectives-vaccines'])))
      assert.ok(html.includes(`title="${escape(category.translations.find((item) => item.locale === locale).name)}"`))
      assert.ok(html.includes('(1234567)'))
      const inputId = mode === 'tree' ? 'filter-item-category-42' : `direct-${mode === 'categories' ? 'cat' : 'sub'}-42`
      assert.ok(html.includes(`id="${inputId}"`), 'filter identity remains unchanged')
      assert.match(html, /class="[^"]*min-w-0[^"]*whitespace-normal[^"]*break-words/)
      assert.match(html, /<input[^>]+class="[^"]*shrink-0/)
      assert.match(html, /<aside[^>]+class="[^"]*w-80 max-w-full min-w-0 shrink-0/)
    })
  }
}
