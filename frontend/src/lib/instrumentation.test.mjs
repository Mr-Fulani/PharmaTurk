import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import http from 'node:http'
import { createRequire } from 'node:module'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
import axios from 'axios'

const require = createRequire(import.meta.url)
const source = await readFile(new URL('../instrumentation.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText

async function register(runtime) {
  const mod = { exports: {} }
  vm.runInThisContext(`(function (exports, require, module, process) {${compiled}\n})`)(
    mod.exports, require, mod, { env: { NEXT_RUNTIME: runtime } },
  )
  await mod.exports.register()
}

// Gunicorn закрывает простаивающий keep-alive сокет через 2 с; SSR не должен
// держать такие сокеты, иначе следующий запрос падает с ECONNRESET.
test('SSR-запросы к API идут без keep-alive', async () => {
  const seen = []
  const server = http.createServer((req, res) => {
    seen.push({ connection: req.headers.connection, port: req.socket.remotePort })
    res.setHeader('Content-Type', 'application/json')
    res.end('{"results":[]}')
  })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const url = `http://127.0.0.1:${server.address().port}/api/catalog/brands`
  const keepAliveBefore = http.globalAgent.keepAlive
  try {
    await register('edge')
    assert.equal(http.globalAgent.keepAlive, keepAliveBefore, 'вне Node-рантайма агент не трогаем')

    await register('nodejs')
    await axios.get(url)
    await axios.get(url)

    assert.equal(http.globalAgent.keepAlive, false)
    assert.deepEqual(seen.map((row) => row.connection), ['close', 'close'])
    assert.notEqual(seen[0].port, seen[1].port, 'второй запрос — новое соединение')
  } finally {
    http.globalAgent.keepAlive = keepAliveBefore
    server.close()
  }
})
