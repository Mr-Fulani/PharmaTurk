import test from 'node:test'
import assert from 'node:assert/strict'

import { buildCatalogPageQuery, parseBrandIds, parseCatalogFiltersQuery } from './catalogQuery.js'

test('pagination preserves the selected brand', () => {
  assert.deepEqual(
    buildCatalogPageQuery({ slug: 'medicines', brand_id: '42' }, 2),
    { slug: 'medicines', brand_id: '42', page: '2' }
  )
})

test('filter change updates brands and resets pagination', () => {
  const filters = {
    categories: [], categorySlugs: [], brands: [42, 77], subcategories: [],
    subcategorySlugs: [], genders: [], fragranceTypes: [], authorIds: [], genreIds: [],
    publishers: [], languages: [], inStock: false, isNew: false, sortBy: 'name_asc', attributes: {}
  }
  assert.deepEqual(
    buildCatalogPageQuery(
      { slug: 'medicines', page: '3', brand: 'legacy-brand' },
      1,
      { filters }
    ),
    { slug: 'medicines', brand_id: ['42', '77'] }
  )
})

test('parseBrandIds supports repeated and comma-separated query values', () => {
  assert.deepEqual(parseBrandIds(['42', '77,42', 'invalid']), [42, 77])
})

test('all sidebar filters survive pagination and can be restored from query', () => {
  const defaults = {
    categories: [], categorySlugs: [], brands: [], brandSlugs: [], subcategories: [],
    subcategorySlugs: [], genders: [], fragranceTypes: [], authorIds: [], genreIds: [],
    publishers: [], languages: [], inStock: false, isNew: false, sortBy: 'name_asc', attributes: {}
  }
  const filters = {
    ...defaults,
    genders: ['women'],
    priceMin: 100,
    priceMax: 500,
    inStock: true,
    sortBy: 'price_asc',
    attributes: { color: ['red', 'blue'] },
  }

  const pageOneQuery = buildCatalogPageQuery({ slug: 'clothing', page: '4' }, 1, { filters })
  const pageTwoQuery = buildCatalogPageQuery(pageOneQuery, 2)

  assert.deepEqual(pageTwoQuery, {
    slug: 'clothing',
    page: '2',
    gender: 'women',
    price_min: '100',
    price_max: '500',
    in_stock: '1',
    ordering: 'price_asc',
    attr_color: ['red', 'blue'],
  })
  assert.deepEqual(parseCatalogFiltersQuery(pageTwoQuery, defaults), filters)
})
