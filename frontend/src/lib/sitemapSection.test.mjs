import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

import * as serverPublicCache from './serverPublicCache.js'

// Секция sitemap при сбое API: раньше пустой список уходил с public, s-maxage=86400,
// и Cloudflare сутки держал пустую секцию.
const source = await readFile(new URL('../pages/sitemaps/[section].tsx', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText

function loadPage({ fetchAllPages, axiosGet = async () => ({ data: [] }) }) {
  const sitemap = {
    SITEMAP_DOMAINS: ['medicines'],
    buildProductPath: (slug) => `/product/${slug}`,
    buildUrl: (path) => ({ loc: `https://mudaroba.com${path}` }),
    fetchAllPages,
    generateSitemapXml: (urls) => `<urlset>${urls.map((url) => `<url>${url.loc}</url>`).join('')}</urlset>`,
  }
  const modules = {
    axios: { __esModule: true, default: { get: axiosGet } },
    '../../lib/urls': { getInternalApiUrl: (path) => path },
    '../../lib/sitemap': sitemap,
    '../../lib/serverPublicCache': serverPublicCache,
    '../../content/blog/articles': { BLOG_ARTICLES: [{ slug: 'kak-proverit-tureckoe-lekarstvo', updatedAt: '2026-10-24' }] },
  }
  const exports = {}
  vm.runInNewContext(compiled, { exports, require: (name) => modules[name], console: { error() {} } })
  return exports
}

async function render(page, section) {
  const res = {
    statusCode: 200,
    headers: {},
    body: '',
    setHeader(name, value) { this.headers[name.toLowerCase()] = value },
    write(chunk) { this.body += chunk },
    end() {},
  }
  await page.getServerSideProps({ params: { section }, res })
  return res
}

test('пустая из-за сбоя API секция — 503 без кэша', async () => {
  const page = loadPage({ fetchAllPages: async () => { throw new Error('backend down') } })

  const res = await render(page, 'products-medicines.xml')

  assert.equal(res.statusCode, 503)
  assert.equal(res.headers['cache-control'], 'no-store')
  assert.equal(res.headers['retry-after'], '300')
})

test('полная секция кэшируется на сутки', async () => {
  const page = loadPage({ fetchAllPages: async () => [{ slug: 'parol', product_type: 'medicines' }] })

  const res = await render(page, 'products-medicines.xml')

  assert.equal(res.statusCode, 200)
  assert.equal(res.headers['cache-control'], 'public, s-maxage=86400, stale-while-revalidate=604800')
  assert.match(res.body, /parol/)
})

test('частичный сбой: страницы есть, но ответ не кэшируется', async () => {
  const page = loadPage({
    fetchAllPages: async () => [],
    axiosGet: async (url) => {
      if (url === 'pages/') throw new Error('timeout')
      return { data: [] }
    },
  })

  const res = await render(page, 'static.xml')

  assert.equal(res.statusCode, 200)
  assert.equal(res.headers['cache-control'], 'no-store')
  assert.match(res.body, /<url>/)
})

test('после сбоя секция собирается заново, а не берётся из памяти', async () => {
  let fail = true
  const page = loadPage({
    fetchAllPages: async () => {
      if (fail) throw new Error('backend down')
      return [{ slug: 'parol', product_type: 'medicines' }]
    },
  })

  assert.equal((await render(page, 'products-medicines.xml')).statusCode, 503)
  fail = false
  const res = await render(page, 'products-medicines.xml')

  assert.equal(res.statusCode, 200)
  assert.match(res.body, /parol/)
})

test('статьи блога — в секции static, страницы препаратов — в секции drugs', async () => {
  const page = loadPage({
    fetchAllPages: async (path, params) => (params?.kind === 'drug_groups' ? [{ slug: 'majezik', updated_at: '2026-10-24T10:00:00Z' }] : []),
  })

  const staticRes = await render(page, 'static.xml')
  assert.match(staticRes.body, /\/blog<\/url>/)
  assert.match(staticRes.body, /\/blog\/kak-proverit-tureckoe-lekarstvo/)

  const drugsRes = await render(page, 'drugs.xml')
  assert.equal(drugsRes.statusCode, 200)
  assert.match(drugsRes.body, /\/drugs\/majezik/)
})
