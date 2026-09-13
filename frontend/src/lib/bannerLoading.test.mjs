import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
const require = createRequire(import.meta.url)
const Image = () => null
const media = [1, 2, 3].map(id => ({ id, content_type: 'image', content_url: `https://cdn.mudaroba.com/${id}.webp`, title: `Slide ${id}` }))
async function renderer(file) {
  const compiled = ts.transpileModule(await readFile(new URL(file, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText
  const states = []
  let cursor = 0
  const exports = {}
  const modules = {
    react: {
      useState(initial) { const i = cursor++; if (!(i in states)) states[i] = typeof initial === 'function' ? initial() : initial; return [states[i], value => { states[i] = typeof value === 'function' ? value(states[i]) : value }] },
      useRef(initial) { const i = cursor++; if (!(i in states)) states[i] = { current: initial }; return states[i] },
      useEffect() {}, useCallback: fn => fn,
    },
    'react/jsx-runtime': require('react/jsx-runtime'), 'next/image': Image,
    'next/router': { useRouter: () => ({ locale: 'ru' }) },
    'next-i18next': { useTranslation: () => ({ t: (_, fallback) => fallback }) },
    '../lib/media': { resolveMediaUrl: url => url, getPlaceholderImageUrl: () => '/fallback.svg', getVideoEmbedUrl: () => null, withListingImageMaxWidth: url => url },
    '../lib/api': {}, './BannerCarousel.module.css': {},
  }
  vm.runInNewContext(compiled, { exports, require: name => modules[name], URL, setInterval, clearInterval, Date })
  return props => { cursor = 0; return exports.default(props) }
}
function nodes(node, match) {
  if (!node || typeof node !== 'object') return []
  if (Array.isArray(node)) return node.flatMap(n => nodes(n, match))
  return [...(match(node) ? [node] : []), ...nodes(node.props?.children, match)]
}
const props = position => ({ position, initialBanners: [{ id: 1, position, media_files: media }] })
test('only the main hero is eager and high priority in the initial render', async () => {
  for (const position of ['main', 'after_brands', 'before_footer', 'after_popular_products']) {
    const render = await renderer('../components/BannerCarouselMedia.tsx')
    const images = nodes(render(props(position)), node => node.type === Image)
    assert.equal(images.filter(i => i.props.priority).length, position === 'main' ? 1 : 0)
    assert.equal(images[0].props.loading, position === 'main' ? 'eager' : 'lazy')
    assert.equal(images[0].props.fetchPriority, position === 'main' ? 'high' : 'auto')
    assert.ok(images[0].props.sizes.includes('(max-width: 480px) 740px'))
  }
})
test('rotation preserves the original hero source size and priority', async () => {
  const render = await renderer('../components/BannerCarouselMedia.tsx')
  let tree = render(props('main'))
  const first = nodes(tree, n => n.type === Image)[0].props
  nodes(tree, n => n.props?.['aria-label'] === 'Следующее медиа')[0].props.onClick()
  tree = render(props('main'))
  const images = nodes(tree, n => n.type === Image)
  assert.equal(images[0].props.alt, 'Slide 2')
  const original = images.find(i => i.props.alt === 'Slide 1').props
  assert.equal(original.sizes, first.sizes)
  assert.equal(original.src, first.src)
  assert.equal(original.loading, 'eager')
  assert.equal(original.fetchPriority, 'high')
  assert.equal(images.filter(i => i.props.priority).length, 1)
})
test('homepage proxy sources retain the asset path and contain one width parameter', async () => {
  const render = await renderer('../components/FallbackMediaImage.tsx')
  const image = render({ src: '/api/catalog/proxy-media/?path=marketing%2Fcards%2Ftest.jpg&max_width=600&w=600', alt: 'Card', sizes: '96px', responsiveProxy: true })
  assert.equal(image.props.sizes, '96px')
  const sources = image.props.srcSet.split(', ')
  assert.equal(sources.length, 5)
  for (const source of sources) {
    const [url, descriptor] = source.split(' ')
    const params = new URL(url, 'https://mudaroba.com').searchParams
    assert.equal(params.get('path'), 'marketing/cards/test.jpg')
    assert.equal(params.getAll('max_width').length, 1)
    assert.equal(params.has('w'), false)
    assert.equal(`${params.get('max_width')}w`, descriptor)
  }
})
test('existing proxy callers retain their original image request', async () => {
  const render = await renderer('../components/FallbackMediaImage.tsx')
  const src = '/api/catalog/proxy-media/?path=test.jpg'
  const image = render({ src, alt: 'Card' })
  assert.equal(image.props.src, src)
  assert.equal(image.props.srcSet, undefined)
})
