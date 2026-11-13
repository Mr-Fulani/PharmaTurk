import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { THEMES, THEME_BROWSER_COLOR, THEME_FONT_PRELOAD } from './siteAppearance.js'
import { THEME_RECHECK_MS, THEME_STORAGE_KEY, catchUpTheme, themeApiBaseFromEnv, themeCatchUpScript } from './themeCatchUp.js'

// Страница догоняет тему сама (docs/DESIGN_THEMES.md): HTML из кэша CDN приходит со старой
// темой, скрипт в <head> сверяет её с настройкой.

const cfg = (apiBase = '/api') => ({ themes: [...THEMES], fonts: THEME_FONT_PRELOAD, colors: THEME_BROWSER_COLOR, key: THEME_STORAGE_KEY, recheckMs: THEME_RECHECK_MS, apiBase })

/** Поддельное окно: <html data-skin>, <head> с предзагрузкой шрифта и theme-color, память, fetch. */
function fakeWindow({ skin = '', stored, search = '', apiTheme = 'green', apiOk = true, origin = 'https://mudaroba.com', now = 1_000_000, brokenStorage = false } = {}) {
  const attrs = skin ? { 'data-skin': skin } : {}
  const links = skin ? [{ rel: 'preload', href: THEME_FONT_PRELOAD[skin] }] : []
  const meta = { content: THEME_BROWSER_COLOR[skin || 'cream'], setAttribute(name, value) { this[name] = value } }
  const storage = new Map(stored ? [[THEME_STORAGE_KEY, JSON.stringify(stored)]] : [])
  const requests = []
  let settle
  const done = new Promise((resolve) => { settle = resolve })
  const w = {
    document: {
      documentElement: { getAttribute: (name) => attrs[name] ?? null, setAttribute: (name, value) => { attrs[name] = value } },
      head: { appendChild: (node) => links.push(node) },
      createElement: () => ({}),
      querySelector: (selector) => {
        if (selector.startsWith('meta')) return meta
        const href = /href="([^"]+)"/.exec(selector)[1]
        return links.find((link) => link.rel === 'preload' && link.href === href) || null
      },
    },
    location: { search, origin },
    localStorage: {
      getItem: (key) => { if (brokenStorage) throw new Error('нет доступа'); return storage.get(key) ?? null },
      setItem: (key, value) => { if (brokenStorage) throw new Error('нет доступа'); storage.set(key, value) },
    },
    Date: { now: () => now },
    fetch: (url, options) => {
      requests.push({ url, options })
      const response = apiOk ? { ok: true, json: async () => ({ theme: apiTheme, home_blocks: [] }) } : { ok: false }
      // Ответ приходит после синхронной части скрипта; settle — когда цепочка then отработала.
      return Promise.resolve(response).finally(() => setTimeout(settle, 0))
    },
  }
  return { w, attrs, links, meta, storage, requests, done }
}

test('страница из кэша со старой темой: скрипт ставит тему из настройки, шрифт и цвет панели', async () => {
  const page = fakeWindow({ skin: 'iznik', apiTheme: 'green' })
  catchUpTheme(page.w, cfg())
  assert.equal(page.attrs['data-skin'], 'iznik', 'до ответа настройки тема страницы не трогается')
  assert.deepEqual(page.requests.map((request) => request.url), ['/api/settings/appearance'])
  assert.equal(page.requests[0].options.credentials, 'omit')
  await page.done
  assert.equal(page.attrs['data-skin'], 'green')
  assert.ok(page.links.some((link) => link.rel === 'preload' && link.as === 'font' && link.href === THEME_FONT_PRELOAD.green), 'шрифт новой темы не предзагружен')
  assert.equal(page.meta.content, THEME_BROWSER_COLOR.green)
  assert.deepEqual(JSON.parse(page.storage.get(THEME_STORAGE_KEY)), { theme: 'green', at: 1_000_000 })
})

test('следующая страница из кэша: тема из памяти ставится сразу, до ответа настройки', async () => {
  const page = fakeWindow({ skin: 'iznik', stored: { theme: 'green', at: 1_000_000 - 5_000 }, apiTheme: 'green' })
  catchUpTheme(page.w, cfg())
  assert.equal(page.attrs['data-skin'], 'green', 'тема из памяти должна примениться синхронно')
  // Страница и память расходятся — сверяем, кто прав.
  assert.equal(page.requests.length, 1)
  await page.done
  assert.equal(page.attrs['data-skin'], 'green')
})

test('память оказалась старее страницы: настройка возвращает тему страницы', async () => {
  const page = fakeWindow({ skin: 'green', stored: { theme: 'iznik', at: 1_000_000 - 5_000 }, apiTheme: 'green' })
  catchUpTheme(page.w, cfg())
  assert.equal(page.requests.length, 1)
  await page.done
  assert.equal(page.attrs['data-skin'], 'green')
  assert.equal(JSON.parse(page.storage.get(THEME_STORAGE_KEY)).theme, 'green')
})

