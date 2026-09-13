import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const source = await readFile(new URL('../pages/index.tsx', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText

const inventory = [
  { id: 1, name: 'Popular', products_count: 100 },
  { id: 2, name: 'Pinned', show_on_homepage: true, homepage_priority: 1, products_count: 1 },
]

function loadHome({ ssrFails = false, clientGet, ssrBrandDelay = 0 } = {}) {
  const effects = []
  const updates = []
  const requests = []
  const ssrRequests = []
  const modules = {
    react: {
      useRef: () => ({ current: null }),
      useState: (initial) => [initial, (value) => updates.push(value)],
      useEffect: (effect) => effects.push(effect),
    },
    'react/jsx-runtime': require('react/jsx-runtime'),
    'next/router': { useRouter: () => ({ locale: 'ru', defaultLocale: 'ru' }) },
    'next/dynamic': () => () => null,
    'next-i18next': { useTranslation: () => ({ t: (_, fallback) => fallback }) },
    'next-i18next/serverSideTranslations': { serverSideTranslations: async () => ({}) },
    '../lib/urls': { getSiteOrigin: () => '', getInternalApiUrl: (path) => path },
    '../lib/sanitizeHtml': { safeJsonLd: JSON.stringify },
    '../lib/media': {
      getPlaceholderImageUrl: () => '', withListingImageMaxWidth: () => '',
      isVideoUrl: () => false, extractYouTubeId: () => null, resolveMediaUrl: (url) => url,
    },
    '../lib/i18n': { getLocalizedBrandName: (_, name) => name },
    '../lib/footerSettings': { fetchFooterSettings: async () => ({}) },
    '../lib/api': { getSingleFlight: async (...args) => {
      requests.push(args)
      return clientGet ? clientGet(...args) : { data: { results: inventory } }
    } },
    axios: { get: async (url, config) => {
      ssrRequests.push(url)
      if (url.includes('catalog/brands')) {
        if (ssrFails || config.timeout < ssrBrandDelay) throw new Error('SSR brand timeout')
        return { data: { results: inventory } }
      }
      return { data: [] }
    } },
  }
  const exports = {}
  vm.runInNewContext(compiled, {
    exports,
    require: (name) => modules[name] ?? (name === '../lib/homepageBrands' ? require('./homepageBrands.js') : () => null),
    console: { log() {}, error() {} },
  })
  return { ...exports, effects, updates, requests, ssrRequests }
}

test('после таймаута SSR неполная главная не кэшируется', async () => {
  const home = loadHome({ ssrFails: true })
  const headers = new Map()
  const result = await home.getServerSideProps({ locale: 'ru', res: { setHeader: (k, v) => headers.set(k, v) } })
  assert.equal(result.props.brands.length, 0)
  assert.equal(headers.get('Cache-Control'), 'private, no-store')
})

test('пустой SSR-список восстанавливается в браузере с прежним приоритетом брендов', async () => {
  const home = loadHome()
  home.default({ brands: [], categories: [] })
  home.effects.forEach((effect) => effect())
  await new Promise(setImmediate)
  assert.equal(home.requests.length, 1)
  assert.ok(home.requests[0][1].timeout > 7200)
  assert.deepEqual(Array.from(home.updates.at(-1), (brand) => brand.id), [2, 1])
})

test('успешный SSR сохраняет приоритет закреплённых брендов', async () => {
  const home = loadHome()
  const result = await home.getServerSideProps({ locale: 'ru', res: { setHeader() {} } })
  assert.deepEqual(Array.from(result.props.brands, (brand) => brand.id), [2, 1])
  home.default({ brands: result.props.brands, categories: [] })
  home.effects.forEach((effect) => effect())
  assert.equal(home.requests.length, 0)
})

test('ответ после ухода со страницы не меняет состояние', async () => {
  let resolveRequest
  const home = loadHome({ clientGet: () => new Promise((resolve) => { resolveRequest = resolve }) })
  home.default({ brands: [], categories: [] })
  const cleanups = home.effects.map((effect) => effect())
  cleanups.forEach((cleanup) => cleanup?.())
  const updatesBefore = home.updates.length
  resolveRequest({ data: inventory })
  await new Promise(setImmediate)
  assert.equal(home.updates.length, updatesBefore)
})


test('ответ брендов за 7.2 секунды попадает в HTML без второго запроса из браузера', async () => {
  const home = loadHome({ ssrBrandDelay: 7200 })
  const result = await home.getServerSideProps({ locale: 'ru', res: { setHeader() {} } })
  assert.equal(result.props.brands.length, 2)
  assert.ok(home.ssrRequests[0].includes('catalog/brands'))
  home.default({ brands: result.props.brands, categories: [] })
  home.effects.forEach((effect) => effect())
  assert.equal(home.requests.length, 0)
})

test('повторный пустой SSR-ответ не убирает восстановленные карточки во время запроса', async () => {
  let resolveRequest
  const home = loadHome({ clientGet: () => new Promise((resolve) => { resolveRequest = resolve }) })
  home.default({ brands: [], categories: [] })
  const firstCleanups = home.effects.map((effect) => effect())
  resolveRequest({ data: inventory })
  await new Promise(setImmediate)
  assert.equal(home.updates.at(-1).length, 2)
  firstCleanups.forEach((cleanup) => cleanup?.())
  const updatesBefore = home.updates.length
  home.effects.length = 0
  home.default({ brands: [], categories: [] })
  home.effects.forEach((effect) => effect())
  assert.equal(home.updates.length, updatesBefore)
  resolveRequest({ data: inventory })
  await new Promise(setImmediate)
})
