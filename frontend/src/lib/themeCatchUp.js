// Страница догоняет тему сама (решение владельца 13.11.2026, docs/DESIGN_THEMES.md).
// HTML разделов и карточек лежит в кэше CDN до суток, поэтому после смены темы в админке
// он ещё какое-то время приходит со старым data-skin. Маленький скрипт в <head> сверяет
// тему страницы с настройкой и ставит актуальную — без ключей CDN и без его очистки.

import { THEMES, THEME_BROWSER_COLOR, THEME_FONT_PRELOAD } from './siteAppearance.js'

export const THEME_STORAGE_KEY = 'site-theme'
// Чаще раза в минуту посетитель настройку не запрашивает (если страница и память согласны).
export const THEME_RECHECK_MS = 60_000

/**
 * Тело инлайн-скрипта. Попадает в HTML через toString(), поэтому самодостаточно: ничего
 * не берёт из модуля, всё нужное приходит в cfg; синтаксис — без того, что сборщик
 * заменяет вспомогательными функциями. В тестах вызывается напрямую с поддельным окном.
 */
export function catchUpTheme(w, cfg) {
  try {
    var doc = w.document
    var root = doc.documentElement
    // Предпросмотр ?skin=<тема> не перебиваем.
    var preview = /[?&]skin=([^&#]*)/.exec(w.location.search || '')
    if (preview && cfg.themes.indexOf(preview[1]) !== -1) return

    var htmlTheme = root.getAttribute('data-skin') || ''
    var stored = null
    try {
      stored = JSON.parse(w.localStorage.getItem(cfg.key) || 'null')
    } catch (error) {
      stored = null
    }

    var apply = function (theme) {
      if (cfg.themes.indexOf(theme) === -1 || root.getAttribute('data-skin') === theme) return
      // Шрифт темы — заранее, до первой отрисовки текста: меньше сдвиг при подмене шрифта.
      var font = cfg.fonts[theme]
      if (font && !doc.querySelector('link[rel="preload"][href="' + font + '"]')) {
        var link = doc.createElement('link')
        link.rel = 'preload'
        link.as = 'font'
        link.type = 'font/woff2'
        link.crossOrigin = 'anonymous'
        link.href = font
        doc.head.appendChild(link)
      }
      root.setAttribute('data-skin', theme)
      var meta = doc.querySelector('meta[name="theme-color"]')
      if (meta && cfg.colors[theme]) meta.setAttribute('content', cfg.colors[theme])
    }

    // Тема из прошлой сверки — сразу, до первой отрисовки: страница из кэша не мелькает старой.
    var known = !!stored && cfg.themes.indexOf(stored.theme) !== -1
    if (known) apply(stored.theme)
    // Страница и память согласны, сверка была недавно — запрос не нужен.
    if (known && stored.theme === htmlTheme && w.Date.now() - stored.at < cfg.recheckMs) return

    var base = cfg.apiBase
    if (!base) {
      // Как getClientApiBase(): на сайте — /api, на локальном стенде — бэкенд на :8000.
      var origin = w.location.origin
      if (!/:\d+$/.test(origin)) base = '/api'
      else base = origin.replace(/:\d+$/, '') + ':8000/api'
    }
    w.fetch(base + '/settings/appearance', { credentials: 'omit' })
      .then(function (response) {
        return response.ok ? response.json() : null
      })
      .then(function (data) {
        if (!data || cfg.themes.indexOf(data.theme) === -1) return
        try {
          w.localStorage.setItem(cfg.key, JSON.stringify({ theme: data.theme, at: w.Date.now() }))
        } catch (error) {
          // Память браузера недоступна (частный режим) — тема всё равно применится.
        }
        apply(data.theme)
      })
      .catch(function () {})
  } catch (error) {
    // Сверка темы не должна ломать страницу.
  }
}

// Переменные называем буквально: Next подставляет NEXT_PUBLIC_* при сборке только так.
const BUILD_ENV = {
  NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE,
  NEXT_PUBLIC_BACKEND_URL: process.env.NEXT_PUBLIC_BACKEND_URL,
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
}

/** Адрес API из переменных сборки — как в getClientApiBase(); пусто — определит сам скрипт. */
export function themeApiBaseFromEnv(env = BUILD_ENV) {
  const base = env.NEXT_PUBLIC_API_BASE || env.NEXT_PUBLIC_BACKEND_URL || env.NEXT_PUBLIC_API_URL || ''
  if (!base) return ''
  const trimmed = base.replace(/\/+$/, '')
  return trimmed.endsWith('/api') ? trimmed : `${trimmed}/api`
}

/** Текст инлайн-скрипта для <head>. */
export function themeCatchUpScript(apiBase = themeApiBaseFromEnv()) {
  const cfg = {
    themes: [...THEMES],
    fonts: THEME_FONT_PRELOAD,
    colors: THEME_BROWSER_COLOR,
    key: THEME_STORAGE_KEY,
    recheckMs: THEME_RECHECK_MS,
    apiBase,
  }
  // «<» экранируем: JSON внутри <script> не должен закрыть тег.
  return `(${catchUpTheme.toString()})(window,${JSON.stringify(cfg).replace(/</g, '\\u003c')})`
}
