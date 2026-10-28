import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildBrandProductsParams,
  brandProductsRequestKey,
  brandDescriptionText,
  brandTitleCategories,
  isThinBrand,
  shouldShowGenderFilter,
} from './brandCatalog.js'

const baseFilters = {
  categories: [],
  categorySlugs: [],
  brands: [],
  brandSlugs: [],
  subcategories: [],
  subcategorySlugs: [],
  genders: [],
  inStock: false,
  isNew: false,
  sortBy: 'name_asc',
}

test('default filters produce only page, page_size, compact view and ordering', () => {
  assert.deepEqual(buildBrandProductsParams(baseFilters, 1, 24), {
    page: 1,
    page_size: 24,
    view: 'card',
    ordering: 'name_asc',
  })
})

test('category slugs take precedence over category ids', () => {
  const filters = { ...baseFilters, categories: [5, 7], categorySlugs: ['clothing', 'shoes'] }
  const params = buildBrandProductsParams(filters, 1, 24)
  assert.equal(params.category_slug, 'clothing,shoes')
  assert.equal(params.category_id, undefined)
})

test('category ids are used when slugs are absent', () => {
  const filters = { ...baseFilters, categories: [5, 7] }
  assert.deepEqual(buildBrandProductsParams(filters, 1, 24).category_id, [5, 7])
})

test('gender, price and flags map to query params', () => {
  const filters = {
    ...baseFilters,
    genders: ['women', 'kids'],
    priceMin: 100,
    priceMax: 500,
    inStock: true,
    isNew: true,
    sortBy: 'price_desc',
  }
  assert.deepEqual(buildBrandProductsParams(filters, 3, 24), {
    page: 3,
    page_size: 24,
    view: 'card',
    gender: 'women,kids',
    price_min: 100,
    price_max: 500,
    in_stock: true,
    is_new: true,
    ordering: 'price_desc',
  })
})

test('request key matches for identical filters and differs otherwise', () => {
  const key1 = brandProductsRequestKey('nike', buildBrandProductsParams(baseFilters, 1, 24))
  const key2 = brandProductsRequestKey('nike', buildBrandProductsParams({ ...baseFilters }, 1, 24))
  const otherPage = brandProductsRequestKey('nike', buildBrandProductsParams(baseFilters, 2, 24))
  const otherSlug = brandProductsRequestKey('adidas', buildBrandProductsParams(baseFilters, 1, 24))
  assert.equal(key1, key2)
  assert.notEqual(key1, otherPage)
  assert.notEqual(key1, otherSlug)
})

test('gender filter is shown for fashion categories only', () => {
  assert.equal(shouldShowGenderFilter(['clothing', 'medicines']), true)
  assert.equal(shouldShowGenderFilter(['islamic_clothing']), true)
  assert.equal(shouldShowGenderFilter(['SHOES']), true)
  assert.equal(shouldShowGenderFilter(['auto-parts']), false)
  assert.equal(shouldShowGenderFilter(['medicines', 'supplements']), false)
  assert.equal(shouldShowGenderFilter([]), false)
  assert.equal(shouldShowGenderFilter(undefined), false)
})

test('brand description text tolerates brands without description', () => {
  assert.equal(brandDescriptionText(null), '')
  assert.equal(brandDescriptionText(undefined), '')
  assert.equal(brandDescriptionText('<p>Немецкий</p>бренд'), ' Немецкий бренд')
})

test('brand with one or two products is thin, three is enough', () => {
  assert.equal(isThinBrand(0), true)
  assert.equal(isThinBrand(2), true)
  assert.equal(isThinBrand(3), false)
  assert.equal(isThinBrand(undefined), true)
})

test('brand title names two main sections, medicines as a plain word', () => {
  const categories = [
    { slug: 'supplements', name: 'БАДы', product_count: 29, translations: [{ locale: 'en', name: 'Supplements' }] },
    { slug: 'medicines', name: 'Медицина', product_count: 212, translations: [{ locale: 'en', name: 'Medicine' }] },
    { slug: 'perfumery', name: 'Парфюмерия', product_count: 3 },
  ]
  assert.equal(brandTitleCategories(categories, 'ru', 'лекарства'), 'лекарства, БАДы')
  assert.equal(brandTitleCategories(categories, 'en', 'medicines'), 'medicines, supplements')
  assert.equal(brandTitleCategories([{ slug: 'furniture', name: 'Мебель', product_count: 5 }], 'ru', 'лекарства'), 'мебель')
  assert.equal(brandTitleCategories([], 'ru', 'лекарства'), '')
})
