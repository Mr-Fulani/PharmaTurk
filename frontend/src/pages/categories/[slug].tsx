import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import { getLocalizedCategoryName, getLocalizedCategoryDescription } from '../../lib/i18n'
import { GetServerSideProps } from 'next'
import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import axios from 'axios'
import { getApiForCategory } from '../../lib/api'
import ProductCard from '../../components/ProductCard'
import CategorySidebar, { FilterState, SidebarTreeItem, SidebarTreeSection } from '../../components/CategorySidebar'
import Pagination from '../../components/Pagination'

interface Product {
  id: number
  name: string
  slug: string
  description: string
  price: number
  price_formatted: string
  old_price?: number
  old_price_formatted?: string
  currency: string
  final_price_rub?: number
  final_price_usd?: number
  main_image?: string
  main_image_url?: string
  video_url?: string
  is_available: boolean
  is_featured: boolean
  category?: {
    id: number
    name: string
    slug: string
  }
  brand?: {
    id: number
    name: string
    slug: string
  }
  size?: string
  color?: string
  material?: string
  season?: string
  heel_height?: string
  sole_type?: string
  model?: string
  specifications?: any
  warranty?: string
  power_consumption?: string
}

interface CategoryTranslation {
  locale: string
  name: string
  description?: string
}

interface Category {
  id: number
  name: string
  slug: string
  description: string
  children_count: number
  product_count?: number
  parent?: number | null
  gender?: string
  gender_display?: string
  clothing_type?: string
  translations?: CategoryTranslation[]
  shoe_type?: string
  device_type?: string
}

interface Brand {
  id: number
  name: string
  slug: string
  description: string
  logo?: string
  product_count?: number
}

interface CategoryPageProps {
  products: Product[]
  categories: Category[]
  sidebarCategories: Category[]
  brands: Brand[]
  subcategories?: Category[]
  categoryName: string
  categoryDescription?: string
  totalCount: number
  currentPage: number
  totalPages: number
  initialRouteSlug?: string
  categoryType: 'medicines' | 'clothing' | 'shoes' | 'electronics' | 'supplements' | 'medical-equipment' | 'furniture' | 'tableware' | 'accessories' | 'jewelry' | 'underwear' | 'headwear' | 'books'
  categoryTypeSlug?: string // Реальный тип категории из API (может быть кастомным)
}

type CategoryTypeKey = CategoryPageProps['categoryType']

const brandProductTypeMap: Record<CategoryTypeKey, string> = {
  medicines: 'medicines',
  supplements: 'supplements',
  clothing: 'clothing',
  shoes: 'shoes',
  electronics: 'electronics',
  'medical-equipment': 'medical_equipment',
  furniture: 'furniture',
  tableware: 'tableware',
  accessories: 'accessories',
  jewelry: 'jewelry',
  underwear: 'underwear',
  headwear: 'headwear',
  books: 'books',
}

const resolveBrandProductType = (type: CategoryTypeKey) => brandProductTypeMap[type] || 'medicines'

const normalizeSlug = (value: any) =>
  (value || '')
    .toString()
    .trim()
    .toLowerCase()
    .replace(/_/g, '-')

const filterBrandsByProducts = (
  brands: any[],
  products: any[],
  categoryType: CategoryTypeKey,
  routeSlug?: string
) => {
  const allowedForMedicines = ['medicines', 'supplements', 'medical-equipment']
  const categorySlug = normalizeSlug(routeSlug || categoryType)

  const matchesCategory = (value?: string | null) => {
    const v = normalizeSlug(value)
    if (!v) return false
    if (categoryType === 'medicines') {
      return allowedForMedicines.includes(v)
    }
    return v === categorySlug
  }

  return brands.filter((b: any) => {
    const bPrim = normalizeSlug(b.primary_category_slug)
    const bType = normalizeSlug((b as any).product_type)
    const bSlug = normalizeSlug(b.slug || b.name)
    return matchesCategory(bPrim) || matchesCategory(bType) || matchesCategory(bSlug)
  })
}

const resolveCategoryTypeFromSlug = (slugRaw: string | string[] | undefined): CategoryTypeKey => {
  const slug = Array.isArray(slugRaw) ? slugRaw[0] : slugRaw || ''
  const norm = slug.toLowerCase().replace(/_/g, '-')
  if (norm.startsWith('shoes')) return 'shoes'
  if (norm.startsWith('clothing')) return 'clothing'
  if (norm.startsWith('electronics')) return 'electronics'
  if (norm.startsWith('furniture')) return 'furniture'
  if (norm.startsWith('tableware')) return 'tableware'
  if (norm.startsWith('accessories')) return 'accessories'
  if (norm.startsWith('jewelry')) return 'jewelry'
  if (norm.startsWith('underwear')) return 'underwear'
  if (norm.startsWith('headwear')) return 'headwear'
  if (norm.startsWith('medical-equipment')) return 'medical-equipment'
  if (norm.startsWith('supplements')) return 'supplements'
  if (norm.startsWith('medicines')) return 'medicines'
  if (norm.startsWith('books')) return 'books'
  return 'medicines'
}

const createTreeItem = (category: Category): SidebarTreeItem => ({
  id: `cat-${category.id}`,
  name: category.name,
  slug: category.slug,
  dataId: category.id,
  count: category.product_count,
  type: 'category'
})

// Подкатегории для мужской одежды
const MALE_CLOTHING_ITEMS = [
  { name: 'СВИТЕРЫ', keywords: ['sweaters', 'свитеры', 'свитер'] },
  { name: 'КУРТКИ', keywords: ['jackets', 'куртки', 'куртка'] },
  { name: 'ПУХОВИКИ | ЖИЛЕТЫ', keywords: ['down-jackets', 'vests', 'пуховики', 'жилеты', 'пуховик', 'жилет'] },
  { name: 'ПАЛЬТО И ТРЕНЧИ', keywords: ['coats', 'trench', 'пальто', 'тренчи', 'тренч', 'плащи'] },
  { name: 'КОЖАНЫЕ', keywords: ['leather', 'кожаные', 'кожа'] },
  { name: 'БРЮКИ', keywords: ['trousers', 'pants', 'брюки', 'штаны'] },
  { name: 'ДЖИНСЫ', keywords: ['jeans', 'джинсы'] },
  { name: 'ФУТБОЛКИ', keywords: ['t-shirts', 'футболки', 'футболка'] },
  { name: 'РУБАШКИ', keywords: ['shirts', 'рубашки', 'рубашка'] },
  { name: 'ТОЛСТОВКИ', keywords: ['hoodies', 'sweatshirts', 'толстовки', 'худи'] },
  { name: 'СВИТЕРЫ | КАРДИГАНЫ', keywords: ['cardigans', 'кардиганы', 'кардиган'] },
  { name: 'СПОРТИВНЫЕ КОСТЮМЫ', keywords: ['tracksuits', 'sport-suits', 'спортивные костюмы'] },
  { name: 'КЛАССИЧЕСКИЕ КОСТЮМЫ', keywords: ['suits', 'classic-suits', 'классические костюмы', 'костюмы'] },
  { name: 'ПОЛО', keywords: ['polo', 'поло'] },
  { name: 'КУРТКИ-РУБАШКИ', keywords: ['overshirts', 'shackets', 'куртки-рубашки'] },
  { name: 'БЛЕЙЗЕРЫ', keywords: ['blazers', 'блейзеры', 'пиджаки'] },
  { name: 'СУМКИ | РЮКЗАКИ', keywords: ['bags', 'backpacks', 'сумки', 'рюкзаки'] },
  { name: 'ШОРТЫ', keywords: ['shorts', 'шорты'] },
]

