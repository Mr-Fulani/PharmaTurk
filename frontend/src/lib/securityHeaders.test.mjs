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
  return rule?.headers.find((header) => header.key === 'Content-Security-Policy-Report-Only')?.value
}

test('production pages send CSP only in Report-Only mode (TD-018)', async () => {
  const rules = await headersFor('production')
  const keys = rules.flatMap((rule) => rule.headers.map((header) => header.key))

  assert.ok(cspValue(rules))
  // Enforce — отдельным шагом (docs/SECURITY_CSP.md), сейчас ничего не блокируем.
  assert.ok(!keys.includes('Content-Security-Policy'))
})

test('report-only CSP keeps analytics, Telegram login, CDN media and video embeds allowed', async () => {
  const csp = cspValue(await headersFor('production'))
  const directive = (name) => csp.split('; ').find((part) => part.startsWith(`${name} `)) || ''

  assert.match(directive('script-src'), /https:\/\/www\.googletagmanager\.com/)
  assert.match(directive('script-src'), /https:\/\/mc\.yandex\.ru/)
  assert.match(directive('script-src'), /https:\/\/telegram\.org/)
  assert.match(directive('script-src'), /https:\/\/static\.cloudflareinsights\.com/)
  assert.match(directive('frame-src'), /https:\/\/oauth\.telegram\.org/)
  assert.match(directive('frame-src'), /https:\/\/www\.youtube-nocookie\.com/)
  assert.match(directive('media-src'), /https:\/\/cdn\.mudaroba\.com/)
  assert.match(directive('connect-src'), /https:\/\/\*\.google-analytics\.com/)
  assert.equal(directive('object-src'), "object-src 'none'")
  assert.equal(directive('report-uri'), 'report-uri /api/csp-report/')
  // В report-only браузер игнорирует эту директиву и пишет предупреждение в консоль.
  assert.ok(!csp.includes('upgrade-insecure-requests'))
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
