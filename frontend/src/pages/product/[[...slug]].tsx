import { GetServerSideProps } from 'next'
import Head from 'next/head'
import Link from 'next/link'
import axios from 'axios'
import api from '../../lib/api'
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useRouter } from 'next/router'
import AddToCartButton from '../../components/AddToCartButton'
import BuyNowButton from '../../components/BuyNowButton'
import SecurityAndService from '../../components/SecurityAndService'
import ServiceAttributes from '../../components/ServiceAttributes'
import FavoriteButton from '../../components/FavoriteButton'
import ShareButton from '../../components/ShareButton'
import SimilarProducts from '../../components/SimilarProducts'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { getLocalizedBrandName, getLocalizedCategoryName, getLocalizedColor, getLocalizedCoverType, getLocalizedProductDescription, getLocalizedProductName, ProductTranslation, BrandTranslation } from '../../lib/i18n'
import { resolveMediaUrl, isVideoUrl, getPlaceholderImageUrl, getVideoEmbedUrl, pickPreferredVideoUrl } from '../../lib/media'
import { getSiteOrigin } from '../../lib/urls'
import { isBaseProductType, favoriteApiProductId } from '../../lib/product'
import { useTheme } from '../../context/ThemeContext'

type CategoryType = string

const CATEGORY_ALIASES: Record<string, CategoryType> = {
  supplements: 'supplements',
  'medical-equipment': 'medical-equipment',
  medical_equipment: 'medical-equipment',
  furniture: 'furniture',
  tableware: 'tableware',
  accessories: 'accessories',
  jewelry: 'jewelry',
  perfumery: 'perfumery',
  underwear: 'underwear',
  headwear: 'headwear',
  books: 'books',
  uslugi: 'uslugi',
}

const normalizeCategoryType = (value?: string): CategoryType => {
  if (!value) return 'medicines'
  const lower = value.toLowerCase().replace(/_/g, '-')
  // Если есть алиас - возвращаем его, иначе возвращаем как есть (для поддержки новых категорий)
  return CATEGORY_ALIASES[lower] || lower
}

const parsePriceWithCurrency = (value?: string | number | null) => {
  if (value === null || typeof value === 'undefined') {
    return { price: null as string | number | null, currency: null as string | null }
  }
  if (typeof value === 'number') {
    return { price: value, currency: null as string | null }
  }
  const trimmed = value.trim()
  const match = trimmed.match(/^([0-9]+(?:[.,][0-9]+)?)\s*([A-Za-z]{3,5})$/)
  if (match) {
    return { price: match[1].replace(',', '.'), currency: match[2].toUpperCase() }
  }
  return { price: trimmed, currency: null as string | null }
}

const parseNumber = (value: string | number | null | undefined) => {
  if (value === null || typeof value === 'undefined') return null
  const normalized = String(value).replace(',', '.').replace(/[^0-9.]/g, '')
  if (!normalized) return null
  const num = Number(normalized)
  return Number.isFinite(num) ? num : null
}

const formatPrice = (value: string | number | null | undefined): string | null => {
  if (value === null || typeof value === 'undefined') return null
  const num = parseNumber(value)
  if (num === null) return String(value)

  // Округляем до 2 знаков после запятой, затем убираем лишние нули и саму точку, если она не нужна
  let str = num.toFixed(2)
  if (str.includes('.')) {
    str = str.replace(/0+$/, '').replace(/\.$/, '')
  }
  return str
}

const normalizeMediaValue = (value?: string | null) => {
  if (!value) return null
  const trimmed = String(value).trim()
  if (!trimmed) return null
  const lower = trimmed.toLowerCase()
  if (lower === 'null' || lower === 'none' || lower === 'undefined') return null
  return trimmed
}

/** Нормализованный путь для сравнения картинок (без ведущих слешей), одинаково на SSR и в браузере. */
const normalizeImagePathKey = (raw: string): string => {
  const noHash = raw.split('#')[0] || ''
  const [pathPart, ...qsParts] = noHash.split('?')
  const path = pathPart.replace(/^\/+/, '').toLowerCase()
  const qs = qsParts.length ? `?${qsParts.join('?').toLowerCase()}` : ''
  return `${path}${qs}`
}

/**
 * Ключ дедупликации слайдов: не используем resolveMediaUrl — на проде SSR и клиент могут давать разные строки
 * для одного файла (разные базы API / относительный vs абсолютный CDN). Сравниваем путь и proxy path=.
 */
const galleryImageDedupeKey = (value?: string | null): string | null => {
  const n = normalizeMediaValue(value)
  if (!n) return null

  if (/proxy-media/i.test(n) && n.includes('path=')) {
    try {
      const m = n.match(/[?&]path=([^&]+)/)
      if (m?.[1]) {
        const decoded = decodeURIComponent(m[1].replace(/\+/g, '%20'))
        return normalizeImagePathKey(decoded)
      }
    } catch {
      /* ignore */
    }
  }

  if (/^https?:\/\//i.test(n) || n.startsWith('//')) {
    try {
      const urlStr = n.startsWith('//') ? `https:${n}` : n
      const u = new URL(urlStr)
      return normalizeImagePathKey(`${u.pathname}${u.search || ''}`)
    } catch {
      return n.toLowerCase()
    }
  }

  try {
    const tail = n.split('#')[0] || n
    const abs = tail.startsWith('/') ? `https://x.invalid${tail}` : `https://x.invalid/${tail}`
    const u = new URL(abs)
    return normalizeImagePathKey(`${u.pathname}${u.search || ''}`)
  } catch {
    return n.toLowerCase()
  }
}

type GalleryItemDedupe = {
  id: number | string
  image_url: string
  video_url?: string | null
  alt_text?: string
  is_main?: boolean
  sort_order?: number
  isVideo?: boolean
}

/** После сортировки убираем повторы одного файла (мебель: product.main_* дублирует кадры варианта). */
function dedupeGalleryItemsPreservingOrder(items: GalleryItemDedupe[]): GalleryItemDedupe[] {
  const seenImg = new Set<string>()
  const seenVid = new Set<string>()
  const out: GalleryItemDedupe[] = []
  for (const item of items) {
    if (item.isVideo && item.video_url) {
      const vk = normalizeMediaValue(item.video_url)
      if (!vk || seenVid.has(vk)) continue
      seenVid.add(vk)
      out.push(item)
      continue
    }
    const u = normalizeMediaValue(item.image_url)
    if (!u) continue
    const k = galleryImageDedupeKey(u)
    if (!k || seenImg.has(k)) continue
    seenImg.add(k)
    out.push(item)
  }
  return out
}