// Подкатегории для женской одежды (включает все из мужской + специфичные)
const FEMALE_CLOTHING_ITEMS = [
  { name: 'СВИТЕРЫ', keywords: ['sweaters', 'свитеры', 'свитер'] },
  { name: 'КУРТКИ', keywords: ['jackets', 'куртки', 'куртка'] },
  { name: 'ПУХОВИКИ | ЖИЛЕТЫ', keywords: ['down-jackets', 'vests', 'пуховики', 'жилеты', 'пуховик', 'жилет'] },
  { name: 'ПАЛЬТО И ТРЕНЧИ', keywords: ['coats', 'trench', 'пальто', 'тренчи', 'тренч', 'плащи'] },
  { name: 'КОЖАНЫЕ', keywords: ['leather', 'кожаные', 'кожа'] },
  { name: 'БРЮКИ', keywords: ['trousers', 'pants', 'брюки', 'штаны'] },
  { name: 'ДЖИНСЫ', keywords: ['jeans', 'джинсы'] },
  { name: 'ФУТБОЛКИ', keywords: ['t-shirts', 'футболки', 'футболка'] },
  { name: 'РУБАШКИ', keywords: ['shirts', 'рубашки', 'рубашка'] },
  { name: 'ТОЛСТОВКИ', keywords: ['hoodies', 'sweatshirts', 'толстовки', 'худи'] },
  { name: 'СВИТЕРЫ | КАРДИГАНЫ', keywords: ['cardigans', 'кардиганы', 'кардиган'] },
  { name: 'СПОРТИВНЫЕ КОСТЮМЫ', keywords: ['tracksuits', 'sport-suits', 'спортивные костюмы'] },
  { name: 'КЛАССИЧЕСКИЕ КОСТЮМЫ', keywords: ['suits', 'classic-suits', 'классические костюмы', 'костюмы'] },
  { name: 'ПОЛО', keywords: ['polo', 'поло'] },
  { name: 'КУРТКИ-РУБАШКИ', keywords: ['overshirts', 'shackets', 'куртки-рубашки'] },
  { name: 'БЛЕЙЗЕРЫ', keywords: ['blazers', 'блейзеры', 'пиджаки'] },
  { name: 'СУМКИ | РЮКЗАКИ', keywords: ['bags', 'backpacks', 'сумки', 'рюкзаки'] },
  { name: 'ПЛАТЬЯ', keywords: ['dresses', 'платья', 'платье'] },
  { name: 'ЮБКИ', keywords: ['skirts', 'юбки', 'юбка'] },
  { name: 'БЛУЗКИ', keywords: ['blouses', 'блузки', 'блузка'] },
  { name: 'ТОПЫ', keywords: ['tops', 'топы', 'топ'] },
  { name: 'ШОРТЫ', keywords: ['shorts', 'шорты'] },
]

// Подкатегории для детской одежды (может быть все, что подходит детям)
const KIDS_CLOTHING_ITEMS = [
  { name: 'СВИТЕРЫ', keywords: ['sweaters', 'свитеры', 'свитер'] },
  { name: 'КУРТКИ', keywords: ['jackets', 'куртки', 'куртка'] },
  { name: 'ПУХОВИКИ | ЖИЛЕТЫ', keywords: ['down-jackets', 'vests', 'пуховики', 'жилеты', 'пуховик', 'жилет'] },
  { name: 'ПАЛЬТО И ТРЕНЧИ', keywords: ['coats', 'trench', 'пальто', 'тренчи', 'тренч', 'плащи'] },
  { name: 'БРЮКИ', keywords: ['trousers', 'pants', 'брюки', 'штаны'] },
  { name: 'ДЖИНСЫ', keywords: ['jeans', 'джинсы'] },
  { name: 'ФУТБОЛКИ', keywords: ['t-shirts', 'футболки', 'футболка'] },
  { name: 'РУБАШКИ', keywords: ['shirts', 'рубашки', 'рубашка'] },
  { name: 'ТОЛСТОВКИ', keywords: ['hoodies', 'sweatshirts', 'толстовки', 'худи'] },
  { name: 'СПОРТИВНЫЕ КОСТЮМЫ', keywords: ['tracksuits', 'sport-suits', 'спортивные костюмы'] },
  { name: 'ПОЛО', keywords: ['polo', 'поло'] },
  { name: 'ПЛАТЬЯ', keywords: ['dresses', 'платья', 'платье'] },
  { name: 'ЮБКИ', keywords: ['skirts', 'юбки', 'юбка'] },
  { name: 'СУМКИ | РЮКЗАКИ', keywords: ['bags', 'backpacks', 'сумки', 'рюкзаки'] },
  { name: 'ШОРТЫ', keywords: ['shorts', 'шорты'] },
]

const GENDER_SUBITEMS: Record<string, typeof MALE_CLOTHING_ITEMS> = {
  male: MALE_CLOTHING_ITEMS,
  female: FEMALE_CLOTHING_ITEMS,
  kids: KIDS_CLOTHING_ITEMS,
}

const clothingGenderKeywords: Record<string, string[]> = {
  male: ['male', 'men', 'муж', 'мужская'],
  female: ['female', 'women', 'жен', 'женская'],
  kids: ['kids', 'children', 'дет', 'детская']
}

const buildClothingSections = (categories: Category[]): SidebarTreeSection[] => {
  const sections = [
    { key: 'male', title: 'Мужская одежда' },
    { key: 'female', title: 'Женская одежда' },
    { key: 'kids', title: 'Детская одежда' }
  ]

  return sections.map(({ key, title }) => {
    const genderKeywords = clothingGenderKeywords[key] || []
    const subitemsStructure = GENDER_SUBITEMS[key] || []
    
    const genderCategories = categories.filter((category) => {
        // Check explicit gender field if available
        if (category.gender) {
            return category.gender === key
        }
        // Fallback to keyword matching in slug/name
        return genderKeywords.some((keyword) => category.slug.includes(keyword) || category.name.toLowerCase().includes(keyword))
    })

    const subcategories: SidebarTreeItem[] = []
    const usedCategoryIds = new Set<number>()
    
    // Добавляем подкатегории для данного гендера
    subitemsStructure.forEach((itemStruct, index) => {
      const match = genderCategories.find(cat => 
        itemStruct.keywords.some(kw => cat.slug.toLowerCase().includes(kw) || cat.name.toLowerCase().includes(kw))
      )
      
      if (match && !usedCategoryIds.has(match.id)) {
        usedCategoryIds.add(match.id)
        subcategories.push({
          id: `cat-${match.id}`,
          name: match.name, // Используем реальное название категории для локализации
          slug: match.slug,
          dataId: match.id,
          count: match.product_count,
          type: 'category'
        })
      } else {
        // Показываем подкатегорию даже если данных нет
        subcategories.push({
          id: `placeholder-${key}-${index}`,
          name: itemStruct.name,
          slug: undefined,
          dataId: undefined,
          count: undefined,
          type: 'category'
        })
      }
    })

    // Добавляем оставшиеся категории, которых нет в структуре
    genderCategories.forEach(cat => {
        if (!usedCategoryIds.has(cat.id)) {
            subcategories.push(createTreeItem(cat))
        }
    })

    // Создаем главный раздел с вложенными подкатегориями
    return {
      title,
      items: [{
        id: `section-${key}`,
        name: title,
        type: 'category',
        children: subcategories
      }]
    }
  })
}
// Подкатегории для обезболивающих
const PAINKILLERS_SUBITEMS = [
  { name: 'Анальгетики', keywords: ['analgesic', 'анальгетик'] },
  { name: 'Противовоспалительные', keywords: ['anti-inflammatory', 'противовоспалител'] },
  { name: 'Спазмолитики', keywords: ['antispasmodic', 'спазмолитик'] },
  { name: 'Обезболивающие мази', keywords: ['pain-relief-cream', 'обезболивающая мазь'] },
  { name: 'Мигрень и головная боль', keywords: ['migraine', 'headache', 'мигрень', 'головная боль'] },
]

