import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { IncomingMessage, ServerResponse } from 'node:http'
import { createRequire } from 'node:module'
import { Socket } from 'node:net'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const source = await readFile(new URL('../pages/_error.tsx', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText

function loadErrorPage() {
  const exports = {}
  vm.runInNewContext(compiled, { exports, require })
  return exports.default
}

const PUBLIC_CACHE = 'public, s-maxage=300, stale-while-revalidate=86400'

test('500 после public-заголовка gSSP уходит с private, no-store', async () => {
  const ErrorPage = loadErrorPage()
  const res = new ServerResponse(new IncomingMessage(new Socket()))
  // gSSP успел поставить общий кэш, затем упал — Next рендерит _error на том же res
  res.setHeader('Cache-Control', PUBLIC_CACHE)
  res.statusCode = 500

  const props = await ErrorPage.getInitialProps({ res, err: new Error('boom') })

  assert.equal(props.statusCode, 500)
  assert.equal(res.getHeader('Cache-Control'), 'private, no-store')
})

test('на клиенте (без res) _error отдаёт код ошибки и не падает', async () => {
  const ErrorPage = loadErrorPage()
  const props = await ErrorPage.getInitialProps({ err: Object.assign(new Error('boom'), { statusCode: 500 }) })
  assert.equal(props.statusCode, 500)
})
