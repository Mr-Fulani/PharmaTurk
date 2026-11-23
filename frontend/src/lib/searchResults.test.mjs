import assert from 'node:assert/strict'
import test from 'node:test'

import {
  appendSearchPage,
  nextSearchSource,
  readSearchInfo,
  readSearchPage,
  searchProductParams,
  searchServiceParams,
  readSearchFacets,
  readSearchFilters,
  hasSearchFilters,
  searchPageQuery,
  SEARCH_PAGE_SIZE,
} from './searchResults.js'

test('first page has no page param, next pages ask for the page number', () => {
  assert.deepEqual(searchProductParams('нурофен'), {
    search: 'нурофен',
    page_size: SEARCH_PAGE_SIZE,
    view: 'card',
    include_facets: false,
    search_facets: 1,
    search_source: 'page',
  })
  assert.equal(searchProductParams('нурофен', 3).page, 3)
  assert.equal(searchProductParams('нурофен', 3).search_source, 'page')
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
  assert.deepEqual(readSearchInfo({ search_info: { mode: 'partial', query: 'диклофенак' } }), { mode: 'partial', query: 'диклофенак' })
  assert.equal(readSearchInfo({ search_info: { mode: 'other', query: 'x' } }), null)
  assert.equal(readSearchInfo({ results: [] }), null)
  assert.equal(readSearchInfo([]), null)
})

test('filters come from the address and go to the API; filtered search is not counted', () => {
  const filters = readSearchFilters({ type: 'shoes', brand: '12', available: '1', sort: 'price_asc' })
  assert.deepEqual(filters, { type: 'shoes', brand: 12, available: true, sort: 'price_asc' })
  assert.equal(hasSearchFilters(filters), true)
  const params = searchProductParams('кроссовки', 1, filters)
  assert.deepEqual(
    [params.product_type, params.brand_id, params.is_available, params.ordering, params.search_facets, params.search_source],
    ['shoes', 12, true, 'price_asc', 1, 'page'],
  )
  assert.equal(searchProductParams('кроссовки', 2, filters).search_facets, undefined)
  // Мусор в адресе не ломает страницу; сортировка сама по себе фильтром не считается.
  const plain = readSearchFilters({ brand: 'abc', sort: 'drop table', type: ['a', 'b'] })
  assert.deepEqual(plain, { type: 'a', brand: null, available: false, sort: 'relevance' })
  assert.equal(hasSearchFilters(readSearchFilters({ sort: 'newest' })), false)
  assert.equal(searchProductParams('кроссовки', 1, readSearchFilters({ sort: 'newest' })).search_source, 'page')
  assert.deepEqual(searchPageQuery('кроссовки', filters), { query: 'кроссовки', type: 'shoes', brand: '12', available: '1', sort: 'price_asc' })
  assert.deepEqual(searchPageQuery('кроссовки', plain), { query: 'кроссовки', type: 'a' })
})

test('facets ignore malformed rows', () => {
  const facets = readSearchFacets({
    search_facets: { types: [{ value: 'shoes', count: 5 }, { value: 'x', count: 0 }, null], brands: [{ id: 1, name: 'Nike', count: 3 }, { id: 'x' }] },
  })
  assert.deepEqual(facets, { types: [{ value: 'shoes', count: 5 }], brands: [{ id: 1, name: 'Nike', count: 3 }] })
  assert.deepEqual(readSearchFacets([]), { types: [], brands: [] })
})