// Подкатегории для антибиотиков
const ANTIBIOTICS_SUBITEMS = [
  { name: 'Пенициллины', keywords: ['penicillin', 'пенициллин'] },
  { name: 'Цефалоспорины', keywords: ['cephalosporin', 'цефалоспорин'] },
  { name: 'Макролиды', keywords: ['macrolide', 'макролид'] },
  { name: 'Фторхинолоны', keywords: ['fluoroquinolone', 'фторхинолон'] },
  { name: 'Тетрациклины', keywords: ['tetracycline', 'тетрациклин'] },
  { name: 'Антибиотики широкого спектра', keywords: ['broad-spectrum', 'широкого спектра'] },
]

// Подкатегории для витаминов
const VITAMINS_SUBITEMS = [
  { name: 'Витамин C', keywords: ['vitamin-c', 'витамин с', 'аскорбиновая'] },
  { name: 'Витамин D', keywords: ['vitamin-d', 'витамин д'] },
  { name: 'Витамин B комплекс', keywords: ['vitamin-b', 'витамин б', 'витамин в'] },
  { name: 'Мультивитамины', keywords: ['multivitamin', 'мультивитамин'] },
  { name: 'Кальций и магний', keywords: ['calcium', 'magnesium', 'кальций', 'магний'] },
  { name: 'Железо', keywords: ['iron', 'железо'] },
  { name: 'Омега-3', keywords: ['omega-3', 'омега-3'] },
  { name: 'Иммуномодуляторы', keywords: ['immunomodulator', 'иммуномодулятор'] },
]

// Подкатегории для гинекологии
const GYNECOLOGY_SUBITEMS = [
  { name: 'Контрацептивы', keywords: ['contraceptive', 'контрацептив'] },
  { name: 'Гормональные препараты', keywords: ['hormonal', 'гормональн'] },
  { name: 'Противовоспалительные', keywords: ['anti-inflammatory', 'противовоспалител'] },
  { name: 'Молочница', keywords: ['candidiasis', 'thrush', 'молочница', 'кандидоз'] },
  { name: 'Климакс', keywords: ['menopause', 'климакс'] },
  { name: 'Беременность', keywords: ['pregnancy', 'беременност'] },
]

// Подкатегории для онкологии
const ONCOLOGY_SUBITEMS = [
  { name: 'Химиотерапия', keywords: ['chemotherapy', 'химиотерап'] },
  { name: 'Иммунотерапия', keywords: ['immunotherapy', 'иммунотерап'] },
  { name: 'Обезболивание', keywords: ['pain-management', 'обезболивани'] },
  { name: 'Поддерживающая терапия', keywords: ['supportive-care', 'поддерживающ'] },
  { name: 'Восстановление', keywords: ['recovery', 'восстановлени'] },
]

const MEDICINE_GROUPS = [
  {
    label: 'Обезболивающие',
    keywords: ['pain', 'обезбол'],
    subitems: PAINKILLERS_SUBITEMS
  },
  {
    label: 'Антибиотики',
    keywords: ['antibiotic', 'антибиот'],
    subitems: ANTIBIOTICS_SUBITEMS
  },
  {
    label: 'Витамины и иммунитет',
    keywords: ['vitamin', 'витамин'],
    subitems: VITAMINS_SUBITEMS
  },
  {
    label: 'Гинекология',
    keywords: ['gynec', 'гинек'],
    subitems: GYNECOLOGY_SUBITEMS
  },
  {
    label: 'Онкология',
    keywords: ['oncology', 'онколо', 'рак'],
    subitems: ONCOLOGY_SUBITEMS
  }
]

const buildMedicineSections = (categories: Category[]): SidebarTreeSection[] =>
  MEDICINE_GROUPS.map((group) => {
    const groupCategories = categories.filter((category) =>
      group.keywords.some((keyword) => category.slug.includes(keyword) || category.name.toLowerCase().includes(keyword))
    )

    const subcategories: SidebarTreeItem[] = []
    const usedCategoryIds = new Set<number>()
    
    // Добавляем подкатегории для данной группы
    group.subitems.forEach((itemStruct, index) => {
      const match = groupCategories.find(cat => 
        itemStruct.keywords.some(kw => cat.slug.toLowerCase().includes(kw) || cat.name.toLowerCase().includes(kw))
      )
      
      if (match && !usedCategoryIds.has(match.id)) {
        usedCategoryIds.add(match.id)
        subcategories.push({
          id: `med-${match.id}`,
          name: match.name, // Используем реальное название категории для локализации
          slug: match.slug,
          dataId: match.id,
          count: match.product_count,
          type: 'category'
        })
      } else {
        // Показываем подкатегорию даже если данных нет
        subcategories.push({
          id: `placeholder-med-${group.label}-${index}`,
          name: itemStruct.name,
          slug: undefined,
          dataId: undefined,
          count: undefined,
          type: 'category'
        })
      }
    })

    // Добавляем оставшиеся категории группы, которых нет в структуре
    groupCategories.forEach(cat => {
        if (!usedCategoryIds.has(cat.id)) {
            subcategories.push({
              id: `med-${cat.id}`,
              name: cat.name,
              slug: cat.slug,
              dataId: cat.id,
              count: cat.product_count,
              type: 'category'
            })
        }
    })

    // Создаем главный раздел с вложенными подкатегориями
    return {
      title: group.label,
      items: [{
        id: `section-med-${group.label}`,
        name: group.label,
        type: 'category',
        children: subcategories
      }]
    }
  })

const getCategorySections = (type: CategoryPageProps['categoryType'], categories: Category[]): SidebarTreeSection[] => {
  if (type === 'clothing') {
    return buildClothingSections(categories)
  }
  if (type === 'medicines') {
    return buildMedicineSections(categories)
  }
  if (type === 'books') {
    return buildBookSections(categories)
  }
  return []
}

const BOOK_GROUPS = [
  {
    label: 'Исламская литература',
    keywords: ['ислам', 'islamic', 'фикх', 'fiqh', 'тафсир', 'tafsir', 'адаб', 'adab', 'хадис', 'hadith'],
    subitems: [
      { name: 'Исламский фикх', keywords: ['фикх', 'fiqh', 'islamic-fiqh'] },
      { name: 'Тафсир', keywords: ['тафсир', 'tafsir'] },
      { name: 'Адаб', keywords: ['адаб', 'adab'] },
      { name: 'Хадис', keywords: ['хадис', 'hadith'] },
      { name: 'История', keywords: ['история', 'history'] },
    ]
  },
  {
    label: 'Бизнес',
    keywords: ['бизнес', 'business'],
    subitems: [
      { name: 'Бизнес литература', keywords: ['бизнес', 'business'] },
    ]
  },
  {
    label: 'Наука',
    keywords: ['науч', 'science'],
    subitems: [
      { name: 'Научная литература', keywords: ['науч', 'science'] },
    ]
  },
  {
    label: 'Художественная',
    keywords: ['худож', 'fiction'],
    subitems: [
      { name: 'Художественная литература', keywords: ['худож', 'fiction'] },
    ]
  }
]

