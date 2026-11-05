import assert from 'node:assert/strict'
import test from 'node:test'

import {
  appendSearchPage,
  nextSearchSource,
  readSearchInfo,
  readSearchPage,
  searchProductParams,
  searchServiceParams,
  SEARCH_PAGE_SIZE,
} from './searchResults.js'

test('first page has no page param, next pages ask for the page number', () => {
  assert.deepEqual(searchProductParams('нурофен'), {
    search: 'нурофен',
    page_size: SEARCH_PAGE_SIZE,
    view: 'card',
    include_facets: false,
  })
  assert.equal(searchProductParams('нурофен', 3).page, 3)
})

test('paginated response gives total count and whether more pages exist', () => {
  const page = readSearchPage({ count: 140, next: 'https://x/api?page=2', results: [{ id: 1 }] })
  assert.deepEqual(page, { results: [{ id: 1 }], count: 140, hasMore: true })
  assert.equal(readSearchPage({ count: 1, next: null, results: [{ id: 1 }] }).hasMore, false)
})

test('plain array response is a single page', () => {
  assert.deepEqual(readSearchPage([{ id: 1 }, { id: 2 }]), {
    results: [{ id: 1 }, { id: 2 }],
    count: 2,
    hasMore: false,
  })
  assert.deepEqual(readSearchPage(null), { results: [], count: 0, hasMore: false })
})

test('next page is appended without duplicates', () => {
  assert.deepEqual(appendSearchPage([{ id: 1 }, { id: 2 }], [{ id: 2 }, { id: 3 }]), [
    { id: 1 },
    { id: 2 },
    { id: 3 },
  ])
})

test('services are paged the same way, without facets flag', () => {
  assert.deepEqual(searchServiceParams('массаж', 2), { search: 'массаж', page_size: SEARCH_PAGE_SIZE, view: 'card', page: 2 })
})

test('show more loads products first, then services', () => {
  assert.equal(nextSearchSource({ hasMore: true }, { hasMore: true }), 'products')
  assert.equal(nextSearchSource({ hasMore: false }, { hasMore: true }), 'services')
  assert.equal(nextSearchSource({ hasMore: false }, { hasMore: false }), null)
})

test('search_info is shown only for known correction modes', () => {
  assert.deepEqual(readSearchInfo({ search_info: { mode: 'layout', query: 'нурофен' } }), { mode: 'layout', query: 'нурофен' })
  assert.equal(readSearchInfo({ search_info: { mode: 'other', query: 'x' } }), null)
  assert.equal(readSearchInfo({ results: [] }), null)
  assert.equal(readSearchInfo([]), null)
})