/** Краткая строка под названием мебели (тип, цвет, размер) — без HTML из админки */
const stripHtmlToPlainText = (html: string) => {
  if (!html) return ''
  return String(html)
    .replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Фрагмент описания для одного раскрывающегося блока */
type DescriptionSection = { title: string; html: string }

/**
 * Делит HTML описания по заголовкам h2–h4 (несколько блоков для вертикального аккордеона).
 * Без заголовков — один блок на всё содержимое.
 */
function splitDescriptionIntoSections(html: string): DescriptionSection[] {
  const trimmed = String(html || '').trim()
  if (!trimmed) return []

  const re = /<h([2-4])[^>]*>([\s\S]*?)<\/h\1>/gi
  const matches: { start: number; title: string }[] = []
  let m: RegExpExecArray | null
  while ((m = re.exec(trimmed)) !== null) {
    const title = stripHtmlToPlainText(m[2] || '').trim()
    matches.push({ start: m.index, title })
  }

  if (matches.length === 0) {
    return [{ title: '', html: trimmed }]
  }

  const sections: DescriptionSection[] = []
  if (matches[0].start > 0) {
    const pre = trimmed.slice(0, matches[0].start).trim()
    if (pre) sections.push({ title: '', html: pre })
  }
  for (let i = 0; i < matches.length; i++) {
    const start = matches[i].start
    const end = i + 1 < matches.length ? matches[i + 1].start : trimmed.length
    const chunk = trimmed.slice(start, end).trim()
    if (chunk) {
      sections.push({ title: matches[i].title, html: chunk })
    }
  }

  return sections.length > 0 ? sections : [{ title: '', html: trimmed }]
}

const getAdministrationRouteLabel = (value: string | null | undefined, t: any) => {
  if (!value) return null
  const routeLabels: Record<string, string> = {
    'Ağızdan': t('route_oral', 'Peroral'),
    'Damar İçine': t('route_intravenous', 'Intravenous'),
    'Kas İçine': t('route_intramuscular', 'Intramuscular'),
    'Cilt Üzerine': t('route_topical', 'Topical'),
    'Solunum Yoluyla': t('route_inhalation', 'Inhalation'),
    'Rektal Yoldan': t('route_rectal', 'Rectal'),
    'Göz İçine': t('route_ophthalmic', 'Ophthalmic'),
    'Kulak İçine': t('route_otic', 'Otic'),
  }
  return routeLabels[value] || value
}

const getDosageFormLabel = (value: string | null | undefined, t: any) => {
  if (!value) return null
  const forms: Record<string, string> = {
    tablet: t('dosage_tablet', 'Таблетки'),
    capsule: t('dosage_capsule', 'Капсулы'),
    syrup: t('dosage_syrup', 'Сироп'),
    injection: t('dosage_injection', 'Инъекция'),
    cream: t('dosage_cream', 'Крем'),
    ointment: t('dosage_ointment', 'Мазь'),
    gel: t('dosage_gel', 'Гель'),
    drops: t('dosage_drops', 'Капли'),
    spray: t('dosage_spray', 'Спрей'),
    powder: t('dosage_powder', 'Порошок'),
    suppository: t('dosage_suppository', 'Суппозитории'),
    other: t('dosage_other', 'Другое'),
  }
  return forms[value] || value
}

const getSgkStatusLabel = (value: string | null | undefined, t: any) => {
  if (!value) return null
  const statusLabels: Record<string, string> = {
    'Bedeli Ödenir': t('sgk_status_paid', 'Bedeli Ödenir'),
    'Bedeli Ödenmez': t('sgk_status_not_paid', 'Bedeli Ödenmez'),
    'Pasif': t('sgk_status_passive', 'Pasif'),
  }
  return statusLabels[value] || value
}

const getPrescriptionTypeLabel = (value: string | null | undefined, t: any) => {
  if (!value) return null
  const prescriptionLabels: Record<string, string> = {
    'Beyaz Reçete': t('prescription_white', 'Beyaz Reçete'),
    'Kırmızı Reçete': t('prescription_red', 'Kırmızı Reçete'),
    'Yeşil Reçete': t('prescription_green', 'Yeşil Reçete'),
    'Mor Reçete': t('prescription_purple', 'Mor Reçete'),
    'Turuncu Reçete': t('prescription_orange', 'Turuncu Reçete'),
    'Normal Reçete': t('prescription_normal', 'Normal Reçete'),
    'Reçetesiz': t('prescription_none', 'Reçetesiz'),
  }
  return prescriptionLabels[value] || value
}

const formatShelfLife = (value: string | null | undefined, t: any) => {
  if (!value) return null
  if (value.includes(' Ay')) return value.replace(' Ay', ' ' + t('months', 'мес.'))
  if (value.includes(' Yıl')) return value.replace(' Yıl', ' ' + t('years', 'лет'))
  return value
}

interface SizeItem {
  id: number
  size?: string
  size_display?: string
  size_value?: string | number | null
  is_available?: boolean
  stock_quantity?: number | null
}

interface Product {
  id: number
  base_product_id?: number | null
  name: string
  slug: string
  description: string
  product_type?: string
  price: number | string | null
  price_formatted?: string | null
  old_price?: string | number | null
  old_price_formatted?: string | null
  currency: string
  stock_quantity?: number | null
  main_image?: string
  main_image_url?: string
  video_url?: string
  images?: { id: number; image_url: string; video_url?: string | null; alt_text?: string; is_main?: boolean; sort_order?: number }[]
  sizes?: SizeItem[]
  variants?: Variant[]
  default_variant_slug?: string | null
  active_variant_slug?: string | null
  active_variant_price?: string | null
  active_variant_currency?: string | null
  active_variant_old_price_formatted?: string | null
  active_variant_stock_quantity?: number | null
  active_variant_main_image_url?: string | null
  translations?: ProductTranslation[]
  // SEO
  meta_title?: string | null
  meta_description?: string | null
  meta_keywords?: string | null
  og_title?: string | null
  og_description?: string | null
  og_image_url?: string | null
  // Common Attributes
  brand?: { id: number; name: string; slug?: string; translations?: BrandTranslation[] } | null
  category?: { id: number; name: string; slug: string; ancestors?: { id: number; name: string; slug: string }[] } | null
  is_new?: boolean
  is_featured?: boolean
  is_bestseller?: boolean
  rating?: number | string | null
  reviews_count?: number | null
  availability_status?: string | null
  is_available?: boolean
  min_order_quantity?: number | null
  pack_quantity?: number | null
  gtin?: string | null
  mpn?: string | null
  country_of_origin?: string | null
  // Books
  isbn?: string | null
  publisher?: string | null
  publication_date?: string | null
  pages?: number | null
  language?: string | null
  cover_type?: string | null
  book_authors?: { id: number; author: { full_name: string; full_name_en?: string } }[]
  book_genres?: { id: number; genre: { name: string; name_en?: string } }[]
  book_attributes?: { format?: string; thickness_mm?: string }
  // Medicines & Supplements
  dosage_form?: string | null
  active_ingredient?: string | null
  prescription_required?: boolean | null
  prescription_type?: string | null
  volume?: string | null
  origin_country?: string | null
  usage_instructions?: string | null
  side_effects?: string | null
  contraindications?: string | null
  storage_conditions?: string | null
  indications?: string | null
  administration_route?: string | null
  shelf_life?: string | null
  barcode?: string | null
  atc_code?: string | null
  nfc_code?: string | null
  sgk_equivalent_code?: string | null
  sgk_active_ingredient_code?: string | null
  sgk_public_no?: string | null
  sgk_status?: string | null
  special_notes?: string | null
  serving_size?: string | null
  // Physical Attributes
  weight_value?: number | string | null
  weight_unit?: string | null
  length?: number | string | null
  width?: number | string | null
  height?: number | string | null
  dimensions_unit?: string | null
  sku?: string | null
  /** Артикул поставщика / IKEA item no (не из slug) */
  external_id?: string | null
  product_code?: string | null
  release_form?: string | null
  dosage?: string | null
  package_count?: number | string | null
  // Clothing & Shoes
  color?: string | null
  size?: string | null
  material?: string | null
  season?: string | null
  // Services
  main_video_url?: string | null
  main_gif_url?: string | null
  gallery?: { id: number; image_url: string; video_url?: string | null; alt_text?: string; is_main?: boolean; sort_order?: number }[]
  service_attributes?: { id: number; key: string; key_display: string; value: string; sort_order: number }[]
  dynamic_attributes?: { id: number; key: string; key_display: string; value: string; sort_order: number }[]
  furniture_type?: string | null
  dimensions?: string | null
}

interface FooterSettings {
  phone: string
  email: string
  location: string
  telegram_url: string
  whatsapp_url: string
}

interface Variant {
  id: number
  slug: string
  name?: string
  color?: string
  sku?: string
  price?: number | string | null
  old_price?: number | string | null
  currency?: string
  is_available?: boolean
  stock_quantity?: number | null
  main_image?: string
  images?: { id: number; image_url: string; video_url?: string | null; alt_text?: string; is_main?: boolean; sort_order?: number }[]
  sizes?: SizeItem[]
  active_variant_currency?: string | null
  /** Размер варианта (IKEA variant1), напр. 120x70 cm */
  size_display?: string | null
  /** Подпись цвета (поле color или ikea_variant_info) */
  color_display?: string | null
}

const resolveAvailableStock = (
  product: Product,
  selectedVariant: Variant | null | undefined,
  selectedSize: string | undefined
): number | null => {
  const sizeCandidate = selectedSize
    ? (selectedVariant?.sizes || product.sizes || []).find((s) => {
      const sizeValue = `${s.size ?? s.size_display ?? (s.size_value !== undefined && s.size_value !== null ? String(s.size_value) : '')}`.trim()
      return sizeValue === selectedSize
    })
    : undefined

  const sizeStock = sizeCandidate?.stock_quantity
  if (sizeStock !== null && sizeStock !== undefined) {
    return sizeStock
  }

  const variantStock = selectedVariant?.stock_quantity
  if (variantStock !== null && variantStock !== undefined) {
    return variantStock
  }

  const productStock = product.stock_quantity
  if (productStock !== null && productStock !== undefined) {
    return productStock
  }

  return null
}

export default function ProductPage({
  product: initialProduct,
  productType,
  isBaseProduct,
  preferredCurrency
}: {
  product: Product | null
  productType: CategoryType
  isBaseProduct: boolean
  preferredCurrency: string
}) {
  const { t, i18n } = useTranslation('common')
  const router = useRouter()
  const { theme } = useTheme()
  const [product, setProduct] = useState<Product | null>(initialProduct)

  useEffect(() => {
    setProduct(initialProduct)
  }, [initialProduct])
  const variants = product?.variants || []
  const localizedProductName = product
    ? getLocalizedProductName(product.name, t, product.translations, router.locale)
    : ''
  const displayProductName = localizedProductName || product?.name || ''
  const localeKey = (router.locale || '').toLowerCase()
  const isEnglishLocale = localeKey.startsWith('en')

  const envSupportEmail = process.env.NEXT_PUBLIC_SUPPORT_EMAIL || ''
  const [footerSettings, setFooterSettings] = useState<FooterSettings>({
    phone: '+90 552 582 14 97',
    email: envSupportEmail,
    location: '',
    telegram_url: 'https://t.me/fulani_admin',
    whatsapp_url: 'https://wa.me/905525821497'
  })

  useEffect(() => {
    if (typeof window !== 'undefined') {
      api.get('/settings/footer-settings')
        .then(response => {
          if (response.data) {
            setFooterSettings({
              phone: response.data.phone || '+90 552 582 14 97',
              email: response.data.email || envSupportEmail,
              location: response.data.location || '',
              telegram_url: response.data.telegram_url || 'https://t.me/fulani_admin',
              whatsapp_url: response.data.whatsapp_url || 'https://wa.me/905525821497'
            })
          }
        })
        .catch(err => console.error('Error fetching footer settings:', err))
    }
  }, [])

  // Выбираем дефолтный вариант-цвет: активный, либо первый доступный
  const initialVariant =
    variants.find((v) => v.slug === product?.active_variant_slug) ||
    variants.find((v) => v.slug === product?.default_variant_slug) ||
    variants.find((v) => v.is_available) ||
    variants[0] ||
    null

  const [selectedVariantSlug, setSelectedVariantSlug] = useState<string | null>(initialVariant?.slug || null)
  const selectedVariant = variants.find((v) => v.slug === selectedVariantSlug) || initialVariant

  /** IKEA и др.: варианты есть, но color не заполнен — фолбэк на slug/sku для селектора */
  const furnitureVariantPickerBySlug =
    productType === 'furniture' &&
    variants.length > 1 &&
    variants.every((v) => !String(v.color || '').trim())

  const colorPickerValues: string[] = furnitureVariantPickerBySlug
    ? (variants.map((v) => v.slug).filter(Boolean) as string[])
    : Array.from(new Set((variants.map((v) => v.color).filter(Boolean) as string[])))

  const resolveVariantByPickerValue = (key: string) =>
    furnitureVariantPickerBySlug
      ? variants.find((v) => v.slug === key)
      : variants.find((v) => v.color === key)

  const pickerLabel = (key: string) => {
    if (furnitureVariantPickerBySlug) {
      const v = variants.find((x) => x.slug === key)
      const cd = String(v?.color_display || v?.color || '').trim()
      if (cd) return cd
      if (v?.sku) return String(v.sku)
      return v?.name || key
    }
    return getLocalizedColor(key, t)
  }

  // Ключ выбора в сетке «цветов»: реальный color или slug (мебель без color)
  const defaultPickerKey = furnitureVariantPickerBySlug
    ? (initialVariant?.slug || undefined)
    : (initialVariant?.color || undefined)

  // Цвет и размер исходя из выбранного варианта
  const [selectedColor, setSelectedColor] = useState<string | undefined>(defaultPickerKey)
  // По умолчанию размер не выбран — пользователь должен выбрать вручную
  const [selectedSize, setSelectedSize] = useState<string | undefined>(undefined)
  // Количество товара
  const [quantity, setQuantity] = useState(1)
  /** Раскрытие блоков описания по индексу (вертикальный аккордеон) */
  const [descriptionAccordionOpen, setDescriptionAccordionOpen] = useState<Record<number, boolean>>({})

  useEffect(() => {
    const next = furnitureVariantPickerBySlug ? initialVariant?.slug : initialVariant?.color
    if (next) setSelectedColor(next)
  }, [product?.slug, furnitureVariantPickerBySlug, initialVariant?.slug, initialVariant?.color])

  // Список размеров для выбранного цвета (берем из выбранного варианта-цвета)
  const sizesForColor = (selectedVariant?.sizes && selectedVariant.sizes.length > 0)
    ? selectedVariant.sizes
    : (product?.sizes || [])
  const normalizedSizes = sizesForColor
    .map((s, index) => {
      const sizeValue = `${s.size ?? s.size_display ?? (s.size_value !== undefined && s.size_value !== null ? String(s.size_value) : '')}`.trim()
      const sizeLabel = `${s.size_display ?? s.size ?? (s.size_value !== undefined && s.size_value !== null ? String(s.size_value) : '')}`.trim()
      return { ...s, sizeValue, sizeLabel, sizeKey: sizeValue || String(index) }
    })
    .filter((s) => Boolean(s.sizeLabel))

  const furnitureSizeDisplay =
    productType === 'furniture' && selectedVariant?.size_display
      ? String(selectedVariant.size_display).trim()
      : null

  /** Подзаголовок в стиле IKEA: тип, цвет/артикул, размер */
  const furnitureDescriptorLine = useMemo(() => {
    if (productType !== 'furniture' || !product) return null
    const parts: string[] = []
    const ft = stripHtmlToPlainText(String(product.furniture_type || ''))
    if (ft) parts.push(ft)
    const col = String(selectedVariant?.color_display || selectedVariant?.color || '').trim()
    if (col) parts.push(col)
    else if (furnitureVariantPickerBySlug && selectedVariant?.sku)
      parts.push(String(selectedVariant.sku))
    const sz = String(selectedVariant?.size_display || '').trim()
    if (sz) parts.push(sz)
    if (parts.length === 0) return null
    return parts.join(', ').toLowerCase()
  }, [
    productType,
    product,
    product?.furniture_type,
    furnitureVariantPickerBySlug,
    selectedVariant?.color_display,
    selectedVariant?.color,
    selectedVariant?.sku,
    selectedVariant?.size_display,
  ])

  /** Артикул у цены: SKU варианта (IKEA) или external_id товара — не зависит от slug после ИИ */
  const furnitureArticleDisplay = useMemo(() => {
    if (productType !== 'furniture' || !product) return null
    const vSku = String(selectedVariant?.sku || '').trim()
    if (vSku) return vSku
    const ext = String(product.external_id || '').trim()
    if (ext) return ext
    return String(product.sku || product.product_code || '').trim() || null
  }, [
    productType,
    product,
    product?.external_id,
    product?.sku,
    product?.product_code,
    selectedVariant?.sku,
  ])

  const showFurnitureVariantsNearPrice =
    productType === 'furniture' &&
    (colorPickerValues.length > 0 ||
      Boolean(furnitureSizeDisplay) ||
      Boolean(furnitureArticleDisplay))

  const localizedDescriptionHtml = useMemo(() => {
    if (!product) return ''
    return getLocalizedProductDescription(
      product.description,
      t,
      product.translations,
      router.locale
    )
  }, [product, t, router.locale])

  const descriptionSections = useMemo(
    () => splitDescriptionIntoSections(localizedDescriptionHtml),
    [localizedDescriptionHtml]
  )

  useEffect(() => {
    setDescriptionAccordionOpen({})
  }, [product?.slug])

  const maxAvailable = product ? resolveAvailableStock(product, selectedVariant, selectedSize) : null
  const sizeHintMessage = t(
    'select_size_hint',
    i18n.language?.startsWith('ru')
      ? 'Выберите размер'
      : 'Select a size'
  )
  const productSlug = product?.slug

  const breadcrumbs = useMemo(() => {
    const list = [
      { label: t('breadcrumb_home', 'Главная'), href: '/' },
      { label: t('breadcrumb_categories', 'Категории'), href: '/categories' }
    ]

    // Если есть категория, добавляем её и всех её предков
    if (product?.category) {
      // Сначала предки (от корня вниз)
      if (product.category.ancestors && product.category.ancestors.length > 0) {
        product.category.ancestors.forEach(ancestor => {
          const ancestorName = getLocalizedCategoryName(
            ancestor.slug,
            ancestor.name,
            t,
            undefined,
            router.locale
          )
          list.push({
            label: ancestorName,
            href: `/categories/${ancestor.slug}`
          })
        })
      }

      // Сама категория товара
      const categoryName = getLocalizedCategoryName(
        product.category.slug,
        product.category.name,
        t,
        undefined,
        router.locale
      )
      list.push({
        label: categoryName,
        href: `/categories/${product.category.slug}`
      })
    } else if (productType && productType !== 'medicines') {
      // Фолбэк на тип продукта, если категория не задана явно
      const categoryName = getLocalizedCategoryName(
        productType,
        productType,
        t,
        undefined,
        router.locale
      )
      list.push({
        label: categoryName,
        href: `/categories/${productType}`
      })
    }

    list.push({
      label: displayProductName,
      href: '#'
    })
    return list
  }, [product, displayProductName, productType, t, router.locale])

  useEffect(() => {
    if (maxAvailable === 0) {
      setQuantity(1)
      return
    }
    if (maxAvailable !== null && quantity > maxAvailable) {
      setQuantity(Math.max(1, maxAvailable))
    }
  }, [maxAvailable, quantity])

  useEffect(() => {
    if (!productSlug || !selectedVariantSlug || isBaseProduct) return
    let cancelled = false
    const loadVariantDetails = async () => {
      try {
        const res = await api.get(`catalog/products/resolve/${encodeURIComponent(productSlug)}`, {
          params: { active_variant_slug: selectedVariantSlug },
        })
        const payload = res?.data?.payload
        if (!cancelled && payload) {
          setProduct(payload)
        }
      } catch { }
    }
    loadVariantDetails()
    return () => {
      cancelled = true
    }
  }, [selectedVariantSlug, productType, productSlug, isBaseProduct])

  // Подбор варианта при смене цвета (или slug для мебели IKEA без поля color)
  const pickVariant = (key?: string) => {
    if (!key) return
    const found =
      (furnitureVariantPickerBySlug
        ? variants.find((v) => v.slug === key)
        : variants.find((v) => v.color === key)) || variants[0]
    if (found) {
      setSelectedVariantSlug(found.slug)
      setSelectedColor(furnitureVariantPickerBySlug ? found.slug : (found.color || key))
      // Сброс выбора размера — пользователь должен выбрать вручную
      setSelectedSize(undefined)
      const gallerySourceLocal = found.images?.length ? found.images : product.images || []
      setActiveImage(
        resolveMediaUrl(
          found.main_image ||
          found.images?.find((img) => img.is_main)?.image_url ||
          found.images?.[0]?.image_url ||
          product.active_variant_main_image_url ||
          product.main_image_url ||
          product.main_image ||
          gallerySourceLocal.find((img) => img.is_main)?.image_url ||
          gallerySourceLocal[0]?.image_url ||
          null
        ) || null
      )
    }
  }

  // Элемент галереи: обычное фото или плейсхолдер «Видео»
  type GalleryItem = { id: number | string; image_url: string; video_url?: string | null; alt_text?: string; is_main?: boolean; sort_order?: number; isVideo?: boolean }
    const buildGallerySource = useCallback((): GalleryItem[] => {
      if (!product) return []
      const variantImages = selectedVariant?.images || []
      const productImages = (product.images && product.images.length > 0) ? product.images : (product.gallery || [])
      
      const mergedImages = productType === 'jewelry'
        ? [...variantImages, ...productImages]
        : (variantImages.length > 0 ? variantImages : productImages)

      /**
       * Мебель: корневое main_* дублирует первый кадр галереи. На проде галерея иногда только в product.images
       * (merged API), а variant.images пустой — расширяем условие до «есть любые кадры из merged».
       */
      const furnitureSkipSyntheticMain =
        productType === 'furniture' && mergedImages.length > 0
  
      const mainImageRaw = normalizeMediaValue(selectedVariant?.main_image || product.main_image_url || product.main_image)
  
      const normalizedProductVideoUrl = normalizeMediaValue(product.main_video_url || product.video_url)
      const normalizedProductGifUrl = normalizeMediaValue(product.main_gif_url)
  
      const seenVideoUrls = new Set<string>()
      const seenImageUrls = new Set<string>()
  
      const baseImages: GalleryItem[] = mergedImages.flatMap((img) => {
        const imageUrl = normalizeMediaValue(img.image_url)
        const imageDedupeKey = galleryImageDedupeKey(img.image_url)
        const possibleVideoUrl = (img as any).video_url || (imageUrl && isVideoUrl(imageUrl) ? imageUrl : null)
        const videoUrl = normalizeMediaValue(possibleVideoUrl)
  
        // Если это видео
        if (videoUrl && isVideoUrl(videoUrl)) {
          if (seenVideoUrls.has(videoUrl)) return []
          seenVideoUrls.add(videoUrl)
          return [{
            id: img.id,
            image_url: imageUrl && !isVideoUrl(imageUrl) ? imageUrl : '',
            video_url: videoUrl,
            alt_text: img.alt_text || 'Video',
            isVideo: true,
            is_main: img.is_main,
            sort_order: (img as any).sort_order || 0,
          } as GalleryItem]
        }
  
        if (!imageUrl || !imageDedupeKey || seenImageUrls.has(imageDedupeKey)) return []
        seenImageUrls.add(imageDedupeKey)
        
        return [{
          id: img.id,
          image_url: imageUrl,
          alt_text: img.alt_text,
          is_main: img.is_main,
          sort_order: (img as any).sort_order || 0,
        } as GalleryItem]
      })
  
      let list: GalleryItem[] = [...baseImages]
      
      // Добавляем мейн-поля, если они еще не в списке
      if (normalizedProductVideoUrl && !seenVideoUrls.has(normalizedProductVideoUrl)) {
        list.push({ id: 'main-v', image_url: '', video_url: normalizedProductVideoUrl, alt_text: 'Видео', isVideo: true, is_main: !list.some(i => i.is_main), sort_order: -50 })
      }
      const gifDedupeKey = galleryImageDedupeKey(normalizedProductGifUrl)
      if (normalizedProductGifUrl && gifDedupeKey && !seenImageUrls.has(gifDedupeKey)) {
        seenImageUrls.add(gifDedupeKey)
        list.push({ id: 'main-g', image_url: normalizedProductGifUrl, alt_text: 'GIF', is_main: !list.some(i => i.is_main), sort_order: -40 })
      }
      const mainDedupeKey = galleryImageDedupeKey(mainImageRaw)
      if (
        mainImageRaw &&
        mainDedupeKey &&
        !seenImageUrls.has(mainDedupeKey) &&
        !furnitureSkipSyntheticMain
      ) {
        seenImageUrls.add(mainDedupeKey)
        list.push({ id: 'main-i', image_url: mainImageRaw, alt_text: product.name, is_main: !list.some(i => i.is_main), sort_order: -30 })
      }
  
      const sortPriority = (item: GalleryItem) => {
        // Услуги: видео-анкор (is_main) -> 0, любое видео -> 1, главная картинка -> 2, остальное -> 3
        if (item.is_main && item.isVideo) return 0
        if (item.is_main) return 1
        if (item.isVideo) return 2
        return 3
      }
  
      const sorted = [...list].sort((a, b) => {
        const prioA = sortPriority(a)
        const prioB = sortPriority(b)
        if (prioA !== prioB) return prioA - prioB
        
        const orderA = a.sort_order ?? 999
        const orderB = b.sort_order ?? 999
        if (orderA !== orderB) return orderA - orderB
        
        return String(a.id).localeCompare(String(b.id), 'ru')
      })

      const sortedDeduped = dedupeGalleryItemsPreservingOrder(sorted)

      const hasProxyVideo = sortedDeduped.some((i) => i.isVideo && i.video_url && /proxy-media/i.test(i.video_url))
      if (hasProxyVideo) {
        return dedupeGalleryItemsPreservingOrder(
          sortedDeduped.filter((i) => {
            if (!i.isVideo || !i.video_url) return true
            if (/proxy-media/i.test(i.video_url)) return true
            if (/^https?:\/\//i.test(i.video_url)) return false
            return true
          })
        )
      }
      return sortedDeduped
    }, [product, productType, selectedVariant])

  const gallerySource = useMemo(() => buildGallerySource(), [buildGallerySource])
  const galleryMainImageUrl = normalizeMediaValue(
    gallerySource.find((img) => !img.isVideo && img.is_main)?.image_url ||
    gallerySource.find((img) => !img.isVideo && img.image_url)?.image_url
  )
  const initialImage =
    resolveMediaUrl(
      galleryMainImageUrl ||
      normalizeMediaValue(selectedVariant?.main_image) ||
      normalizeMediaValue(selectedVariant?.images?.find((img) => img.is_main)?.image_url) ||
      normalizeMediaValue(selectedVariant?.images?.[0]?.image_url) ||
      normalizeMediaValue(product?.active_variant_main_image_url || null) ||
      normalizeMediaValue(product?.main_image_url || null) ||
      normalizeMediaValue(product?.main_image || null) ||
      normalizeMediaValue(gallerySource.find((img) => !img.isVideo && img.image_url)?.image_url)
    ) || ''
  const hasImageSource = Boolean(
    normalizeMediaValue(selectedVariant?.main_image) ||
    selectedVariant?.images?.some((img) => normalizeMediaValue(img.image_url)) ||
    normalizeMediaValue(product?.main_image_url || null) ||
    normalizeMediaValue(product?.main_image || null) ||
    product?.images?.some((img) => normalizeMediaValue(img.image_url)) ||
    gallerySource.some((img) => !img.isVideo && normalizeMediaValue(img.image_url))
  )
  const [activeImage, setActiveImage] = useState<string | null>(initialImage || null)
  const [mainImageLoading, setMainImageLoading] = useState(false)
  /** Для миниатюр с битой ссылкой: по id храним URL плейсхолдера, чтобы по клику показывать его в главной области */
  const [thumbPlaceholderByKey, setThumbPlaceholderByKey] = useState<Record<string, string>>({})
  const initialVideoUrl = product
    ? pickPreferredVideoUrl([
      product.main_video_url,
      product.video_url,
      ...gallerySource.filter((item) => item.isVideo && item.video_url).map((item) => item.video_url),
    ])
    : null
  const [activeVideoUrl, setActiveVideoUrl] = useState<string | null>(initialVideoUrl)
  const [activeMediaType, setActiveMediaType] = useState<'video' | 'image'>(
    initialVideoUrl ? 'video' : 'image'
  )

  // ПРИНУДИТЕЛЬНО ПЕРЕКЛЮЧАЕМ НА ВИДЕО, ЕСЛИ ОНО ПЕРВОЕ В ГАЛЕРЕЕ (URL — с приоритетом proxy-media)
  useEffect(() => {
    if (gallerySource.length > 0) {
      const first = gallerySource[0]
      if (first.isVideo && first.video_url) {
        setActiveMediaType('video')
        setActiveVideoUrl(
          pickPreferredVideoUrl([
            product?.main_video_url,
            product?.video_url,
            first.video_url,
          ]) || first.video_url
        )
      } else if (first.image_url) {
        setActiveMediaType('image')
        setActiveImage(resolveMediaUrl(first.image_url))
      }
    }
  }, [gallerySource, product?.main_video_url, product?.video_url])

  // Обновляем главную картинку при изменении товара или варианта
  useEffect(() => {
    if (!product) return
    const currentGallerySource = buildGallerySource()
    const imageFromGallery =
      normalizeMediaValue(currentGallerySource.find((img) => !img.isVideo && img.is_main)?.image_url) ||
      normalizeMediaValue(currentGallerySource.find((img) => !img.isVideo && img.image_url)?.image_url)
    const newImage =
      resolveMediaUrl(
        imageFromGallery ||
        normalizeMediaValue(selectedVariant?.main_image) ||
        normalizeMediaValue(selectedVariant?.images?.find((img) => img.is_main)?.image_url) ||
        normalizeMediaValue(selectedVariant?.images?.[0]?.image_url) ||
        normalizeMediaValue(product.main_image_url || null) ||
        normalizeMediaValue(product.main_image || null) ||
        normalizeMediaValue(currentGallerySource.find((img) => !img.isVideo && img.image_url)?.image_url) ||
        null
      ) || null
    setActiveImage(newImage)
    setMainImageLoading(false)

    const freshVideoUrl = pickPreferredVideoUrl([
      product.main_video_url,
      product.video_url,
      ...currentGallerySource.filter((item) => item.isVideo && item.video_url).map((item) => item.video_url),
    ])

    setActiveVideoUrl(freshVideoUrl)
    
    const hasImages = currentGallerySource.some((img) => !img.isVideo && normalizeMediaValue(img.image_url))
    
    // Если первым элементом в галерее идет видео — не затираем freshVideoUrl внешним .mov
    if (currentGallerySource[0]?.isVideo && currentGallerySource[0]?.video_url) {
      setActiveMediaType('video')
      setActiveVideoUrl(
        pickPreferredVideoUrl([freshVideoUrl, currentGallerySource[0].video_url]) || currentGallerySource[0].video_url
      )
    } else if (hasImages) {
      setActiveMediaType(freshVideoUrl ? 'video' : 'image')
    }
  }, [buildGallerySource, product, selectedVariant, router.asPath])

  if (!product) {
    return <div className="mx-auto max-w-6xl p-6">{t('not_found', 'Товар не найден')}</div>
  }

  // Получаем числовое значение цены для расчетов
  const parsedActiveVariantPrice = parsePriceWithCurrency(product.active_variant_price ?? null)

  // Для доменных товаров (лекарства и т.д.) без вариантов используем price_formatted
  // который бэкенд уже сконвертировал в нужную валюту
  const parsedPriceFormatted = parsePriceWithCurrency(
    (!selectedVariant?.price && !product.active_variant_price && product.price_formatted)
      ? String(product.price_formatted)
      : null
  )

  const priceValue = selectedVariant?.price
    ? parseFloat(String(selectedVariant.price))
    : (product.active_variant_price
      ? parseFloat(String(product.active_variant_price))
      : (parsedPriceFormatted.price
        ? parseFloat(String(parsedPriceFormatted.price))
        : (product.price ? parseFloat(String(product.price)) : null)))

  const currency =
    (selectedVariant?.price != null ? selectedVariant?.currency : null) ||
    product.active_variant_currency ||
    parsedActiveVariantPrice.currency ||
    parsedPriceFormatted.currency ||
    preferredCurrency ||
    product.currency ||
    'USD'

  // Старая цена: как и price — сначала выбранный вариант; active_variant_* с API — только дефолтный slug.
  const oldPriceSource =
    variants.length > 0 && selectedVariant
      ? (selectedVariant.old_price != null && selectedVariant.old_price !== ''
        ? selectedVariant.old_price
        : null)
      : (product.active_variant_old_price_formatted ||
        product.old_price_formatted ||
        product.old_price)
  const { price: parsedOldPrice, currency: parsedOldCurrency } = parsePriceWithCurrency(
    oldPriceSource !== null && typeof oldPriceSource !== 'undefined' ? String(oldPriceSource) : null
  )
  const displayOldPrice = parsedOldCurrency && parsedOldCurrency !== currency ? null : (parsedOldPrice ?? oldPriceSource)
  const displayOldCurrency = parsedOldCurrency || currency
  const displayOldPriceLabel = displayOldPrice ? formatPrice(displayOldPrice) : null
  const displayOldCurrencyLabel = displayOldCurrency ? String(displayOldCurrency) : null
  const oldPriceValue = parseNumber(displayOldPrice)
  const discountPercent = priceValue !== null && oldPriceValue !== null && oldPriceValue > priceValue && oldPriceValue > 0
    ? Math.round(((oldPriceValue - priceValue) / oldPriceValue) * 100)
    : null

  // Вычисляем общую сумму с учетом количества
  const totalPrice = priceValue !== null ? formatPrice(priceValue * quantity) : null
  const displayPrice = priceValue !== null
    ? `${formatPrice(priceValue)} ${currency}`
    : t('price_on_request')
  const displayTotalPrice = totalPrice !== null
    ? `${totalPrice} ${currency}`
    : t('price_on_request')

  const sizeRequired = normalizedSizes.length > 0
  const hasProductVariants = variants.length > 0
  /** Избранное и корзина по варианту: небазовые типы или мебель/база с несколькими вариантами */
  const favoriteUsesVariantSlug = !isBaseProduct || (isBaseProduct && hasProductVariants)
  const favoriteProductSlugForApi = favoriteUsesVariantSlug
    ? isBaseProduct
      ? (selectedVariant?.slug || product.slug)
      : (selectedVariantSlug || product.slug)
    : undefined
  const favoriteSizeForApi = !isBaseProduct ? (selectedSize || '') : ''
  const cartUsesProductIdOnly = isBaseProduct && !hasProductVariants
  const cartProductSlug =
    isBaseProduct && hasProductVariants
      ? (selectedVariant?.slug || product.slug)
      : !isBaseProduct
        ? (selectedVariantSlug || product.slug)
        : product.slug
  const siteUrl = getSiteOrigin()
  const productPath = isBaseProduct ? `/product/${product.slug}` : `/product/${productType}/${product.slug}`
  const localePrefix = router.locale === router.defaultLocale ? '' : `/${router.locale}`
  const canonicalUrl = `${siteUrl}${localePrefix}${productPath}`
  // Извлекаем переводы для текущего языка (или используем fallback)
  const apiTranslation = product.translations?.find(
    (tr) => tr.locale === router.locale || tr.locale === router.locale?.split('-')[0]
  )
  const localizedDescription = apiTranslation?.description || product.description

  const metaTitle = (
    apiTranslation?.meta_title || 
    apiTranslation?.og_title || 
    (product.translations && product.translations.length > 0 ? '' : product.meta_title) || 
    (product.translations && product.translations.length > 0 ? '' : product.og_title) || 
    ''
  ).trim() || `${displayProductName || product.name} — Mudaroba`

  const metaDescription = (
    apiTranslation?.meta_description ||
    apiTranslation?.og_description ||
    (product.translations && product.translations.length > 0 ? '' : product.meta_description) ||
    (product.translations && product.translations.length > 0 ? '' : product.og_description) ||
    ''
  ).trim() || localizedDescription?.slice(0, 200) || `${displayProductName || product.name} — ${t('buy_on_mudaroba', 'купить на Mudaroba')}`
  const ogImage = (product.og_image_url || '').trim() || activeImage || product.active_variant_main_image_url || product.main_image_url || product.main_image || '/product-placeholder.svg'
  const availability =
    selectedVariant?.is_available === false || selectedVariant?.stock_quantity === 0
      ? 'https://schema.org/OutOfStock'
      : 'https://schema.org/InStock'
  const priceForSchema = selectedVariant?.price || product.price || product.active_variant_price
  const currencyForSchema = selectedVariant?.currency || product.active_variant_currency || product.currency
  const productSchema = {
    '@context': 'https://schema.org',
    '@type': productType === 'books' ? 'Book' : 'Product',
    name: displayProductName || product.name,
    description: metaDescription,
    image: ogImage,
    ...(productType === 'books' && product.isbn && { isbn: product.isbn }),
    ...(productType === 'books' && product.book_authors?.length
      ? { author: product.book_authors.map((a) => ({ '@type': 'Person', name: a.author?.full_name })) }
      : {}),
    ...(productType === 'books' && product.publisher && { publisher: { '@type': 'Organization', name: product.publisher } }),
    ...(productType === 'books' && product.pages != null && { numberOfPages: product.pages }),
    sku: product.slug,
    offers: priceForSchema
      ? {
        '@type': 'Offer',
        price: priceForSchema,
        priceCurrency: currencyForSchema || 'USD',
        availability,
        url: canonicalUrl,
      }
      : undefined,
  }
  const isService = productType === 'uslugi'
  return (
    <>
      <Head>
        <title>{metaTitle}</title>
        <meta name="description" content={metaDescription} />
        {product.meta_keywords && <meta name="keywords" content={product.meta_keywords} />}
        <link rel="canonical" href={canonicalUrl} />
        <link rel="alternate" hrefLang="ru" href={canonicalUrl} />
        <meta property="og:title" content={metaTitle} />
        <meta property="og:description" content={metaDescription} />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:type" content="product" />
        <meta property="og:image" content={ogImage} />
        <meta property="twitter:card" content="summary_large_image" />
        <meta property="twitter:title" content={metaTitle} />
        <meta property="twitter:description" content={metaDescription} />
        <script
          type="application/ld+json"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: JSON.stringify(productSchema) }}
        />
      </Head>
      <div className="mx-auto max-w-6xl px-3 pt-3 pb-0 sm:py-3 flex items-center justify-between overflow-x-auto no-scrollbar">
        <nav className="text-sm text-main flex flex-wrap items-center gap-2 whitespace-nowrap">
          {breadcrumbs.map((item, idx) => {
            const isLast = idx === breadcrumbs.length - 1
            return (
              <span key={`${item.href}-${idx}`} className="flex items-center gap-2">
                {!isLast ? (
                  <Link href={item.href} className="hover:text-[var(--accent)] transition-colors">
                    {item.label}
                  </Link>
                ) : (
                  <span className="text-main font-medium">{item.label}</span>
                )}
                {!isLast && <span className="text-main/60">/</span>}
              </span>
            )
          })}
        </nav>
      </div>
      <main className="mx-auto max-w-6xl px-3 pt-0 pb-8 sm:py-8">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-[1.3fr_1fr] md:items-start">
          <div className="flex flex-col md:flex-row gap-4 md:h-[calc(100vh-22rem)] md:sticky md:top-6 md:self-start">
            
            {/* --- МOБИЛЬНАЯ КАРУСЕЛЬ (Скрыта на десктопе) --- */}
            <div className="flex md:hidden overflow-x-auto snap-x snap-mandatory gap-4 pb-2 -mx-6 px-6 hide-scrollbar flex-shrink-0">
              {gallerySource.length > 0 ? gallerySource.map((img) => {
                const isVideoItem = (img as GalleryItem).isVideo === true
                const resolvedUrl = resolveMediaUrl(img.image_url)
                const thumbKey = `mobile-${String(img.id)}`
                return (
                  <div key={thumbKey} className="relative shrink-0 w-full aspect-[4/5] snap-center rounded-xl overflow-hidden bg-gray-50 border border-gray-100">
                    {isVideoItem && img.video_url ? (
                      (() => {
                        const embedUrl = getVideoEmbedUrl(img.video_url)
                        if (embedUrl) {
                          return (
                            <iframe
                              src={embedUrl}
                              className="w-full h-full border-0"
                              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                              allowFullScreen
                              title={img.alt_text || displayProductName}
                            />
                          )
                        }
                        const prodAny = product as any
                        const productFallbackImage = prodAny.main_image_url || prodAny.main_image || prodAny.image_url
                        const videoPoster =
                          (img.image_url && !isVideoUrl(img.image_url)
                            ? resolveMediaUrl(img.image_url)
                            : null) ||
                          (productFallbackImage ? resolveMediaUrl(productFallbackImage) : null) ||
                          undefined
                        return (
                          <video
                            src={resolveMediaUrl(img.video_url)}
                            poster={videoPoster}
                            controls
                            playsInline
                            muted
                            preload="metadata"
                            className="w-full h-full object-contain"
                          />
                        )
                      })()
                    ) : (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={resolvedUrl || getPlaceholderImageUrl({ type: 'product', id: product.id })}
                        alt={img.alt_text || displayProductName || product.name}
                        className="w-full h-full object-contain"
                        onError={(e) => { e.currentTarget.src = '/product-placeholder.svg' }}
                      />
                    )}
                    {/* Индикация фото (точки) как в kiton */}
                    <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1 z-10 opacity-70">
                      {gallerySource.map((_, i) => (
                        <div key={i} className={`w-1.5 h-1.5 rounded-full shadow-sm ${i === 0 ? 'bg-white scale-125' : 'bg-white/60'}`} />
                      ))}
                    </div>
                    
                    <div className="absolute top-3 right-3 z-20 flex flex-col gap-1.5" onClick={(e) => { e.preventDefault(); e.stopPropagation() }}>
                      <FavoriteButton
                        productId={favoriteUsesVariantSlug ? undefined : favoriteApiProductId(product, productType)}
                        productType={productType}
                        favoriteProductSlug={favoriteUsesVariantSlug ? favoriteProductSlugForApi : undefined}
                        favoriteSize={favoriteUsesVariantSlug ? favoriteSizeForApi : undefined}
                        cornerIcon={true}
                      />
                      <ShareButton title={metaTitle} description={metaDescription} imageUrl={ogImage} slug={product.slug} productType={productType} pageUrl={canonicalUrl} cornerIcon={true} />
                    </div>
                  </div>
                )
              }) : (
                <div className="relative shrink-0 w-full aspect-[4/5] snap-center rounded-xl overflow-hidden bg-gray-50 border border-gray-100">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={getPlaceholderImageUrl({ type: 'product', id: product.id, width: 800, height: 800 })}
                    alt="No image"
                    className="w-full h-full object-contain"
                    onError={(e) => { e.currentTarget.src = '/product-placeholder.svg' }}
                  />
                  <div className="absolute top-3 right-3 z-20 flex flex-col gap-1.5" onClick={(e) => { e.preventDefault(); e.stopPropagation() }}>
                    <FavoriteButton
                      productId={favoriteUsesVariantSlug ? undefined : favoriteApiProductId(product, productType)}
                      productType={productType}
                      favoriteProductSlug={favoriteUsesVariantSlug ? favoriteProductSlugForApi : undefined}
                      favoriteSize={favoriteUsesVariantSlug ? favoriteSizeForApi : undefined}
                      cornerIcon={true}
                    />
                    <ShareButton title={metaTitle} description={metaDescription} imageUrl={ogImage} slug={product.slug} productType={productType} pageUrl={canonicalUrl} cornerIcon={true} />
                  </div>
                </div>
              )}
            </div>

            {/* --- ДЕСКТОПНЫЕ МИНИАТЮРЫ СЛЕВА (Скрыты на мобильных) --- */}
            {gallerySource.length > 0 && (
              <div className="hidden md:flex flex-col gap-3 overflow-y-auto flex-shrink-0">
                {gallerySource.map((img) => {
                  const resolvedThumbnail = resolveMediaUrl(img.image_url)
                  const thumbKey = String(img.id)
                  const placeholderId = `${product.id}-thumb-${img.id}`
                  const placeholderSmall = getPlaceholderImageUrl({ type: 'product', id: placeholderId, width: 200, height: 200 })
                  const placeholderLarge = getPlaceholderImageUrl({ type: 'product', id: placeholderId, width: 800, height: 800 })
                  const effectiveThumbUrl = thumbPlaceholderByKey[thumbKey] || resolvedThumbnail || placeholderLarge
                  const isVideoItem = (img as GalleryItem).isVideo === true
                  const isActive =
                    isVideoItem
                      ? activeMediaType === 'video' && Boolean(img.video_url && img.video_url === activeVideoUrl)
                      : activeMediaType === 'image' && (activeImage === resolvedThumbnail || activeImage === effectiveThumbUrl)
                  return (
                    <button
                      key={thumbKey}
                      type="button"
                      className={`relative w-28 h-28 rounded-lg overflow-hidden border flex-shrink-0 cursor-pointer ${isActive ? 'border-violet-500 ring-2 ring-violet-300' : 'border-gray-200 hover:border-gray-300'}`}
                      onClick={() => {
                        if (isVideoItem) {
                          setActiveMediaType('video')
                          if (img.video_url) {
                            setActiveVideoUrl(img.video_url)
                          }
                        } else {
                          setActiveMediaType('image')
                          const nextUrl = effectiveThumbUrl || resolvedThumbnail || null
                          if (nextUrl !== activeImage) {
                            setMainImageLoading(true)
                            setActiveImage(nextUrl)
                          }
                        }
                      }}
                    >
                      {isVideoItem && img.video_url ? (
                        (() => {
                          const embedUrl = getVideoEmbedUrl(img.video_url)
                          if (embedUrl) {
                            return (
                              <div className="w-full h-full bg-black flex items-center justify-center">
                                <svg className="w-8 h-8 text-white/80" fill="currentColor" viewBox="0 0 24 24">
                                  <path d="M8 5v14l11-7z" />
                                </svg>
                              </div>
                            )
                          }
                          return (
                            <video
                              src={resolveMediaUrl(img.video_url)}
                              muted
                              playsInline
                              preload="metadata"
                              className="w-full h-full object-cover pointer-events-none"
                              aria-label={img.alt_text || displayProductName || product.name}
                            />
                          )
                        })()
                      ) : (
                        /* eslint-disable-next-line @next/next/no-img-element */
                        <img
                          src={resolvedThumbnail || placeholderSmall}
                          alt={img.alt_text || displayProductName || product.name}
                          className="w-full h-full object-cover pointer-events-none"
                          onError={(e) => {
                            setThumbPlaceholderByKey((prev) => ({ ...prev, [thumbKey]: placeholderLarge }))
                            e.currentTarget.src = placeholderSmall
                          }}
                        />
                      )}
                      {isVideoItem && (
                        <span className="absolute inset-0 flex items-center justify-center bg-black/30 rounded-lg" aria-hidden>
                          <svg className="w-10 h-10 text-white drop-shadow" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M8 5v14l11-7z" />
                          </svg>
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            )}
            {/* Главная область (Десктоп): видео или выбранное фото */}
            <div className="hidden md:flex flex-1 h-full items-start justify-start rounded-xl relative">
              {activeMediaType === 'video' && activeVideoUrl && isVideoUrl(activeVideoUrl) ? (
                (() => {
                  const embedUrl = getVideoEmbedUrl(activeVideoUrl)
                  if (embedUrl) {
                    return (
                      <iframe
                        src={embedUrl}
                        className="w-full aspect-video rounded-xl border-0"
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowFullScreen
                        title="Product Video"
                      />
                    )
                  }
                  return (
                    <video
                      key={activeVideoUrl || 'product-video'}
                      src={resolveMediaUrl(activeVideoUrl)}
                      controls
                      playsInline
                      muted
                      preload="metadata"
                      className="max-w-full max-h-full rounded-xl object-contain"
                    />
                  )
                })()
              ) : activeImage ? (
                <div className="relative w-full h-full min-h-[200px]">
                  {mainImageLoading && (
                    <div
                      className="absolute inset-0 flex items-center justify-center bg-gray-100 dark:bg-gray-800 rounded-xl animate-pulse"
                      aria-hidden
                    />
                  )}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={activeImage}
                    alt={displayProductName || product.name}
                    className={`max-w-full max-h-full rounded-xl object-contain transition-opacity duration-150 ${mainImageLoading ? 'opacity-0' : 'opacity-100'}`}
                    decoding="async"
                    onLoad={() => setMainImageLoading(false)}
                    onError={(e) => {
                      // Фолбек на picsum, завязанный на id товара
                      const { getPlaceholderImageUrl } = require('../../lib/media')
                      setMainImageLoading(false)
                      e.currentTarget.src = getPlaceholderImageUrl({
                        type: 'product',
                        id: product.id,
                        width: 800,
                        height: 800,
                      })
                    }}
                  />
                  {/* Иконки в углу главного изображения: избранное + шаринг */}
                  <div
                    className="absolute top-3 right-3 z-20 flex flex-col gap-1.5"
                    onClick={(e) => { e.preventDefault(); e.stopPropagation() }}
                  >
                    <FavoriteButton
                      productId={favoriteUsesVariantSlug ? undefined : favoriteApiProductId(product, productType)}
                      productType={productType}
                      favoriteProductSlug={favoriteUsesVariantSlug ? favoriteProductSlugForApi : undefined}
                      favoriteSize={favoriteUsesVariantSlug ? favoriteSizeForApi : undefined}
                      cornerIcon={true}
                    />
                    <ShareButton
                      title={metaTitle}
                      description={metaDescription}
                      imageUrl={ogImage}
                      slug={product.slug}
                      productType={productType}
                      pageUrl={canonicalUrl}
                      cornerIcon={true}
                    />
                  </div>
                </div>
              ) : (
                <div className="relative w-full h-full min-h-[200px]">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={require('../../lib/media').getPlaceholderImageUrl({
                      type: 'product',
                      id: product.id,
                      width: 800,
                      height: 800,
                    })}
                    alt="No image"
                    className="max-w-full max-h-full rounded-xl object-contain"
                    onError={(e) => {
                      e.currentTarget.src = '/product-placeholder.svg'
                    }}
                  />
                  {/* Иконки в углу плейсхолдера: избранное + шаринг */}
                  <div
                    className="absolute top-3 right-3 z-20 flex flex-col gap-1.5"
                    onClick={(e) => { e.preventDefault(); e.stopPropagation() }}
                  >
                    <FavoriteButton
                      productId={favoriteUsesVariantSlug ? undefined : favoriteApiProductId(product, productType)}
                      productType={productType}
                      favoriteProductSlug={favoriteUsesVariantSlug ? favoriteProductSlugForApi : undefined}
                      favoriteSize={favoriteUsesVariantSlug ? favoriteSizeForApi : undefined}
                      cornerIcon={true}
                    />
                    <ShareButton
                      title={metaTitle}
                      description={metaDescription}
                      imageUrl={ogImage}
                      slug={product.slug}
                      productType={productType}
                      pageUrl={canonicalUrl}
                      cornerIcon={true}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
          <div>
            <h1
              className="text-2xl font-bold"
              style={{ color: theme === 'dark' ? '#ffffff' : '#111827' }}
            >
              {displayProductName || product.name}
            </h1>
            {productType === 'furniture' && furnitureDescriptorLine && (
              <p
                className="mt-2 text-base leading-snug"
                style={{ color: theme === 'dark' ? '#9CA3AF' : '#4B5563' }}
              >
                {furnitureDescriptorLine}
              </p>
            )}
            {/* Основные характеристики (Бренд и Артикул) */}
            {productType !== 'uslugi' && product.product_type !== 'uslugi' && productType !== 'books' && (
              <div
                className="mt-3 space-y-1.5 text-sm"
                style={{ color: theme === 'dark' ? '#D1D5DB' : '#4B5563' }}
              >
                {/* Бренд */}
                {product.brand && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('brand', 'Бренд')}: </span>
                    {getLocalizedBrandName(product.brand.slug || '', product.brand.name, t, product.brand.translations, router.locale)}
                  </p>
                )}
                {/* Артикул / SKU */}
                {(product.sku || product.product_code) && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('product_code', 'Код')}: </span>
                    {product.sku || product.product_code}
                  </p>
                )}
              </div>
            )}

            {/* Блок «Книга»: автор, издательство, страницы, ISBN, язык, обложка, рейтинг */}
            {productType === 'books' && (
              <div
                className="mt-3 space-y-1.5 text-sm"
                style={{ color: theme === 'dark' ? '#D1D5DB' : '#4B5563' }}
              >
                {product.book_authors && product.book_authors.length > 0 && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('author', 'Автор')}: </span>
                    {product.book_authors.map((a) => {
                      if (!a.author) return null
                      return isEnglishLocale ? (a.author.full_name_en || a.author.full_name) : a.author.full_name
                    }).filter(Boolean).join(', ')}
                  </p>
                )}
                {(product.publisher || product.pages) && (
                  <p>
                    {product.publisher}
                    {product.publisher && product.pages && ' · '}
                    {product.pages != null && `${product.pages} ${t('pages', 'стр.')}`}
                  </p>
                )}
                {product.isbn && (
                  <p>ISBN: {product.isbn}</p>
                )}
                {(product.language || product.cover_type) && (
                  <p>
                    {[product.language, product.cover_type ? getLocalizedCoverType(product.cover_type, t) : null].filter(Boolean).join(' · ')}
                  </p>
                )}
                {(product.weight_value != null && product.weight_value !== '') && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('book_weight', 'Вес')}: </span>
                    {String(product.weight_value)} {product.weight_unit || 'kg'}
                  </p>
                )}
                {(product.book_attributes?.thickness_mm) && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('book_thickness_mm', 'Толщина, мм')}: </span>
                    {product.book_attributes.thickness_mm}
                  </p>
                )}
                {(product.book_attributes?.format) && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('book_format', 'Формат')}: </span>
                    {product.book_attributes.format}
                  </p>
                )}
                {product.publication_date && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('book_publication_year', 'Год издания')}: </span>
                    {String(product.publication_date).slice(0, 4)}
                  </p>
                )}
                {(product.rating != null && product.rating !== '' && Number(product.rating) > 0) && (
                  <p className="flex items-center gap-2">
                    <span className="inline-flex items-center gap-0.5 text-amber-600">
                      <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20"><path d="M10 15l-5.878 3.09 1.123-6.545L.489 6.91l6.572-.955L10 0l2.939 5.955 6.572.955-4.756 4.635 1.123 6.545z" /></svg>
                      {typeof product.rating === 'number' ? product.rating.toFixed(1) : String(product.rating)}
                    </span>
                    {product.reviews_count != null && product.reviews_count > 0 && (
                      <span style={{ color: theme === 'dark' ? '#9CA3AF' : '#6B7280' }}>
                        ({product.reviews_count} {t('reviews', 'отзывов')})
                      </span>
                    )}
                  </p>
                )}
              </div>
            )}
            {/* Блок «Медикамент»: полная карточка характеристик */}
            {(productType === 'medicines' || product.product_type === 'medicines') && (
              <div
                className="mt-3 space-y-1.5 text-sm"
                style={{ color: theme === 'dark' ? '#D1D5DB' : '#4B5563' }}
              >
                {/* Лекарственная форма */}
                {product.dosage_form && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('dosage_form', 'Лекарственная форма')}: </span>
                    {getDosageFormLabel(product.dosage_form, t)}
                  </p>
                )}
                {/* Действующее вещество */}
                {product.active_ingredient && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('active_ingredient', 'Действующее вещество')}: </span>
                    {product.active_ingredient}
                  </p>
                )}
                {/* Рецепт */}
                {product.prescription_required && (
                  <p className="flex items-center gap-1.5">
                    <svg className="h-4 w-4 text-orange-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span className="font-medium text-orange-600 dark:text-orange-400">{t('prescription_required', 'Отпускается по рецепту')}</span>
                  </p>
                )}
                {/* Объем/Количество */}
                {product.volume && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('volume', 'Объем/Количество')}: </span>
                    {product.volume}
                  </p>
                )}
                {/* Страна производства */}
                {product.origin_country && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('origin_country', 'Страна производства')}: </span>
                    {product.origin_country.toUpperCase() === 'İTHAL' || product.origin_country.toUpperCase() === 'ITHAL' 
                      ? t('imported', 'Импортное')
                      : product.origin_country.toUpperCase() === 'YERLİ' || product.origin_country.toUpperCase() === 'YERLI'
                        ? t('domestic', 'Турция (Местное)')
                        : product.origin_country}
                  </p>
                )}
                {/* Путь введения */}
                {product.administration_route && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('administration_route', 'Путь введения')}: </span>
                    {getAdministrationRouteLabel(product.administration_route, t)}
                  </p>
                )}
                {/* Срок годности */}
                {product.shelf_life && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('shelf_life', 'Срок годности')}: </span>
                    {formatShelfLife(product.shelf_life, t)}
                  </p>
                )}
                {/* СГК / страховка */}
                {product.sgk_status && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('sgk_status', 'СГК')}: </span>
                    {getSgkStatusLabel(product.sgk_status, t)}
                  </p>
                )}
                {/* Тип рецепта */}
                {product.prescription_type && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('prescription_type', 'Тип рецепта')}: </span>
                    {getPrescriptionTypeLabel(product.prescription_type, t)}
                  </p>
                )}
                {/* Штрих-код */}
                {product.barcode && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('barcode', 'Штрих-код')}: </span>
                    <span className="font-mono">{product.barcode}</span>
                  </p>
                )}
                {/* ATC-код */}
                {product.atc_code && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('atc_code', 'АТХ код')}: </span>
                    <span className="font-mono">{product.atc_code}</span>
                  </p>
                )}
                {/* NFC Код */}
                {product.nfc_code && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('nfc_code', 'NFC код')}: </span>
                    <span className="font-mono">{product.nfc_code}</span>
                  </p>
                )}
                {/* SGK Эквивалент */}
                {product.sgk_equivalent_code && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('sgk_equivalent_code', 'Код эквивалента SGK')}: </span>
                    <span className="font-mono">{product.sgk_equivalent_code}</span>
                  </p>
                )}
                {/* SGK Код акт. вещ-ва */}
                {product.sgk_active_ingredient_code && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('sgk_active_ingredient_code', 'Код акт. вещ-ва SGK')}: </span>
                    <span className="font-mono">{product.sgk_active_ingredient_code}</span>
                  </p>
                )}
                {/* SGK Публичный номер */}
                {product.sgk_public_no && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('sgk_public_no', 'Публичный номер SGK')}: </span>
                    <span className="font-mono">{product.sgk_public_no}</span>
                  </p>
                )}
              </div>
            )}
            {/* Блок «БАД»: карточка характеристик */}
            {(productType === 'supplements' || product.product_type === 'supplements') && (
              <div
                className="mt-3 space-y-1.5 text-sm"
                style={{ color: theme === 'dark' ? '#D1D5DB' : '#4B5563' }}
              >
                {/* Действующее вещество */}
                {product.active_ingredient && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('active_ingredient', 'Действующее вещество')}: </span>
                    {product.active_ingredient}
                  </p>
                )}
                {/* Размер порции */}
                {product.serving_size && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('serving_size', 'Размер порции')}: </span>
                    {product.serving_size}
                  </p>
                )}
              </div>
            )}


            {(product.is_bestseller || product.is_new || product.is_featured) && (

              <div className="flex flex-wrap gap-2 mt-2">
                {product.is_featured && (
                  <span className="rounded-md bg-pink-100 px-2 py-0.5 text-xs font-medium text-pink-700 dark:bg-pink-900/40 dark:text-pink-300">
                    {t('product_featured', 'Хит')}
                  </span>
                )}
                {product.is_bestseller && (
                  <span className="rounded-md bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700 dark:bg-orange-900/40 dark:text-orange-300">
                    {t('bestseller', 'Бестселлер')}
                  </span>
                )}
                {product.is_new && (
                  <span className="rounded-md bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/40 dark:text-green-300">
                    {t('new', 'Новинка')}
                  </span>
                )}
              </div>
            )}
            <div className="mt-3 text-xl font-semibold text-red-600">
              {displayPrice || t('price_on_request')}
            </div>
            {displayOldPriceLabel && (
              <div className="mt-1 flex items-baseline gap-2">
                <div className="text-sm text-gray-400 line-through">
                  {displayOldCurrencyLabel
                    ? `${displayOldPriceLabel} ${displayOldCurrencyLabel}`
                    : displayOldPriceLabel}
                </div>
                {discountPercent !== null && (
                  <div className="text-sm font-semibold !text-red-600">-{discountPercent}%</div>
                )}
              </div>
            )}
            {showFurnitureVariantsNearPrice && (
              <div
                className="mt-5 flex flex-col gap-5 border-t border-b py-4"
                style={{
                  borderColor: theme === 'dark' ? 'rgba(75,85,99,0.5)' : 'rgba(229,231,235,1)',
                }}
              >
                {furnitureArticleDisplay && (
                  <div className="flex flex-col gap-1">
                    <span
                      className="text-sm font-semibold"
                      style={{ color: theme === 'dark' ? '#e5e7eb' : '#111827' }}
                    >
                      {t('article_number', 'Артикул')}
                    </span>
                    <p
                      className="text-sm"
                      style={{ color: theme === 'dark' ? '#D1D5DB' : '#4B5563' }}
                    >
                      {furnitureArticleDisplay}
                    </p>
                  </div>
                )}
                {colorPickerValues.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <span
                      className="text-sm font-semibold"
                      style={{ color: theme === 'dark' ? '#e5e7eb' : '#111827' }}
                    >
                      {furnitureVariantPickerBySlug
                        ? t('product_variant', 'Вариант')
                        : t('color', 'Цвет')}
                    </span>
                    <div className="flex flex-wrap gap-4">
                      {colorPickerValues.map((c) => {
                        const isActive = c === selectedColor
                        const label = pickerLabel(c)
                        const variantForColor = resolveVariantByPickerValue(c) || null
                        const rawThumb =
                          normalizeMediaValue(variantForColor?.main_image) ||
                          normalizeMediaValue(variantForColor?.images?.find((img) => img.is_main)?.image_url) ||
                          normalizeMediaValue(variantForColor?.images?.[0]?.image_url) ||
                          normalizeMediaValue(product?.active_variant_main_image_url) ||
                          normalizeMediaValue(product?.main_image_url) ||
                          normalizeMediaValue(product?.main_image) ||
                          null
                        const placeholder = getPlaceholderImageUrl({
                          type: 'product',
                          seed: `${product?.slug || 'product'}-${c}`,
                          width: 200,
                          height: 200,
                        })
                        const thumbSrc = rawThumb ? resolveMediaUrl(rawThumb) : placeholder
                        const rawCd = String(
                          variantForColor?.color_display || variantForColor?.color || ''
                        ).trim()
                        const colorText = rawCd
                          ? getLocalizedColor(rawCd, t)
                          : label
                        return (
                          <div key={c} className="flex max-w-[5.5rem] flex-col items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedColor(c)
                                pickVariant(c)
                              }}
                              title={colorText}
                              aria-label={colorText}
                              aria-pressed={isActive}
                              className={`h-16 w-16 shrink-0 overflow-hidden rounded-md border bg-white transition ${isActive
                                ? 'border-violet-600 ring-2 ring-violet-200'
                                : 'border-gray-300 hover:border-violet-400'
                                }`}
                            >
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={thumbSrc}
                                alt=""
                                className="h-full w-full object-cover"
                                data-fallback={placeholder}
                                onError={(event) => {
                                  const target = event.currentTarget
                                  const fallback = target.dataset.fallback
                                  if (fallback && target.src !== fallback) {
                                    target.src = fallback
                                  }
                                }}
                              />
                            </button>
                            <span
                              className="w-full text-center text-xs leading-tight break-words"
                              style={{ color: theme === 'dark' ? '#D1D5DB' : '#374151' }}
                            >
                              {colorText}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
                {furnitureSizeDisplay && (
                  <div className="flex flex-col gap-1">
                    <span
                      className="text-sm font-semibold"
                      style={{ color: theme === 'dark' ? '#e5e7eb' : '#111827' }}
                    >
                      {t('size', 'Размер')}
                    </span>
                    <p
                      className="text-sm"
                      style={{ color: theme === 'dark' ? '#D1D5DB' : '#4B5563' }}
                    >
                      {furnitureSizeDisplay}
                    </p>
                  </div>
                )}
              </div>
            )}
            {(productType === 'medicines' || product.product_type === 'medicines') && (
              <div
                className="mt-2 text-xs leading-relaxed"
                style={{ color: theme === 'dark' ? '#9CA3AF' : '#6B7280' }}
              >
                <p>{t('medicine_disclaimer_line1', 'Наш сайт не продает лекарства.')}</p>
                <p>{t('medicine_disclaimer_line2', 'Указанные цены призваны способствовать рациональному использованию лекарственных средств.')}</p>
                <p>{t('medicine_disclaimer_line3', 'Цены на лекарства взяты из еженедельных списков, публикуемых Министерством здравоохранения Турции и Турецким агентством по лекарственным средствам и медицинским изделиям (TİTCK).')}</p>
                <p>{t('medicine_disclaimer_line4', 'Указанные цены являются рекомендованными розничными ценами для аптек и могут меняться.')}</p>
                <p>{t('medicine_disclaimer_line5', 'Цены могут быть неактуальными.')}</p>
              </div>
            )}
            {productType !== 'furniture' && (colorPickerValues.length > 0 || sizesForColor.length > 0) && (
              <div className="mt-4 flex flex-col gap-4">
                {colorPickerValues.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <span
                      className="text-sm font-semibold"
                      style={{ color: theme === 'dark' ? '#e5e7eb' : '#111827' }}
                    >
                      {furnitureVariantPickerBySlug
                        ? t('product_variant', 'Вариант')
                        : t('color', 'Цвет')}
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {colorPickerValues.map((c) => {
                        const isActive = c === selectedColor
                        const label = pickerLabel(c)
                        const variantForColor = resolveVariantByPickerValue(c) || null
                        const rawThumb =
                          normalizeMediaValue(variantForColor?.main_image) ||
                          normalizeMediaValue(variantForColor?.images?.find((img) => img.is_main)?.image_url) ||
                          normalizeMediaValue(variantForColor?.images?.[0]?.image_url) ||
                          normalizeMediaValue(product?.active_variant_main_image_url) ||
                          normalizeMediaValue(product?.main_image_url) ||
                          normalizeMediaValue(product?.main_image) ||
                          null
                        const placeholder = getPlaceholderImageUrl({
                          type: 'product',
                          seed: `${product?.slug || 'product'}-${c}`,
                          width: 200,
                          height: 200,
                        })
                        const thumbSrc = rawThumb ? resolveMediaUrl(rawThumb) : placeholder
                        return (
                          <button
                            key={c}
                            onClick={() => {
                              setSelectedColor(c)
                              pickVariant(c)
                            }}
                            type="button"
                            title={label}
                            aria-label={label}
                            className={`h-16 w-16 overflow-hidden rounded-md border bg-white transition ${isActive
                              ? 'border-violet-600 ring-2 ring-violet-200'
                              : 'border-gray-300 hover:border-violet-400'
                              }`}
                          >
                            <img
                              src={thumbSrc}
                              alt={label}
                              className="h-full w-full object-cover"
                              data-fallback={placeholder}
                              onError={(event) => {
                                const target = event.currentTarget
                                const fallback = target.dataset.fallback
                                if (fallback && target.src !== fallback) {
                                  target.src = fallback
                                }
                              }}
                            />
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
                {sizesForColor.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <span
                      className="text-sm font-semibold"
                      style={{ color: theme === 'dark' ? '#e5e7eb' : '#111827' }}
                    >
                      {t('size', 'Размер')}
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {normalizedSizes.map((s) => {
                        const isAvailable = s.is_available !== false && (s.stock_quantity === null || s.stock_quantity === undefined || s.stock_quantity > 0)
                        const isActive = s.sizeValue === selectedSize
                        return (
                          <button
                            key={s.sizeKey}
                            onClick={() => {
                              if (!isAvailable) return
                              setSelectedSize(s.sizeValue)
                            }}
                            className={`min-w-[56px] rounded-md px-3 py-2 text-sm border transition ${isAvailable
                              ? isActive
                                ? 'border-violet-600 bg-violet-50 text-violet-700'
                                : 'border-gray-300 bg-white text-gray-800 hover:border-violet-400'
                              : 'border-gray-200 bg-gray-100 text-gray-400 cursor-not-allowed'
                              }`}
                            disabled={!isAvailable}
                          >
                            {s.sizeLabel || t('size', 'Размер')}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Динамические атрибуты (Техстек, характеристики, серийник и т.д.) */}
            {(isService ? product.service_attributes : product.dynamic_attributes)?.length > 0 && (
              <div className="mt-8">
                <ServiceAttributes
                  attributes={(isService ? product.service_attributes : (product.dynamic_attributes || []))}
                  title={isService ? undefined : t('characteristics', 'Характеристики')}
                />
              </div>
            )}

            {/* Селектор количества */}
            {!isService && (
              <div className="mt-4 flex flex-col gap-2">
                <span
                  className="text-sm font-semibold"
                  style={{ color: theme === 'dark' ? '#e5e7eb' : '#111827' }}
                >
                  {t('quantity', 'Количество')}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setQuantity(Math.max(1, quantity - 1))}
                    disabled={quantity <= 1}
                    className="flex h-10 w-10 items-center justify-center rounded-md border border-gray-300 bg-white dark:bg-gray-800 dark:border-gray-600 text-gray-700 dark:text-gray-200 transition-colors hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    aria-label={t('decrease_quantity', 'Уменьшить количество')}
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
                    </svg>
                  </button>
                  <span
                    className="min-w-[3rem] text-center text-2xl font-extrabold"
                    style={{ color: theme === 'dark' ? '#ffffff' : '#111827' }}
                  >
                    {quantity}
                  </span>
                  <div className="relative group">
                    <button
                      onClick={() => {
                        if (sizeRequired && !selectedSize) {
                          return
                        }
                        if (maxAvailable !== null) {
                          setQuantity(Math.min(maxAvailable, quantity + 1))
                          return
                        }
                        setQuantity(quantity + 1)
                      }}
                      disabled={(sizeRequired && !selectedSize) || (maxAvailable !== null && quantity >= maxAvailable)}
                      className="flex h-10 w-10 items-center justify-center rounded-md border border-gray-300 bg-white dark:bg-gray-800 dark:border-gray-600 text-gray-700 dark:text-gray-200 transition-colors hover:bg-gray-50 dark:hover:bg-gray-700"
                      aria-label={t('increase_quantity', 'Увеличить количество')}
                    >
                      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                      </svg>
                    </button>
                    {sizeRequired && !selectedSize && (
                      <span className="pointer-events-none absolute -top-2 left-1/2 z-10 -translate-x-1/2 -translate-y-full rounded-md bg-gray-900 px-2 py-1 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100">
                        {sizeHintMessage}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Кнопки действий */}
            <div className="mt-4 flex flex-col gap-3">
              {isService ? (
                <>
                  {/* Для услуг — связь через мессенджеры, а не корзина */}
                  <div className="flex flex-col gap-3">
                    <a
                      href={`${footerSettings.whatsapp_url}?text=${encodeURIComponent(t('order_service_message', 'Здравствуйте! Хочу заказать услугу: ') + (displayProductName || product.name))}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center justify-center gap-2 rounded-lg bg-[#25D366] px-6 py-4 font-bold text-white transition-all hover:scale-[1.02] hover:bg-[#128C7E] active:scale-[0.98]"
                    >
                      <svg className="h-5 w-5 fill-current" viewBox="0 0 24 24">
                        <path d="M17.472 14.382c-.022-.014-.503-.245-.582-.273-.08-.029-.137-.043-.194.043-.057.087-.222.28-.272.336-.05.056-.098.064-.188.019-.089-.044-.378-.14-.72-.445-.265-.236-.445-.53-.496-.618-.05-.088-.005-.136.039-.181.039-.039.088-.103.132-.154.044-.052.059-.088.088-.147.03-.059.015-.11-.008-.155-.022-.046-.194-.467-.266-.64-.07-.168-.14-.146-.194-.148-.05-.002-.108-.002-.165-.002-.057 0-.15-.021-.229.063-.079.084-.301.294-.301.718 0 .423.308.832.351.89.043.059.605.924 1.467 1.297.205.088.365.14.49.18.207.065.395.056.544.034.166-.024.503-.205.574-.403.072-.198.072-.367.05-.403-.022-.036-.081-.057-.17-.101zm-5.469 4.383c-1.206 0-2.388-.325-3.424-.94l-.246-.146-2.544.668.68-2.48-.16-.254a7.926 7.926 0 0 1-1.213-4.252c0-4.387 3.57-7.958 7.958-7.958 2.126 0 4.125.827 5.628 2.33s2.33 3.502 2.33 5.628c0 4.389-3.572 7.96-7.958 7.96zm7.957-17.758C17.935 1.006 15.011 0 12.003 0 5.432 0 .08 5.352.08 11.924c0 2.099.549 4.148 1.595 5.96L0 24l6.324-1.658c1.745.952 3.716 1.455 5.672 1.455 6.568 0 11.921-5.352 11.921-11.924 0-3.184-1.24-6.179-3.49-8.428z" />
                      </svg>
                      {t('order_via_whatsapp', 'Заказать через WhatsApp')}
                    </a>
                    <a
                      href={`${footerSettings.telegram_url}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center justify-center gap-2 rounded-lg bg-[#0088cc] px-6 py-4 font-bold text-white transition-all hover:scale-[1.02] hover:bg-[#0077b5] active:scale-[0.98]"
                    >
                      <svg className="h-5 w-5 fill-current" viewBox="0 0 24 24">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1 .22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.19-.04-.27-.02-.12.02-1.93 1.25-5.45 3.63-.51.35-.98.53-1.39.52-.46-.01-1.33-.26-1.98-.48-.8-.27-1.43-.42-1.38-.89.03-.25.38-.51 1.07-.78 4.21-1.83 7.01-3.04 8.39-3.63 3.96-1.67 4.79-1.96 5.33-1.97.12 0 .38.03.55.17.14.12.18.28.2.4.02.1.03.29.02.4z" />
                      </svg>
                      {t('order_via_telegram', 'Заказать через Telegram')}
                    </a>
                  </div>
                </>
              ) : (
                (productType === 'medicines' || product.product_type === 'medicines') ? (
                  <>
                    <button
                      type="button"
                      disabled={true}
                      className="w-full inline-flex items-center justify-center rounded-md border border-gray-300 bg-gray-100 px-4 py-2 text-sm font-medium text-gray-500 cursor-not-allowed"
                    >
                      {t('medicine_consult_button', 'Узнать актуальную цену - получить консультацию')}
                    </button>
                    <Link
                      href="/how-to-order-medicines"
                      className="w-full inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-all duration-200"
                    >
                      {t('medicine_how_to_order_button', 'Как заказать из Турции')}
                    </Link>
                  </>
                ) : (
                  <>
                    <AddToCartButton
                      productId={cartUsesProductIdOnly ? (product.base_product_id ?? product.id) : undefined}
                      productType={productType}
                      productSlug={cartProductSlug}
                      size={selectedSize}
                      requireSize={!isBaseProduct && sizeRequired}
                      quantity={quantity}
                      showPrice={true}
                      price={displayTotalPrice}
                      className="w-full"
                      label={t('add_to_cart', 'В корзину')}
                    />
                    <BuyNowButton
                      productId={cartUsesProductIdOnly ? (product.base_product_id ?? product.id) : undefined}
                      productType={productType}
                      productSlug={cartProductSlug}
                      size={selectedSize}
                      requireSize={!isBaseProduct && sizeRequired}
                      quantity={quantity}
                      className="w-full"
                    />
                  </>
                )
              )}

            </div>

            {/* Безопасность и сервис */}
            {!isService && <SecurityAndService />}
          </div>
        </div>

        {/* Описание: блоки друг под другом, как у лекарств (раскрывающийся список) */}
        {descriptionSections.length > 0 && (
          <div className="mt-6 flex w-full flex-col gap-4">
            {descriptionSections.map((sec, idx) => {
              const rawBody = sec.html.trim()
              if (!rawBody) return null
              
              // Linkify
              const urlRegex = /((https?:\/\/[^\s<"']+)|(www\.[^\s<"']+))/gi;
              const body = rawBody.replace(urlRegex, (url) => {
                const href = /^https?:\/\//i.test(url) ? url : `https://${url}`;
                return `<a href="${href}" target="_self" class="text-red-500 hover:text-red-700 font-semibold underline underline-offset-2 transition-colors duration-200 break-all">${url}</a>`;
              });

              const sectionTitle = sec.title.trim()
                ? sec.title
                : idx === 0
                  ? t('description', 'Описание')
                  : `${t('description', 'Описание')} (${idx + 1})`
              const isExpanded = Boolean(descriptionAccordionOpen[idx])
              return (
                <div
                  key={idx}
                  className="w-full overflow-hidden rounded-lg border dark:border-gray-700"
                  style={{
                    borderColor: theme === 'dark' ? '#374151' : '#E5E7EB',
                    backgroundColor: theme === 'dark' ? '#1F2937' : '#FFF8E7',
                  }}
                >
                  <button
                    type="button"
                    onClick={() => {
                      setDescriptionAccordionOpen((prev) => ({
                        ...prev,
                        [idx]: !prev[idx],
                      }))
                    }}
                    className="flex w-full items-center justify-between p-4 text-left transition-colors"
                    style={{ backgroundColor: 'transparent' }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = theme === 'dark' ? '#374151' : '#FFF5DC'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = 'transparent'
                    }}
                    aria-expanded={isExpanded}
                  >
                    <span
                      className="font-medium"
                      style={{ color: theme === 'dark' ? '#ffffff' : '#111827' }}
                    >
                      {sectionTitle}
                    </span>
                    <svg
                      className={`h-5 w-5 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                      style={{ color: theme === 'dark' ? '#D1D5DB' : '#4B5563' }}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {isExpanded && (
                    <div
                      className="border-t p-6 dark:border-gray-700"
                      style={{
                        borderTopColor: theme === 'dark' ? '#374151' : '#E5E7EB',
                        backgroundColor: theme === 'dark' ? '#111827' : '#FFFBF0',
                      }}
                    >
                      <div className="prose max-w-none dark:prose-invert">
                        <div
                          className="whitespace-pre-wrap text-base leading-relaxed"
                          style={{ color: theme === 'dark' ? '#F3F4F6' : '#111827' }}
                          dangerouslySetInnerHTML={{ __html: body }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Дополнительные секции для лекарств */}
        {(productType === 'medicines' || product.product_type === 'medicines') && (
          <div className="mt-4 flex flex-col gap-4">
            {[
              { id: 'indications', title: t('indications', 'Показания к применению'), content: product.indications, fieldName: 'indications' },
              { id: 'usage', title: t('usage_instructions', 'Способ применения'), content: product.usage_instructions, fieldName: 'usage_instructions' },
              { id: 'side_effects', title: t('side_effects', 'Побочные действия'), content: product.side_effects, fieldName: 'side_effects' },
              { id: 'contraindications', title: t('contraindications', 'Противопоказания'), content: product.contraindications, fieldName: 'contraindications' },
              { id: 'storage', title: t('storage_conditions', 'Условия хранения'), content: product.storage_conditions, fieldName: 'storage_conditions' },
              { id: 'special_notes', title: t('special_notes', 'Особые сведения'), content: product.special_notes, fieldName: 'special_notes' },
            ].map((section: any) => {
              if (!section.content) return null
              const isExpanded = (product as any)[`_is_${section.id}_expanded`] ?? false
              return (
                <div
                  key={section.id}
                  className="rounded-lg border dark:border-gray-700 overflow-hidden w-full"
                  style={{
                    borderColor: theme === 'dark' ? '#374151' : '#E5E7EB',
                    backgroundColor: theme === 'dark' ? '#1F2937' : '#FFF8E7'
                  }}
                >
                  <button
                    onClick={() => {
                      setProduct(prev => {
                        if (!prev) return prev
                        return { ...prev, [`_is_${section.id}_expanded`]: !isExpanded } as any
                      })
                    }}
                    className="w-full flex items-center justify-between p-4 text-left transition-colors"
                    style={{
                      backgroundColor: 'transparent'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = theme === 'dark' ? '#374151' : '#FFF5DC'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = 'transparent'
                    }}
                  >
                    <span
                      className="font-medium"
                      style={{ color: theme === 'dark' ? '#ffffff' : '#111827' }}
                    >
                      {section.title}
                    </span>
                    <svg
                      className={`w-5 h-5 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                      style={{ color: theme === 'dark' ? '#D1D5DB' : '#4B5563' }}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {isExpanded && (
                    <div
                      className="border-t dark:border-gray-700 p-6"
                      style={{
                        borderTopColor: theme === 'dark' ? '#374151' : '#E5E7EB',
                        backgroundColor: theme === 'dark' ? '#111827' : '#FFFBF0'
                      }}
                    >
                      <div className="prose max-w-none dark:prose-invert">
                        <div
                          className="whitespace-pre-wrap leading-relaxed text-base"
                          style={{ color: theme === 'dark' ? '#F3F4F6' : '#111827' }}
                          dangerouslySetInnerHTML={{ 
                            __html: (() => {
                              const content = section.content;
                              if (!content) return '';
                              const urlRegex = /((https?:\/\/[^\s<"']+)|(www\.[^\s<"']+))/gi;
                              return content.replace(urlRegex, (url) => {
                                const href = /^https?:\/\//i.test(url) ? url : `https://${url}`;
                                return `<a href="${href}" target="_self" style="color: #EF4444; font-weight: 600; text-decoration: underline; word-break: break-all;">${url}</a>`;
                              });
                            })()
                          }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Похожие товары (RecSys когда доступен) */}
        {!isService && (
          <SimilarProducts
            productType={productType}
            currentProductId={product.id}
            currentBaseProductId={product.base_product_id}
            currentProductSlug={product.slug}
            limit={8}
            useRecsys={true}
          />
        )}
      </main >
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  const slugParts = (ctx.params?.slug as string[]) || []
  if (slugParts.length === 0) {
    return { notFound: true }
  }

  let categoryType: CategoryType = 'medicines'
  let productSlug: string

  if (slugParts.length === 1) {
    productSlug = slugParts[0]
  } else {
    categoryType = normalizeCategoryType(slugParts[0])
    productSlug = slugParts[1]
  }

  const { getInternalApiUrl, buildProductUrl } = await import('../../lib/urls')
  const cookieHeader: string = ctx.req.headers.cookie || ''
  const currencyMatch = cookieHeader.match(/(?:^|;\s*)currency=([^;]+)/)
  const currency = currencyMatch ? currencyMatch[1] : 'RUB'

  const localePrefix = ctx.locale ? `/${ctx.locale}` : ''

  const activeVariantFromQuery =
    typeof ctx.query.active_variant_slug === 'string'
      ? ctx.query.active_variant_slug
      : Array.isArray(ctx.query.active_variant_slug)
        ? ctx.query.active_variant_slug[0]
        : undefined

  const resolvePath = `catalog/products/resolve/${encodeURIComponent(productSlug)}`

  try {
    const res = await axios.get(getInternalApiUrl(resolvePath), {
      headers: {
        'X-Currency': currency,
        'Accept-Language': ctx.locale || 'en',
      },
      params: activeVariantFromQuery ? { active_variant_slug: activeVariantFromQuery } : undefined,
    })

    const body = res.data
    const payload = body?.payload
    if (!payload || typeof payload !== 'object') {
      return { notFound: true }
    }

    const actualType = normalizeCategoryType(body.product_type || payload.product_type)
    const canonicalPath = String(body.canonical_path || '').trim()
    const currentProductPath = `/product/${slugParts.join('/')}`

    if (canonicalPath && currentProductPath !== canonicalPath) {
      return {
        redirect: {
          destination: `${localePrefix}${canonicalPath}`,
          permanent: false,
        },
      }
    }

    if (slugParts.length === 2) {
      const normalizedCategoryType = normalizeCategoryType(categoryType)
      const rawPt = payload?.product_type
      if (rawPt != null && String(rawPt).trim() !== '') {
        const fromApi = normalizeCategoryType(String(rawPt))
        if (fromApi !== normalizedCategoryType) {
          return {
            redirect: {
              destination: `${localePrefix}${buildProductUrl(fromApi, String(payload.slug || productSlug))}`,
              permanent: false,
            },
          }
        }
      }
    }

    const activeVariantSlug = payload?.active_variant_slug
    const baseSlug = payload?.slug
    if (
      slugParts.length === 2 &&
      activeVariantSlug &&
      baseSlug &&
      activeVariantSlug === productSlug &&
      baseSlug !== productSlug
    ) {
      return {
        redirect: {
          destination: `${localePrefix}${buildProductUrl(actualType, baseSlug)}`,
          permanent: false,
        },
      }
    }

    return {
      props: {
        ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
        product: payload,
        productType: actualType,
        isBaseProduct: isBaseProductType(actualType),
        preferredCurrency: currency,
      },
    }
  } catch {
    return { notFound: true }
  }
}
