import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildCategoryBrandParams,
  buildCatalogPageQuery,
  getDefaultCatalogSort,
  normalizeCatalogFacets,
  parseBrandIds,
  parseCatalogFiltersQuery,
} from './catalogQuery.js'

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

test('default sort stays out of the URL and an explicit name sort is kept for ranked catalogs', () => {
  const filters = {
    categories: [], categorySlugs: [], brands: [], subcategories: [],
    subcategorySlugs: [], genders: [], fragranceTypes: [], authorIds: [], genreIds: [],
    publishers: [], languages: [], inStock: false, isNew: false, sortBy: 'popular', attributes: {}
  }
  const defaultSortBy = getDefaultCatalogSort('medicines')
  assert.equal(defaultSortBy, 'popular')
  assert.equal(getDefaultCatalogSort('supplements'), 'popular')
  assert.equal(getDefaultCatalogSort('shoes'), 'name_asc')
  assert.deepEqual(
    buildCatalogPageQuery({ slug: 'medicines' }, 1, { filters, defaultSortBy }),
    { slug: 'medicines' }
  )
  assert.deepEqual(
    buildCatalogPageQuery({ slug: 'medicines' }, 1, { filters: { ...filters, sortBy: 'name_asc' }, defaultSortBy }),
    { slug: 'medicines', ordering: 'name_asc' }
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

test('furniture brands use the category directory regardless of products and filters', () => {
  assert.deepEqual(buildCategoryBrandParams({
    productType: 'furniture',
    categoryType: 'furniture',
    routeSlug: 'furniture',
    categorySlugs: ['bedroom'],
    categoryIds: [32],
    inStock: true,
  }), {
    product_type: 'furniture',
    count_scope: 'filtered',
    page_size: 500,
    primary_category_slug: 'furniture',
  })
})

test('other category brand lists can still follow active product filters', () => {
  assert.deepEqual(buildCategoryBrandParams({
    productType: 'clothing',
    categoryType: 'clothing',
    routeSlug: 'clothing',
    categorySlugs: ['women-clothing'],
    inStock: true,
  }), {
    product_type: 'clothing',
    count_scope: 'filtered',
    page_size: 500,
    primary_category_slug: 'clothing',
    category_slug: 'women-clothing',
    in_stock: true,
  })
})

test('missing facet fields clear state instead of retaining the previous category', () => {
  assert.deepEqual(normalizeCatalogFacets({ results: [] }), {
    attributes: [],
    genders: [],
    fragranceTypes: [],
  })
  assert.deepEqual(normalizeCatalogFacets(null), {
    attributes: [],
    genders: [],
    fragranceTypes: [],
  })
})

test('facet normalization preserves arrays returned by the API', () => {
  const attributes = [{ key: 'color', name: 'Color', values: ['Blue'] }]
  assert.deepEqual(normalizeCatalogFacets({
    available_attributes: attributes,
    available_genders: ['unisex'],
    available_fragrance_types: ['eau-de-parfum'],
  }), {
    attributes,
    genders: ['unisex'],
    fragranceTypes: ['eau-de-parfum'],
  })
})
