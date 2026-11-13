import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { join } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const frontendRoot = fileURLToPath(new URL('../..', import.meta.url))

async function headersFor(nodeEnv) {
  const previous = process.env.NODE_ENV
  process.env.NODE_ENV = nodeEnv
  const configPath = require.resolve(join(frontendRoot, 'next.config.js'))
  delete require.cache[configPath]
  try {
    return await require(configPath).headers()
  } finally {
    process.env.NODE_ENV = previous
    delete require.cache[configPath]
  }
}

function cspValue(rules) {
  const rule = rules.find((item) => item.source === '/:path*')
  return rule?.headers.find((header) => header.key === 'Content-Security-Policy')?.value
}

test('production pages and auth pages enforce CSP, no Report-Only header (TD-033)', async () => {
  const rules = await headersFor('production')
  const keys = rules.flatMap((rule) => rule.headers.map((header) => header.key))

  assert.ok(cspValue(rules))
  const authRule = rules.find((item) => item.source === '/auth/:path*')
  assert.ok(authRule.headers.some((header) => header.key === 'Content-Security-Policy'))
  // Откат — CSP_ENFORCE = false в next.config.js (docs/SECURITY_CSP.md); тогда этот тест упадёт.
  assert.ok(!keys.includes('Content-Security-Policy-Report-Only'))
})

test('CSP keeps analytics, Telegram login, CDN media and video embeds allowed', async () => {
  const csp = cspValue(await headersFor('production'))
  const directive = (name) => csp.split('; ').find((part) => part.startsWith(`${name} `)) || ''

  assert.match(directive('script-src'), /https:\/\/www\.googletagmanager\.com/)
  assert.match(directive('script-src'), /https:\/\/mc\.yandex\.ru/)
  assert.match(directive('script-src'), /https:\/\/telegram\.org/)
  assert.match(directive('script-src'), /https:\/\/static\.cloudflareinsights\.com/)
  assert.match(directive('frame-src'), /https:\/\/oauth\.telegram\.org/)
  // Прод 24.10.2026: VK ID на /auth ходил на id.vk.ru — отчёты frame-src и connect-src.
  assert.match(directive('frame-src'), /https:\/\/id\.vk\.ru/)
  assert.match(directive('connect-src'), /https:\/\/id\.vk\.ru/)
  assert.match(directive('frame-src'), /https:\/\/www\.youtube-nocookie\.com/)
  assert.match(directive('media-src'), /https:\/\/cdn\.mudaroba\.com/)
  assert.match(directive('connect-src'), /https:\/\/\*\.google-analytics\.com/)
  assert.equal(directive('object-src'), "object-src 'none'")
  assert.equal(directive('report-uri'), 'report-uri /api/csp-report/')
  // Сайт и так только на https (HSTS), директива не нужна.
  assert.ok(!csp.includes('upgrade-insecure-requests'))
})

test('eval is allowed only on auth pages for the Telegram widget (TD-033)', async () => {
  const rules = await headersFor('production')
  const directive = (csp) => csp.split('; ').find((part) => part.startsWith('script-src '))
  const authRule = rules.find((item) => item.source === '/auth/:path*')
  const authCsp = authRule.headers.find((header) => header.key === 'Content-Security-Policy').value

  assert.doesNotMatch(directive(cspValue(rules)), /unsafe-eval/)
  assert.match(directive(authCsp), /'unsafe-eval'/)
  // Правило входа должно идти после общего: Next применяет последнее значение заголовка.
  assert.ok(rules.findIndex((item) => item.source === '/:path*') < rules.indexOf(authRule))
})

test('reports from 30-31.10.2026 are covered: Metrika mirror and browser translator', async () => {
  const csp = cspValue(await headersFor('production'))
  const directive = (name) => csp.split('; ').find((part) => part.startsWith(`${name} `)) || ''

  assert.match(directive('script-src'), /https:\/\/mc\.yandex\.com/)
  assert.match(directive('frame-src'), /https:\/\/mc\.yandex\.ru/)
  assert.match(directive('frame-src'), /https:\/\/mc\.yandex\.com/)
  assert.match(directive('style-src'), /https:\/\/www\.gstatic\.com/)
})

test('report from 03.11.2026 is covered: product videos from IKEA and umma-land', async () => {
  const csp = cspValue(await headersFor('production'))
  const mediaSrc = csp.split('; ').find((part) => part.startsWith('media-src ')) || ''

  assert.match(mediaSrc, /https:\/\/www\.ikea\.com/)
  assert.match(mediaSrc, /https:\/\/umma-land\.com/)
})

test('dev server gets no CSP (Next dev needs eval and HMR sockets)', async () => {
  assert.equal(cspValue(await headersFor('development')), undefined)
})

async function sourceFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true })
  const files = await Promise.all(
    entries.map((entry) => {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) return sourceFiles(path)
      return /\.(ts|tsx|js|jsx)$/.test(entry.name) ? [path] : []
    }),
  )
  return files.flat()
}

test('frontend never writes the refresh token into a JS-readable cookie', async () => {
  const offenders = []
  for (const file of await sourceFiles(join(frontendRoot, 'src'))) {
    const source = await readFile(file, 'utf8')
    if (/Cookies\.set\(\s*['"](refresh|refresh_token)['"]/.test(source)) offenders.push(file)
  }
  assert.deepEqual(offenders, [])
})

test('report from 13.11.2026 is covered: regional Metrika domains and Webvisor', async () => {
  const csp = cspValue(await headersFor('production'))
  const directive = (name) => csp.split('; ').find((part) => part.startsWith(`${name} `)) || ''

  for (const host of ['mc.yandex.md', 'mc.yandex.kz', 'mc.yandex.uz', 'mc.yandex.com.tr', 'mc.webvisor.org']) {
    assert.ok(directive('connect-src').includes(`https://${host}`), host)
    assert.ok(directive('connect-src').includes(`wss://${host}`), host)
    assert.ok(directive('frame-src').includes(`https://${host}`), host)
    assert.ok(directive('script-src').includes(`https://${host}`), host)
  }
  // Случайные домены wsync Метрики по-прежнему не разрешены.
  assert.doesNotMatch(directive('script-src'), /https:\/\/\*\.ru|https:\/\/\*\.yandex/)
})
