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
