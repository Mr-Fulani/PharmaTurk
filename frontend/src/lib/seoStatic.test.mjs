import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const robots = await readFile(new URL('../../public/robots.txt', import.meta.url), 'utf8')

test('robots keeps render-critical Next.js assets crawlable', () => {
  assert.doesNotMatch(robots, /^\s*Disallow:\s*\/_next(?:\/|\s*$)/im)
})

test('robots advertises the canonical sitemap index', () => {
  assert.match(robots, /^\s*Sitemap:\s*https:\/\/mudaroba\.com\/sitemap\.xml\s*$/im)
})

test('robots: Clean-param для Яндекса — только метки, без параметров самого сайта', () => {
  const lines = robots.match(/^\s*Clean-param:.*$/gim) || []
  assert.ok(lines.length > 0)
  // page/sort/фильтры/поиск меняют содержимое (их обрабатывают canonical и noindex),
  // поэтому в правиле допустимы только метки из этого списка
  const tracking = new Set([
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
    'yclid', 'ysclid', 'gclid', 'fbclid', '_openstat',
  ])
  const params = []
  for (const line of lines) {
    // Яндекс ограничивает правило 500 символами
    assert.ok(line.length <= 500)
    params.push(...line.replace(/^\s*Clean-param:\s*/i, '').split(/\s+/)[0].split('&'))
  }
  for (const name of params) {
    assert.ok(tracking.has(name), `не метка: ${name}`)
  }
  for (const name of ['utm_source', 'utm_medium', 'utm_campaign', 'yclid', 'ysclid']) {
    assert.ok(params.includes(name), name)
  }
})

const llms = await readFile(new URL('../../public/llms.txt', import.meta.url), 'utf8')

test('llms.txt: заголовок, краткое описание и только адреса mudaroba.com без /ru', () => {
  assert.match(llms, /^# Mudaroba\n\n> \S/)
  const urls = llms.match(/https?:\/\/[^\s)]+/g) || []
  assert.ok(urls.length > 10)
  for (const url of urls.filter((u) => !u.startsWith('https://t.me/'))) {
    assert.match(url, /^https:\/\/mudaroba\.com(\/|$)/)
    assert.doesNotMatch(url, /^https:\/\/mudaroba\.com\/ru(\/|$)/)
  }
})
