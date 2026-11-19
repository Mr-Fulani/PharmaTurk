// Лекарства не стоят в «Хитах продаж»: для них справочный блок главной без торговых слов
// (решение владельца 19.11.2026, docs/HOME_BLOCKS.md).
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const read = (path) => readFile(new URL(`../../${path}`, import.meta.url), 'utf8')
const locale = async (lang) => JSON.parse(await read(`public/locales/${lang}/common.json`))

test('справочный блок лекарств: свой список, без торговых слов и кнопки «В заявку»', async () => {
  const block = await read('src/components/MedicineReferenceBlock.tsx')
  assert.ok(block.includes("'/catalog/products/medicine-reference'"))
  assert.ok(block.includes("buildProductUrl('medicines', medicine.slug)"), 'карточка ведёт на страницу препарата')
  assert.ok(!/AddToCart|FavoriteButton|<button/.test(block), 'в блоке нет кнопок')

  const banned = /хит|продаж|купи|заказ|заявк|bestseller|\bhit\b|\bbuy\b|\border\b|sale/i
  for (const lang of ['ru', 'en']) {
    const strings = await locale(lang)
    for (const key of ['medicine_reference_title', 'medicine_reference_subtitle', 'medicine_reference_price', 'medicine_reference_all']) {
      assert.ok(strings[key], `нет перевода ${key} (${lang})`)
      assert.ok(!banned.test(strings[key]), `торговое слово в ${key} (${lang}): ${strings[key]}`)
    }
  }
  const visibleText = [...block.matchAll(/t\('[a-z_]+', '([^']+)'\)/g)].map((match) => match[1])
  assert.equal(visibleText.length, 4)
  for (const text of visibleText) assert.ok(!banned.test(text), text)
})

test('«Хиты продаж» не добирают лекарства из новинок', async () => {
  const carousel = await read('src/components/PopularProductsCarousel.tsx')
  assert.ok(carousel.includes("'/catalog/products/featured'"))
  assert.ok(carousel.includes(".filter((product: Product) => product.product_type !== 'medicines')"))
})

test('подвал: подпись об оплате видна всегда и относится к товарам, кроме лекарств', async () => {
  const footer = await read('src/components/Footer.tsx')
  assert.ok(footer.includes('<p className="mt-2 text-xs text-main opacity-80">{cryptoText}</p>'))
  assert.equal(footer.split('{cryptoText}').length, 2, 'подпись стоит один раз, не во всплывающей подсказке')
  assert.match((await locale('ru')).footer_crypto_payment, /кроме лекарств/)
  assert.match((await locale('en')).footer_crypto_payment, /other than medicines/)
  // Текст по умолчанию в коде подвала совпадает с переводом и с настройкой в админке.
  assert.ok(footer.includes(`const CRYPTO_DEFAULT_RU = '${(await locale('ru')).footer_crypto_payment}'`))
  const model = await read('../backend/apps/settings/models.py')
  const fromModel = [...model.matchAll(/^\s+"(Оплата — по согласованию[^"]*|Относится к товарам[^"]*)"/gm)].map((m) => m[1]).join('')
  assert.equal(fromModel, (await locale('ru')).footer_crypto_payment)
})

test('страница лекарства: og:type не «product», цена и кнопка заявки под data-nosnippet', async () => {
  const page = await read('src/pages/product/[[...slug]].tsx')
  assert.ok(page.includes("og:type\" content={isService || isMedicine ? 'website' : 'product'}"))
  assert.ok(!page.includes('product:price'), 'мета цены для лекарств не отдаются')
  assert.ok(page.includes("const medicineNoSnippet = isMedicine ? { 'data-nosnippet': '' } : {}"))
  // Цена (обычная и «цена по запросу» больничного), подпись «Больничный препарат» у цены,
  // блок кнопок и нижняя панель телефона; сама страница индексируется.
  assert.equal(page.split('{...medicineNoSnippet}').length - 1, 5)
  assert.ok(page.includes('<p {...medicineNoSnippet} className="mt-1 text-sm leading-relaxed'))
  assert.ok(page.includes('<div ref={actionBlockRef} {...medicineNoSnippet}'))
  assert.ok(!/name="robots" content="[^"]*nosnippet/.test(page))
})
