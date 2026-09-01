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