test('страница и память согласны, сверка была меньше минуты назад — запроса нет', () => {
  const page = fakeWindow({ skin: 'green', stored: { theme: 'green', at: 1_000_000 - (THEME_RECHECK_MS - 1) } })
  catchUpTheme(page.w, cfg())
  assert.equal(page.requests.length, 0)
  assert.equal(page.attrs['data-skin'], 'green')
})

test('сверка была больше минуты назад — один запрос, смена темы в админке подхватывается', async () => {
  const page = fakeWindow({ skin: 'green', stored: { theme: 'green', at: 1_000_000 - THEME_RECHECK_MS }, apiTheme: 'cream' })
  catchUpTheme(page.w, cfg())
  assert.equal(page.requests.length, 1)
  await page.done
  assert.equal(page.attrs['data-skin'], 'cream')
})

test('предпросмотр ?skin= не перебивается', () => {
  for (const search of ['?skin=iznik', '?utm_source=x&skin=iznik']) {
    const page = fakeWindow({ skin: 'iznik', stored: { theme: 'green', at: 1_000_000 }, search })
    catchUpTheme(page.w, cfg())
    assert.equal(page.attrs['data-skin'], 'iznik')
    assert.equal(page.requests.length, 0)
  }
  // Чужое значение параметра предпросмотром не считается.
  const page = fakeWindow({ skin: 'iznik', search: '?skin=unknown' })
  catchUpTheme(page.w, cfg())
  assert.equal(page.requests.length, 1)
})

test('статически собранная страница (404) без темы получает её из настройки', async () => {
  const page = fakeWindow({ skin: '', apiTheme: 'iznik' })
  catchUpTheme(page.w, cfg())
  await page.done
  assert.equal(page.attrs['data-skin'], 'iznik')
})

test('сбой настройки, чужая тема и недоступная память страницу не ломают', async () => {
  const failed = fakeWindow({ skin: 'iznik', apiOk: false })
  catchUpTheme(failed.w, cfg())
  await failed.done
  assert.equal(failed.attrs['data-skin'], 'iznik')
  assert.equal(failed.storage.size, 0)

  const unknown = fakeWindow({ skin: 'iznik', apiTheme: 'neon' })
  catchUpTheme(unknown.w, cfg())
  await unknown.done
  assert.equal(unknown.attrs['data-skin'], 'iznik')

  const privateMode = fakeWindow({ skin: 'iznik', apiTheme: 'green', brokenStorage: true })
  catchUpTheme(privateMode.w, cfg())
  await privateMode.done
  assert.equal(privateMode.attrs['data-skin'], 'green')

  assert.doesNotThrow(() => catchUpTheme({}, cfg()))
})

test('адрес настройки: на сайте /api, на локальном стенде — бэкенд на :8000, из сборки — как задан', () => {
  const site = fakeWindow({ skin: 'iznik' })
  catchUpTheme(site.w, cfg(''))
  assert.equal(site.requests[0].url, '/api/settings/appearance')
  const local = fakeWindow({ skin: 'iznik', origin: 'http://localhost:3000' })
  catchUpTheme(local.w, cfg(''))
  assert.equal(local.requests[0].url, 'http://localhost:8000/api/settings/appearance')

  assert.equal(themeApiBaseFromEnv({}), '')
  assert.equal(themeApiBaseFromEnv({ NEXT_PUBLIC_API_BASE: '/api' }), '/api')
  assert.equal(themeApiBaseFromEnv({ NEXT_PUBLIC_BACKEND_URL: 'https://example.test/' }), 'https://example.test/api')
})

test('текст скрипта для <head> самодостаточен и делает то же самое', async () => {
  const script = themeCatchUpScript('/api')
  assert.ok(!script.includes('</script') && script.length < 4000, 'скрипт в <head> должен быть маленьким')
  const page = fakeWindow({ skin: 'iznik', apiTheme: 'green' })
  new Function('window', script)(page.w)
  await page.done
  assert.equal(page.attrs['data-skin'], 'green')
})

test('скрипт стоит в <head> после предзагрузки шрифта и theme-color, прежнего запроса в _app нет', async () => {
  const document = await readFile(new URL('../pages/_document.tsx', import.meta.url), 'utf8')
  const script = document.indexOf('<script id="theme-catch-up" dangerouslySetInnerHTML={{ __html: themeCatchUpScript() }} />')
  assert.ok(script > document.indexOf('<meta name="theme-color"') && document.indexOf('<meta name="theme-color"') > document.indexOf('rel="preload"'))
  assert.ok(script < document.indexOf('</Head>'))
  const app = await readFile(new URL('../pages/_app.tsx', import.meta.url), 'utf8')
  assert.ok(!app.includes('settings/appearance'), 'тему сверяет скрипт в <head>, второй запрос из _app не нужен')
})
