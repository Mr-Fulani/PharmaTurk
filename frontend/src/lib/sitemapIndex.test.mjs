import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

// Индекс sitemap: пустая товарная секция (urlset без <url>) у Google — ошибка
// «Тег XML отсутствует», такие секции в индекс не попадают.
const source = await readFile(new URL('../pages/sitemap.xml.tsx', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText

function loadPage(axiosGet) {
  const modules = {
    axios: { __esModule: true, default: { get: axiosGet } },
    '../lib/urls': { getInternalApiUrl: (path) => path },
    '../lib/sitemap': {
      SITEMAP_DOMAINS: ['medicines', 'electronics', 'shoes'],
      generateSitemapIndexXml: (sections) => sections.map((name) => `<loc>${name}</loc>`).join(''),
    },
  }
  const exports = {}
  vm.runInNewContext(compiled, { exports, require: (name) => modules[name], console: { error() {} } })
  return exports
}

async function render(page) {
  const res = {
    headers: {},
    body: '',
    setHeader(name, value) { this.headers[name.toLowerCase()] = value },
    write(chunk) { this.body += chunk },
    end() {},
  }
  await page.getServerSideProps({ res })
  return res
}

test('пустой домен не попадает в индекс, индекс кэшируется на сутки', async () => {
  const page = loadPage(async (_url, { params }) => ({
    data: { results: params.domain === 'electronics' ? [] : [{ slug: 'x' }] },
  }))

  const res = await render(page)

  assert.match(res.body, /products-medicines/)
  assert.match(res.body, /products-shoes/)
  assert.doesNotMatch(res.body, /products-electronics/)
  assert.match(res.body, /<loc>static<\/loc>/)
  assert.equal(res.headers['cache-control'], 'public, s-maxage=86400, stale-while-revalidate=604800')
})

test('сбой проверки: секция остаётся, индекс не кэшируется', async () => {
  const page = loadPage(async (_url, { params }) => {
    if (params.domain === 'shoes') throw new Error('timeout')
    return { data: { results: params.domain === 'electronics' ? [] : [{ slug: 'x' }] } }
  })

  const res = await render(page)

  assert.match(res.body, /products-shoes/)
  assert.doesNotMatch(res.body, /products-electronics/)
  assert.equal(res.headers['cache-control'], 'no-store')
})