const buildBookSections = (categories: Category[]): SidebarTreeSection[] =>
  BOOK_GROUPS.map((group) => {
    const groupCategories = categories.filter((category) =>
      group.keywords.some((keyword) => category.slug.includes(keyword) || category.name.toLowerCase().includes(keyword))
    )

    const subcategories: SidebarTreeItem[] = []
    const usedCategoryIds = new Set<number>()
    
    // Добавляем подкатегории для данной группы
    group.subitems.forEach((itemStruct, index) => {
      const match = groupCategories.find(cat => 
        itemStruct.keywords.some(kw => cat.slug.toLowerCase().includes(kw) || cat.name.toLowerCase().includes(kw))
      )
      
      if (match && !usedCategoryIds.has(match.id)) {
        usedCategoryIds.add(match.id)
        subcategories.push({
          id: `book-${match.id}`,
          name: match.name,
          slug: match.slug,
          dataId: match.id,
          count: match.product_count,
          type: 'category'
        })
      } else {
        // Показываем подкатегорию даже если данных нет
        subcategories.push({
          id: `placeholder-book-${group.label}-${index}`,
          name: itemStruct.name,
          slug: undefined,
          dataId: undefined,
          count: undefined,
          type: 'category'
        })
      }
    })

    // Добавляем оставшиеся категории группы, которых нет в структуре
    groupCategories.forEach(cat => {
        if (!usedCategoryIds.has(cat.id)) {
            subcategories.push({
              id: `book-${cat.id}`,
              name: cat.name,
              slug: cat.slug,
              dataId: cat.id,
              count: cat.product_count,
              type: 'category'
            })
        }
    })

    // Создаем главный раздел с вложенными подкатегориями
    return {
      title: group.label,
      items: [{
        id: `section-book-${group.label}`,
        name: group.label,
        type: 'category',
        children: subcategories
      }]
    }
  })

const normalizePageParam = (value: string | string[] | undefined): number => {
  if (!value) {
    return 1
  }
  const raw = Array.isArray(value) ? value[0] : value
  const parsed = parseInt(raw ?? '', 10)
  if (Number.isNaN(parsed) || parsed < 1) {
    return 1
  }
  return parsed
}

// Фронтовая фильтрация по дополнительным фильтрам (без нагрузки на бэкенд)
const filterProductsByExtraFilters = (products: Product[], filters: FilterState, categoryType: CategoryTypeKey) => {
  console.log(`filterProductsByExtraFilters: ${products.length} products, categoryType: ${categoryType}`)
  
  const norm = (v: any) => normalizeSlug(v)
  const getCatSlug = (p: any) => norm(p?.category?.slug || (p as any).category_slug || '')

  let result = products

  if (categoryType === 'shoes' && filters.shoeTypes && filters.shoeTypes.length) {
    const wanted = new Set(filters.shoeTypes.map(norm))
    result = result.filter((p) => {
      const cat = getCatSlug(p)
      return Array.from(wanted).some((w) => cat.includes(w) || norm(p.slug).includes(w))
    })
  }

  if (categoryType === 'clothing' && filters.clothingItems && filters.clothingItems.length) {
    const wanted = new Set(filters.clothingItems.map(norm))
    result = result.filter((p) => {
      const cat = getCatSlug(p)
      return Array.from(wanted).some((w) => cat.includes(w) || norm(p.slug).includes(w))
    })
  }

  if (categoryType === 'jewelry') {
    if (filters.jewelryMaterials && filters.jewelryMaterials.length) {
      const wanted = new Set(filters.jewelryMaterials.map(norm))
      result = result.filter((p) => {
        const cat = getCatSlug(p)
        return Array.from(wanted).some((w) => cat.includes(w) || norm(p.slug).includes(w))
      })
    }
    if (filters.jewelryGender && filters.jewelryGender.length) {
      const wantedG = new Set(filters.jewelryGender.map(norm))
      result = result.filter((p) => {
        const cat = getCatSlug(p)
        return Array.from(wantedG).some((w) => cat.includes(w) || norm(p.slug).includes(w))
      })
    }
  }

  if (categoryType === 'headwear' && filters.headwearTypes && filters.headwearTypes.length) {
    const wanted = new Set(filters.headwearTypes.map(norm))
    result = result.filter((p) => {
      const cat = getCatSlug(p)
      return Array.from(wanted).some((w) => cat.includes(w) || norm(p.slug).includes(w))
    })
  }

  // Для книг не применяем фильтрацию - показываем все книги
  
  console.log(`filterProductsByExtraFilters result: ${result.length} products`)

  return result
}

