import assert from 'node:assert/strict'
import { access, readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  DEFAULT_THEME,
  HOME_BLOCK_KEYS,
  THEMES,
  THEME_FONT_PRELOAD,
  fallbackAppearance,
  normalizeAppearance,
  normalizeTheme,
  visibleHomeBlocks,
} from './siteAppearance.js'

const repo = (path) => new URL(`../../../${path}`, import.meta.url)

test('неизвестная или пустая тема — «Кремовая»', () => {
  assert.equal(DEFAULT_THEME, 'cream')
  assert.equal(normalizeTheme('iznik'), 'iznik')
  for (const value of [undefined, null, '', 'dark', 'IZNIK', 42]) assert.equal(normalizeTheme(value), 'cream')
})

test('блоки главной: порядок из админки, выключенные скрыты, чужие ключи отброшены', () => {
  const blocks = [
    { key: 'facts', is_enabled: true },
    { key: 'brands', is_enabled: false },
    { key: 'promo_from_future', is_enabled: true },
    { key: 'main_banner', is_enabled: true },
    { key: 'facts', is_enabled: false },
  ]
  const visible = visibleHomeBlocks(blocks)

  assert.deepEqual(visible.slice(0, 2), ['facts', 'main_banner'])
  assert.ok(!visible.includes('brands'))
  assert.ok(!visible.includes('promo_from_future'))
  // Блок без записи в ответе не пропадает с главной.
  assert.ok(visible.includes('categories'))
  assert.equal(new Set(visible).size, visible.length)
})

test('ответ по умолчанию даёт прежнюю главную', () => {
  const data = { theme: 'cream', home_blocks: HOME_BLOCK_KEYS.map((key) => ({ key, is_enabled: true })) }

  assert.deepEqual(normalizeAppearance(data), { theme: 'cream', homeBlocks: [...HOME_BLOCK_KEYS] })
})

test('настройки не получены — «Кремовая» и главная без блока отзывов', () => {
  const fallback = fallbackAppearance()

  assert.deepEqual(normalizeAppearance(undefined), fallback)
  assert.deepEqual(normalizeAppearance({ theme: 'green', home_blocks: 'oops' }).homeBlocks, fallback.homeBlocks)
  assert.equal(fallback.theme, 'cream')
  assert.deepEqual(fallback.homeBlocks, HOME_BLOCK_KEYS.filter((key) => key !== 'testimonials'))
})

test('темы и блоки совпадают с бэкендом и стилями', async () => {
  const models = await readFile(repo('backend/apps/settings/models.py'), 'utf8')
  const theme = models.slice(models.indexOf('class Theme('), models.indexOf('theme = models.CharField'))
  assert.deepEqual([...theme.matchAll(/= "([a-z]+)",/g)].map((m) => m[1]), [...THEMES])

  const seed = await readFile(repo('backend/apps/settings/migrations/0005_seed_home_blocks.py'), 'utf8')
  const seeded = seed.slice(seed.indexOf('HOME_BLOCKS = ['), seed.indexOf(']', seed.indexOf('HOME_BLOCKS = [')))
  assert.deepEqual([...seeded.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]), [...HOME_BLOCK_KEYS])

  const css = await readFile(repo('frontend/styles/globals.css'), 'utf8')
  for (const skin of THEMES.filter((name) => name !== DEFAULT_THEME)) {
    assert.ok(css.includes(`html[data-skin='${skin}']`), `в globals.css нет темы ${skin}`)
  }
})

test('у каждой темы есть шрифт для предзагрузки', async () => {
  assert.deepEqual(Object.keys(THEME_FONT_PRELOAD).sort(), [...THEMES].sort())
  for (const path of Object.values(THEME_FONT_PRELOAD)) await access(repo(`frontend/public${path}`))
})