export default function CategoryPage({
  products: initialProducts,
  categories,
  sidebarCategories,
  brands,
  subcategories = [],
  categoryName,
  categoryDescription,
  totalCount: initialTotalCount,
  currentPage: initialCurrentPage,
  totalPages: initialTotalPages,
  categoryType,
  initialRouteSlug,
  categoryTypeSlug
}: CategoryPageProps) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const { slug } = router.query

  // Сохранение и восстановление позиции скролла при возврате на страницу
  useEffect(() => {
    if (typeof window === 'undefined') return

    const scrollKey = `scroll_${router.asPath}`
    let shouldRestoreScroll = false
    
    // Сохраняем позицию скролла при уходе со страницы
    const handleRouteChangeStart = (url: string) => {
      if (url !== router.asPath) {
        sessionStorage.setItem(scrollKey, String(window.scrollY))
      }
    }

    const handleRouteChangeComplete = (url: string) => {
      if (url === router.asPath) {
        shouldRestoreScroll = true
        const savedScroll = sessionStorage.getItem(scrollKey)
        if (savedScroll) {
          const scrollY = parseInt(savedScroll, 10)
          // Используем requestAnimationFrame для восстановления после рендера
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              window.scrollTo({ top: scrollY, behavior: 'auto' })
            })
          })
        }
      }
    }

    const handleBeforeUnload = () => {
      sessionStorage.setItem(scrollKey, String(window.scrollY))
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        sessionStorage.setItem(scrollKey, String(window.scrollY))
      } else if (shouldRestoreScroll) {
        const savedScroll = sessionStorage.getItem(scrollKey)
        if (savedScroll) {
          const scrollY = parseInt(savedScroll, 10)
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              window.scrollTo({ top: scrollY, behavior: 'auto' })
            })
          })
        }
      }
    }

    // Восстанавливаем позицию скролла при монтировании (если это возврат на страницу)
    const savedScroll = sessionStorage.getItem(scrollKey)
    if (savedScroll && router.isReady) {
      const scrollY = parseInt(savedScroll, 10)
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          window.scrollTo({ top: scrollY, behavior: 'auto' })
        })
      })
    }

    router.events.on('routeChangeStart', handleRouteChangeStart)
    router.events.on('routeChangeComplete', handleRouteChangeComplete)
    window.addEventListener('beforeunload', handleBeforeUnload)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      router.events.off('routeChangeStart', handleRouteChangeStart)
      router.events.off('routeChangeComplete', handleRouteChangeComplete)
      window.removeEventListener('beforeunload', handleBeforeUnload)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [router.asPath, router.isReady, router.events])

  // Получаем текущую категорию с переводами из API
  const currentCategory = useMemo(() => {
    const routeSlug = Array.isArray(slug) ? slug[0] : slug
    if (!routeSlug) return null
    const normalizedSlug = routeSlug.toLowerCase().replace(/_/g, '-')
    return categories.find((c: Category) => (c.slug || '').toLowerCase().replace(/_/g, '-') === normalizedSlug) || null
  }, [categories, slug])

  // Локализация названия категории на клиенте (обновляется при смене языка)
  const localizedCategoryName = useMemo(() => {
    const routeSlug = Array.isArray(slug) ? slug[0] : slug
    const normalizedSlug = routeSlug ? routeSlug.toLowerCase().replace(/_/g, '-') : null
    
    // Используем функцию локализации, которая проверяет JSON, потом API, потом fallback
    if (currentCategory) {
      return getLocalizedCategoryName(
        currentCategory.slug,
        currentCategory.name,
        t,
        currentCategory.translations,
        router.locale
      )
    }
    
    // Fallback на старый подход, если категория не найдена
    if (normalizedSlug) {
      const slugKey = `category_${normalizedSlug}_name`
      const translatedBySlug = t(slugKey, { defaultValue: null })
      if (translatedBySlug && translatedBySlug !== slugKey) {
        return translatedBySlug
      }
    }
    
    // Fallback на статический маппинг по categoryType
    const categoryNameKeys: Record<string, string> = {
      medicines: 'category_medicines',
      supplements: 'category_supplements',
      clothing: 'category_clothing',
      shoes: 'category_shoes',
      electronics: 'category_electronics',
      tableware: 'category_tableware',
      furniture: 'category_furniture',
      accessories: 'category_accessories',
      jewelry: 'category_jewelry',
      underwear: 'category_underwear',
      headwear: 'category_headwear',
      'medical-equipment': 'category_medical_equipment',
      'medical_equipment': 'category_medical_equipment', // поддержка формата с подчеркиванием
      uslugi: 'category_uslugi_name' // услуги
    }
    const normalizedType = categoryType?.replace(/_/g, '-')
    const key = categoryNameKeys[normalizedType] || categoryNameKeys[categoryType]
    if (key) {
      const translated = t(key, { defaultValue: categoryName })
      return translated
    }
    return categoryName
  }, [categoryType, categoryName, t, router.locale, slug, currentCategory])

  const [products, setProducts] = useState(initialProducts)
  const [totalCount, setTotalCount] = useState(initialTotalCount)
  const [currentPage, setCurrentPage] = useState(initialCurrentPage)
  const [totalPages, setTotalPages] = useState(initialTotalPages)
  const [loading, setLoading] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const initialBrandsRef = useRef<Brand[]>(brands || [])
  useEffect(() => {
    if (initialBrandsRef.current.length === 0 && brands.length > 0) {
      initialBrandsRef.current = brands
    }
  }, [brands])
  const brandOptions = initialBrandsRef.current
  const [filters, setFilters] = useState<FilterState>({
    categories: [],
    categorySlugs: [],
    brands: [],
    brandSlugs: [],
    subcategories: [],
    subcategorySlugs: [],
    inStock: false,
    sortBy: 'name_asc',
    shoeTypes: [],
    clothingItems: [],
    jewelryMaterials: [],
    jewelryGender: [],
  })
  const categoryGroups = useMemo(() => getCategorySections(categoryType, categories), [categoryType, categories])
  // Используем реальный тип из API если есть, иначе fallback на маппинг
  const resolvedBrandType = useMemo(() => categoryTypeSlug || resolveBrandProductType(categoryType), [categoryTypeSlug, categoryType])
  const filtersInitialized = useRef<string>('')
  
  const updatePageQuery = useCallback((page: number, options: { replace?: boolean } = {}) => {
    if (!router.isReady) return
    const nextQuery: Record<string, string | string[] | undefined> = { ...router.query }
    if (page <= 1) {
      delete nextQuery.page
    } else {
      nextQuery.page = String(page)
    }
    const navigate = options.replace ? router.replace : router.push
    navigate(
      {
        pathname: router.pathname,
        query: nextQuery
      },
      undefined,
      { shallow: true, scroll: false }
    ).catch((error) => {
      console.error('Не удалось обновить параметр страницы в URL:', error)
    })
  }, [router])
  
  useEffect(() => {
    if (!router.isReady) return
    const nextPage = normalizePageParam(router.query.page)
    setCurrentPage((prev) => (prev === nextPage ? prev : nextPage))
  }, [router.isReady, router.query.page])

  // Инициализация фильтров из query параметров
  useEffect(() => {
    if (!router.isReady) return
    
    const { brand_id } = router.query
    const brandIdStr = brand_id ? (Array.isArray(brand_id) ? brand_id[0] : String(brand_id)) : ''
    const initKey = `${router.asPath}-${brandIdStr}`
    
    // Если уже инициализировали для этого URL, пропускаем
    if (filtersInitialized.current === initKey) return
    
    if (brand_id) {
      const brandId = Array.isArray(brand_id) ? parseInt(brand_id[0]) : parseInt(brand_id as string)
      if (!isNaN(brandId)) {
        setFilters((prev) => {
          // Если уже установлен правильный бренд, просто обновляем ключ
          if (prev.brands.length === 1 && prev.brands[0] === brandId) {
            filtersInitialized.current = initKey
            return prev
          }
          filtersInitialized.current = initKey
          return {
            ...prev,
            brands: [brandId],
            brandSlugs: []
          }
        })
        return
      }
    } else {
      // Если brand_id нет в URL, очищаем фильтр брендов только если он был установлен
      setFilters((prev) => {
        if (prev.brands.length === 0) {
          filtersInitialized.current = initKey
          return prev
        }
        filtersInitialized.current = initKey
        return {
          ...prev,
          brands: [],
          brandSlugs: []
        }
      })
    }
  }, [router.isReady, router.asPath, router.query.brand_id])

  useEffect(() => {
    const loadBrands = async () => {
      try {
        const params: Record<string, any> = {
          product_type: resolvedBrandType
        }
        const normalizedSlug = (routeSlug || categoryType || '').toString().toLowerCase().replace(/_/g, '-')
        if (normalizedSlug) {
          params.primary_category_slug = normalizedSlug
        }
        if (filters.categories.length > 0) {
          params.category_id = filters.categories
        } else if (filters.categorySlugs.length > 0) {
          params.category_slug = filters.categorySlugs.join(',')
        }
        if (filters.inStock) {
          params.in_stock = true
        }
        const base = process.env.NEXT_PUBLIC_API_BASE || '/api'
        const response = await axios.get(`${base}/catalog/brands`, { params })
        const list = Array.isArray(response.data) ? response.data : response.data.results || []
        if (initialBrandsRef.current.length === 0 && list.length > 0) {
          initialBrandsRef.current = list
        }
        // НЕ обновляем filters.brands если brand_id есть в URL - он должен быть установлен через инициализацию
        const { brand_id } = router.query
        if (brand_id) {
          // Если brand_id есть в URL, не трогаем фильтры - они должны быть установлены через инициализацию
          const brandIdFromUrl = Array.isArray(brand_id) ? parseInt(brand_id[0]) : parseInt(brand_id as string)
          if (!isNaN(brandIdFromUrl)) {
            // Просто проверяем, что бренд доступен, но не меняем фильтры
            const allowedIds = new Set(list.map((brand: any) => brand.id))
            if (allowedIds.has(brandIdFromUrl)) {
              // Бренд доступен - фильтры должны быть установлены через инициализацию
              return
            }
          }
        }
        
        // Если нет brand_id в URL, очищаем только несуществующие бренды
        setFilters((prev) => {
          const allowedIds = new Set(list.map((brand: any) => brand.id))
          const allowedSlugs = new Set(list.map((brand: any) => brand.slug))
          const nextBrandIds = prev.brands.filter((id) => allowedIds.has(id))
          const nextBrandSlugs = prev.brandSlugs.filter((slug) => !slug || allowedSlugs.has(slug))
          
          // Обновляем только если действительно изменилось
          if (nextBrandIds.length === prev.brands.length && 
              nextBrandSlugs.length === prev.brandSlugs.length &&
              nextBrandIds.every((id, idx) => prev.brands[idx] === id)) {
            return prev
          }
          
          return {
            ...prev,
            brands: nextBrandIds,
            brandSlugs: nextBrandSlugs
          }
        })
      } catch (error) {
        console.error('Error loading brands:', error)
      }
    }

    loadBrands()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedBrandType, filters.categories, filters.categorySlugs, filters.inStock, router.query.brand_id])

  // Загрузка товаров с фильтрами
  useEffect(() => {
    let isCancelled = false

    const loadProducts = async () => {
      if (!router.isReady) return
      
      // Если brand_id есть в URL, используем его напрямую, даже если фильтры еще не инициализированы
      const { brand_id } = router.query
      let brandIdToUse: number | null = null
      
      if (brand_id) {
        const brandIdFromUrl = Array.isArray(brand_id) ? parseInt(brand_id[0]) : parseInt(brand_id as string)
        if (!isNaN(brandIdFromUrl)) {
          brandIdToUse = brandIdFromUrl
        }
      }
      
      // Если brand_id в URL, но его нет в фильтрах, используем brand_id из URL
      // Это нужно для случая, когда фильтры еще не инициализированы
      const effectiveBrandIds = brandIdToUse && !filters.brands.includes(brandIdToUse) 
        ? [brandIdToUse] 
        : filters.brands
      
      setLoading(true)
      try {
        const params: any = {
          page: currentPage,
          page_size: 12
        }

        // Ограничиваем выдачу конкретным слагом категории из URL, чтобы не падать в default (medicines)
        const routeSlug = Array.isArray(router.query.slug) ? router.query.slug[0] : (router.query.slug as string | undefined)
        if (routeSlug) {
          // Для книг используем product_type чтобы показать все книги из всех жанров
          if (categoryType === 'books') {
            params.product_type = 'books'
          } else {
            params.category_slug = routeSlug
          }
        }

        if (filters.categories.length > 0) {
          params.category_id = filters.categories
        }
        if (filters.categorySlugs.length > 0) {
          params.category_slug = filters.categorySlugs.join(',')
        }
        if (effectiveBrandIds.length > 0) {
          params.brand_id = effectiveBrandIds
        }
        if (filters.brandSlugs.length > 0) {
          params.brand_slug = filters.brandSlugs.join(',')
        }
        if (filters.subcategories.length > 0) {
          params.subcategory_id = filters.subcategories
        }
        if (filters.subcategorySlugs.length > 0) {
          // Для книг используем category_slug вместо subcategory_slug
          if (categoryType === 'books') {
            params.category_slug = filters.subcategorySlugs.join(',')
          } else {
            params.subcategory_slug = filters.subcategorySlugs.join(',')
          }
        }
        if (filters.priceMin !== undefined) {
          params.price_min = filters.priceMin
        }
        if (filters.priceMax !== undefined) {
          params.price_max = filters.priceMax
        }
        if (filters.inStock) {
          params.in_stock = true
        }
        if (filters.sortBy) {
          params.ordering = filters.sortBy
        }

        const api = getApiForCategory(categoryType)
        
        console.log('Loading products with params:', params)
        const response = await api.getProducts(params)
        const data = response.data
        const productsList = Array.isArray(data) ? data : (data.results || [])
        const filteredList = filterProductsByExtraFilters(productsList, filters, categoryType)
        // Используем count из API для правильной пагинации
        const count = data.count || filteredList.length

        console.log(`Loaded ${productsList.length} products (after filters: ${filteredList.length}), total count: ${count}`)
        console.log('Category type:', categoryType)
        console.log('Sample product:', productsList[0])
        if (isCancelled) return
        setProducts(filteredList)
        setTotalCount(count)
        setTotalPages(Math.ceil(count / 12))
      } catch (error) {
        if (!isCancelled) {
          console.error('Error loading products:', error)
        }
      } finally {
        if (!isCancelled) {
          setLoading(false)
        }
      }
    }

    loadProducts()

    return () => {
      isCancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    router.isReady,
    router.query.brand_id,
    filters.categories,
    filters.categorySlugs,
    filters.brands,
    filters.brandSlugs,
    filters.subcategories,
    filters.subcategorySlugs,
    filters.priceMin,
    filters.priceMax,
    filters.inStock,
    filters.sortBy,
    filters.shoeTypes,
    filters.clothingItems,
    filters.jewelryMaterials,
    filters.jewelryGender,
    filters.headwearTypes,
    currentPage,
    categoryType
  ])

  const handlePageChange = (page: number) => {
    const total = Math.max(totalPages, 1)
    const safePage = Math.min(Math.max(page, 1), total)
    setCurrentPage((prev) => (prev === safePage ? prev : safePage))
    const currentQueryPage = router.isReady ? normalizePageParam(router.query.page) : safePage
    if (safePage !== currentQueryPage) {
      updatePageQuery(safePage)
      // Скроллим в начало только при явной смене страницы пагинации
      if (typeof window !== 'undefined') {
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }
    }
  }

  const handleFilterChange = useCallback((newFilters: FilterState) => {
    setFilters(newFilters)
    setCurrentPage((prev) => (prev === 1 ? prev : 1))
    updatePageQuery(1, { replace: true })
  }, [updatePageQuery])

  const routeSlugFromQuery = useMemo(() => {
    const slugParam = router.query.slug
    return Array.isArray(slugParam) ? slugParam[0] : slugParam || ''
  }, [router.query.slug])

  // Используем серверный slug на первом рендере, чтобы избежать «all categories» до гидратации
  const [routeSlug, setRouteSlug] = useState(initialRouteSlug || routeSlugFromQuery)
  useEffect(() => {
    if (routeSlugFromQuery && routeSlugFromQuery !== routeSlug) {
      setRouteSlug(routeSlugFromQuery)
    }
  }, [routeSlugFromQuery, routeSlug])

  // Фиксируем список категорий для сайтбара на первом рендере, чтобы он не затирался гидрацией
  const initialSidebarCategoriesRef = useRef<Category[]>(Array.isArray(sidebarCategories) && sidebarCategories.length > 0 ? sidebarCategories : categories)
  useEffect(() => {
    if (initialSidebarCategoriesRef.current.length === 0 && sidebarCategories.length > 0) {
      initialSidebarCategoriesRef.current = sidebarCategories
    }
  }, [sidebarCategories])
  const sidebarCategoriesData = useMemo(() => {
    const base = initialSidebarCategoriesRef.current || []
    if (!base.length) return base

    const normSlug = (routeSlug || '').toLowerCase().replace(/_/g, '-')
    const main = base.find((c) => (c.slug || '').toLowerCase().replace(/_/g, '-') === normSlug)

    if (main) {
      const children = base.filter((c) => c.parent === main.id)
      return [main, ...children]
    }

    // Если не нашли категорию по slug — как fallback берём только корневые
    return base.filter((c) => c.parent === null)
  }, [routeSlug])

  const brandLabel = useMemo(() => {
    const brandIdParam = router.query.brand_id
    const brandSlugParam = router.query.brand
    let found = null
    if (brandIdParam) {
      const brandId = Array.isArray(brandIdParam) ? parseInt(brandIdParam[0]) : parseInt(String(brandIdParam))
      if (!isNaN(brandId)) {
        found = brands.find((b) => b.id === brandId)?.name || null
      }
    }
    if (!found && brandSlugParam) {
      const slug = Array.isArray(brandSlugParam) ? brandSlugParam[0] : String(brandSlugParam)
      found = brands.find((b) => b.slug === slug)?.name || null
    }
    return found
  }, [brands, router.query.brand, router.query.brand_id])

  const breadcrumbs = useMemo(() => {
    const items = [
      { href: '/', label: t('breadcrumb_home', 'Главная') },
      { href: '/categories', label: t('breadcrumb_categories', 'Категории') },
      { href: `/categories/${routeSlug}`, label: localizedCategoryName || t('category', 'Категория') },
    ]
    if (brandLabel) {
      items.push({ href: router.asPath, label: brandLabel })
    }
    return items
  }, [brandLabel, localizedCategoryName, routeSlug, router.asPath, t])

  const siteUrl = useMemo(() => (process.env.NEXT_PUBLIC_SITE_URL || 'https://pharmaturk.ru').replace(/\/$/, ''), [])
  const canonicalUrl = useMemo(() => `${siteUrl}/categories/${routeSlug || categoryType}`, [siteUrl, routeSlug, categoryType])
  const ogTitle = useMemo(() => `${localizedCategoryName} — PharmaTurk`, [localizedCategoryName])
  const ogDescription = useMemo(
    () => categoryDescription || t('catalog_of_category', 'Каталог {{category}} в PharmaTurk', { category: localizedCategoryName.toLowerCase() }),
    [categoryDescription, localizedCategoryName, t]
  )
  const breadcrumbSchema = useMemo(() => {
    const items = breadcrumbs.map((item, idx) => ({
      '@type': 'ListItem',
      position: idx + 1,
      name: item.label,
      item: `${siteUrl}${item.href}`
    }))
    return {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: items
    }
  }, [breadcrumbs, siteUrl])

  return (
    <>
      <Head>
        <title>{localizedCategoryName} - PharmaTurk</title>
        <meta name="description" content={ogDescription} />
        <link rel="canonical" href={canonicalUrl} />
        <link rel="alternate" hrefLang="ru" href={canonicalUrl} />
        <meta property="og:title" content={ogTitle} />
        <meta property="og:description" content={ogDescription} />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:type" content="website" />
        <meta property="twitter:title" content={ogTitle} />
        <meta property="twitter:description" content={ogDescription} />
        <meta property="twitter:card" content="summary_large_image" />
        <script
          type="application/ld+json"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbSchema) }}
        />
      </Head>
      
      {/* Hero Section */}
      <div className="text-white py-12 dark:bg-[#0a1222]" style={{ backgroundColor: 'var(--accent)' }}>
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-4xl md:text-5xl font-bold mb-4">{localizedCategoryName}</h1>
              {(() => {
                const localizedDesc = currentCategory 
                  ? getLocalizedCategoryDescription(currentCategory.slug, currentCategory.description, t, currentCategory.translations, router.locale)
                  : categoryDescription
                return localizedDesc ? (
                  <p className="text-lg md:text-xl opacity-90 max-w-2xl">{localizedDesc}</p>
                ) : null
              })()}
              <p className="mt-4 text-sm opacity-80">
                {t('products_found', 'Найдено товаров')}: <span className="font-semibold">{totalCount}</span>
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Breadcrumbs */}
      <nav className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-3 text-sm text-main flex flex-wrap items-center gap-2">
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

      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col lg:flex-row gap-8">
          {/* Sidebar */}
          <div className="lg:w-1/4">
            <CategorySidebar
              key={routeSlug || categoryType}
              categories={categoryGroups.length > 0 ? [] : sidebarCategoriesData}
              brands={brandOptions}
              subcategories={subcategories}
              categoryGroups={[]} // отключаем группировки, используем предфильтрованный список
              onFilterChange={handleFilterChange}
              isOpen={sidebarOpen}
              onToggle={() => setSidebarOpen(!sidebarOpen)}
              initialFilters={filters}
              showSubcategories={true}
              categoryType={categoryType}
            />
          </div>

          {/* Main Content */}
          <div className="lg:w-3/4">
            {/* Toolbar */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
              {/* Mobile filter button */}
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden flex items-center gap-2 px-4 py-2 bg-[var(--surface)] border border-[var(--border)] rounded-lg hover:bg-[var(--accent-soft)] transition-colors text-main"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                </svg>
                {t('sidebar_filters', 'Фильтры')}
              </button>

              {/* View mode toggle */}
              <div className="flex items-center gap-2 ml-auto">
                <button
                  onClick={() => setViewMode('grid')}
                  className={`p-2 rounded-lg transition-colors ${
                    viewMode === 'grid'
                      ? 'bg-[var(--accent-soft)] text-[var(--accent)]'
                      : 'bg-[var(--surface)] text-main hover:bg-[var(--accent-soft)]'
                  }`}
                  aria-label="Grid view"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                  </svg>
                </button>
                  <button
                  onClick={() => setViewMode('list')}
                  className={`p-2 rounded-lg transition-colors ${
                    viewMode === 'list'
                      ? 'bg-[var(--accent-soft)] text-[var(--accent)]'
                      : 'bg-[var(--surface)] text-main hover:bg-[var(--accent-soft)]'
                  }`}
                  aria-label="List view"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                  </button>
              </div>
            </div>

            {/* Products */}
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600"></div>
              </div>
            ) : products.length > 0 ? (
              <>
                <div
                  className={
                    viewMode === 'grid'
                      ? 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-8'
                      : 'space-y-4 mb-8'
                  }
                >
                  {products.map((product) => {
                    // Используем price и currency из API (они уже в правильной валюте)
                    const displayPrice = product.price
                    const displayCurrency = product.currency
                    const displayOldPrice = product.old_price ? String(product.old_price) : null
                    const productHref = `/product/${categoryType}/${product.slug}`
                    const isBaseProductType = ['medicines', 'supplements', 'medical-equipment'].includes(categoryType)
                    
                    return (
                      <ProductCard
                        key={product.id}
                        id={product.id}
                        name={product.name}
                        slug={product.slug}
                        price={displayPrice ? String(displayPrice) : null}
                        currency={displayCurrency}
                        oldPrice={displayOldPrice}
                        imageUrl={product.main_image_url || product.main_image}
                        videoUrl={product.video_url}
                        badge={product.is_featured ? 'Хит' : null}
                        viewMode={viewMode}
                        description={product.description}
                        href={productHref}
                        productType={categoryType}
                        isBaseProduct={isBaseProductType}
                      />
                    )
                  })}
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <Pagination
                    currentPage={currentPage}
                    totalPages={totalPages}
                    onPageChange={handlePageChange}
                  />
                )}
              </>
            ) : (
              <div className="text-center py-20">
                <div className="text-6xl mb-4">😔</div>
                <h3 className="text-2xl font-semibold text-main mb-2">
                  {t('products_not_found', 'Товары не найдены')}
                </h3>
                <p className="text-main/80 mb-6">
                  {t('products_not_found_description', 'Попробуйте изменить параметры фильтров или выберите другую категорию')}
                </p>
                <button
                  onClick={() => {
                    setFilters({
                      categories: [],
                      categorySlugs: [],
                      brands: [],
                      brandSlugs: [],
                      subcategories: [],
                      subcategorySlugs: [],
                      inStock: false,
                      sortBy: 'name_asc'
                    })
                    setCurrentPage(1)
                  }}
                  className="px-6 py-3 bg-accent text-white rounded-lg hover:bg-[var(--accent-strong)] transition-colors"
                >
                  {t('reset_filters', 'Сбросить фильтры')}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

// Сохраняем оригинальную getServerSideProps для совместимости
export const getServerSideProps: GetServerSideProps = async (context) => {
  const { slug, page = 1, brand, brand_id } = context.query
  const pageSize = 12

  try {
    const routeSlug = Array.isArray(slug) ? slug[0] : (slug as string | undefined)
    
    // Используем относительный путь, который работает через Next.js rewrites
    const base = process.env.INTERNAL_API_BASE || ''
    
    // Получаем категорию из API чтобы узнать её реальный тип
    let categoryTypeFromApi: string | null = null
    if (routeSlug) {
      try {
        const catApiRes = await axios.get(`${base}/api/catalog/categories`, {
          params: { slug: routeSlug, page_size: 1 }
        })
        const catData = catApiRes.data.results?.[0]
        if (catData?.category_type_slug) {
          categoryTypeFromApi = catData.category_type_slug.replace(/_/g, '-')
        }
      } catch {
        // ignore
      }
    }
    
    // Используем тип из API, если есть, иначе угадываем из слага
    let categoryType: CategoryTypeKey = categoryTypeFromApi as CategoryTypeKey || resolveCategoryTypeFromSlug(routeSlug)

    const brandSlug = Array.isArray(brand) ? brand[0] : brand
    const brandId = Array.isArray(brand_id) ? brand_id[0] : brand_id
    
    // Используем реальный тип из API для запросов, иначе fallback
    const brandProductType = categoryTypeFromApi || resolveBrandProductType(categoryType)

    // --- Бренды ---
    let brands: any[] = []
    try {
      const primarySlug = routeSlug ? routeSlug.replace(/_/g, '-') : undefined
      const brandParams: any = { page_size: 500 }
      if (primarySlug) {
        brandParams.primary_category_slug = primarySlug
      }
      // Всегда добавляем product_type для более точной фильтрации
      brandParams.product_type = brandProductType
      
      const brandRes = await axios.get(`${base}/api/catalog/brands`, { params: brandParams })
      brands = brandRes.data.results || []
    } catch {
      brands = []
    }

    // --- Товары: всегда общий эндпоинт, чтобы не получать 404 для кастомных категорий ---
    const productParams: any = { page, page_size: pageSize }
    if (routeSlug) {
      // Для книг используем product_type чтобы показать все книги из всех жанров
      if (categoryType === 'books') {
        productParams.product_type = 'books'
      } else {
        productParams.category_slug = routeSlug
      }
    }
    if (brandId) {
      productParams.brand_id = brandId
    } else if (brandSlug) {
      const selectedBrand = brands.find((b: any) => b.slug === brandSlug)
      if (selectedBrand) {
        productParams.brand_id = selectedBrand.id
      }
    }

    let productsData: any = { results: [], count: 0 }
    try {
      const prodRes = await axios.get(`${base}/api/catalog/products`, { params: productParams })
      productsData = prodRes.data || {}
    } catch {
      productsData = { results: [], count: 0 }
    }

    const products = Array.isArray(productsData) ? productsData : (productsData.results || [])
    const totalCount = productsData.count || products.length

    // --- Категории: фильтрованные на бэке ---
    let categories: any[] = []
    let subcategories: any[] = []
    try {
      const catParams: any = {}
      if (routeSlug) {
        catParams.slug = routeSlug
        catParams.include_children = true
      } else {
        catParams.top_level = true
      }
      catParams.page_size = 200
      const catRes = await axios.get(`${base}/api/catalog/categories`, { params: catParams })
      categories = catRes.data.results || []
    } catch {
      categories = []
    }

    // Если детей не вернулось, пытаемся догрузить по parent_slug
    if (routeSlug) {
      const hasChildren = categories.some((c: any) => c.parent !== null && typeof c.parent !== 'undefined')
      if (!hasChildren) {
        try {
          const childRes = await axios.get(`${base}/api/catalog/categories`, {
            params: { parent_slug: routeSlug, page_size: 200 }
          })
          const childList = childRes.data.results || []
          if (childList.length) {
            categories = [...categories, ...childList]
          }
        } catch {
          // ignore
        }
      }
    }

    // Оставляем только текущую категорию и её дочерние, чтобы сайтбар не засорялся
    const routeNorm = routeSlug ? routeSlug.toLowerCase().replace(/_/g, '-') : ''
    const mainCat = categories.find((c: any) => (c.slug || '').toLowerCase().replace(/_/g, '-') === routeNorm)
    let sidebarCategories: any[] = categories
    if (mainCat) {
      const childCats = categories.filter((c: any) => c.parent === mainCat.id)
      sidebarCategories = [mainCat]
      subcategories = childCats
    } else if (routeNorm) {
      sidebarCategories = categories.filter((c: any) => (c.slug || '').toLowerCase().replace(/_/g, '-') === routeNorm)
    }
    // Перезаписываем categories отфильтрованным набором, чтобы на клиенте не было лишних категорий
    categories = sidebarCategories

    // --- Фильтр брендов ---
    brands = filterBrandsByProducts(brands, products, categoryType, routeSlug)

    // Локализация названий категорий
    const getCategoryNames = (locale: string = 'ru'): Record<string, { name: string; description: string }> => {
      if (locale === 'en') {
        return {
          medicines: { name: 'Medicines', description: 'Medicinal preparations and medicines from Turkey' },
          supplements: { name: 'Supplements', description: 'Dietary supplements' },
          clothing: { name: 'Clothing', description: 'Fashionable clothing for the whole family from Turkey' },
          shoes: { name: 'Shoes', description: 'Quality footwear for the whole family' },
          electronics: { name: 'Electronics', description: 'Modern gadgets and technology' },
          tableware: { name: 'Tableware', description: 'Kitchenware and accessories' },
          furniture: { name: 'Furniture', description: 'Furniture for home and office' },
          accessories: { name: 'Accessories', description: 'Bags, belts, wallets and other accessories' },
          jewelry: { name: 'Jewelry', description: 'Jewelry and costume jewelry from Turkey' },
          underwear: { name: 'Underwear', description: 'Basic and everyday underwear' },
          headwear: { name: 'Headwear', description: 'Caps, hats and other headwear' },
          'medical-equipment': { name: 'Medical Equipment', description: 'Medical tools and equipment' },
          uslugi: { name: 'Services', description: 'Services and consultations' }
        }
      }
      return {
        medicines: { name: 'Медикаменты', description: 'Лекарственные препараты и медикаменты из Турции' },
        supplements: { name: 'БАДы', description: 'Биологически активные добавки' },
        clothing: { name: 'Одежда', description: 'Модная одежда для всей семьи из Турции' },
        shoes: { name: 'Обувь', description: 'Качественная обувь для всей семьи' },
        electronics: { name: 'Электроника', description: 'Современные гаджеты и техника' },
        tableware: { name: 'Посуда', description: 'Кухонная посуда и аксессуары' },
        furniture: { name: 'Мебель', description: 'Мебель для дома и офиса' },
        accessories: { name: 'Аксессуары', description: 'Сумки, ремни, кошельки и другие аксессуары' },
        jewelry: { name: 'Украшения', description: 'Украшения и бижутерия из Турции' },
        underwear: { name: 'Нижнее бельё', description: 'Базовое и повседневное нижнее бельё' },
        headwear: { name: 'Головные уборы', description: 'Кепки, шапки и другие головные уборы' },
        'medical-equipment': { name: 'Медицинский инвентарь', description: 'Инструменты и оборудование для медицины' },
        uslugi: { name: 'Услуги', description: 'Услуги и консультации' }
      }
    }

    const categoryNames = getCategoryNames(context.locale)
    const fallbackName = context.locale === 'en' ? 'Products' : 'Товары'
    const fallbackInfo =
      (mainCat && { name: mainCat.name, description: mainCat.description || '' }) ||
      { name: fallbackName, description: '' }
    const categoryInfo = categoryNames[categoryType] || fallbackInfo

    // Заменяем categories на уже отфильтрованный список для сайтбара,
    // чтобы на клиенте не пришёл полный набор и не затёр отображение.
    categories = sidebarCategories

    return {
      props: {
        products,
        categories,
        sidebarCategories,
        brands,
        subcategories,
        categoryName: categoryInfo.name,
        categoryDescription: categoryInfo.description,
        totalCount,
        currentPage: Number(page),
        totalPages: Math.ceil(totalCount / pageSize),
        categoryType,
        categoryTypeSlug: categoryTypeFromApi || null,
        initialRouteSlug: routeSlug || '',
        ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
      },
    }
  } catch (error) {
    console.error('Error fetching data:', error)
    
    return {
      props: {
        products: [],
        categories: [],
        sidebarCategories: [],
        brands: [],
        subcategories: [],
        categoryName: context.locale === 'en' ? 'Products' : 'Товары',
        categoryDescription: '',
        totalCount: 0,
        currentPage: 1,
        totalPages: 1,
        categoryType: 'medicines',
        categoryTypeSlug: null,
        initialRouteSlug: '',
        ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
      },
    }
  }
}

