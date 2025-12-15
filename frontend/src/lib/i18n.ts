import { TFunction } from 'next-i18next'

/**
 * Интерфейс для перевода категории из API
 */
export interface CategoryTranslation {
  locale: string
  name: string
  description?: string
}

/**
 * Интерфейс для перевода бренда из API
 */
export interface BrandTranslation {
  locale: string
  name: string
  description?: string
}

/**
 * Интерфейс для перевода товара из API
 */
export interface ProductTranslation {
  locale: string
  description?: string
}

/**
 * Нормализует slug категории для использования в ключах локализации
 * Заменяет подчеркивания на дефисы и приводит к нижнему регистру
 */
export function normalizeCategorySlug(slug: string): string {
  return (slug || '').trim().toLowerCase().replace(/_/g, '-')
}

/**
 * Получает локализованное название категории
 * Приоритет: 1) JSON файлы, 2) API переводы, 3) fallback (название с бэкенда)
 * 
 * @param slug - slug категории
 * @param fallbackName - название с бэкенда (используется если перевода нет)
 * @param t - функция перевода из next-i18next
 * @param translations - переводы из API (опционально)
 * @param currentLocale - текущий язык (опционально, по умолчанию из t)
 * @returns локализованное название или fallback
 */
export function getLocalizedCategoryName(
  slug: string,
  fallbackName: string,
  t: TFunction,
  translations?: CategoryTranslation[],
  currentLocale?: string
): string {
  const normalizedSlug = normalizeCategorySlug(slug)
  // Получаем текущий язык из роутера или из пути
  let locale = currentLocale
  if (!locale && typeof window !== 'undefined') {
    const pathLocale = window.location.pathname.split('/')[1]
    locale = (pathLocale === 'ru' || pathLocale === 'en') ? pathLocale : 'ru'
  }
  locale = locale || 'ru'
  
  // 1. Сначала проверяем JSON файлы (быстро, кешируется)
  const jsonKey = `category_${normalizedSlug}_name`
  const jsonTranslated = t(jsonKey, { defaultValue: null })
  if (jsonTranslated && jsonTranslated !== jsonKey) {
    return jsonTranslated
  }
  
  // 2. Если нет в JSON - проверяем переводы из API
  if (translations && translations.length > 0) {
    const apiTranslation = translations.find(tr => tr.locale === locale || tr.locale === locale.split('-')[0])
    if (apiTranslation && apiTranslation.name) {
      return apiTranslation.name
    }
  }
  
  // 3. Fallback на название с бэкенда
  return fallbackName
}

/**
 * Получает локализованное описание категории
 * Приоритет: 1) JSON файлы, 2) API переводы, 3) fallback (описание с бэкенда)
 * 
 * @param slug - slug категории
 * @param fallbackDescription - описание с бэкенда (используется если перевода нет)
 * @param t - функция перевода из next-i18next
 * @param translations - переводы из API (опционально)
 * @param currentLocale - текущий язык (опционально, по умолчанию из t)
 * @returns локализованное описание или fallback
 */
export function getLocalizedCategoryDescription(
  slug: string,
  fallbackDescription: string | null | undefined,
  t: TFunction,
  translations?: CategoryTranslation[],
  currentLocale?: string
): string | null {
  if (!fallbackDescription) return null
  
  const normalizedSlug = normalizeCategorySlug(slug)
  // Получаем текущий язык из роутера или из пути
  let locale = currentLocale
  if (!locale && typeof window !== 'undefined') {
    const pathLocale = window.location.pathname.split('/')[1]
    locale = (pathLocale === 'ru' || pathLocale === 'en') ? pathLocale : 'ru'
  }
  locale = locale || 'ru'
  
  // 1. Сначала проверяем JSON файлы (быстро, кешируется)
  const jsonKey = `category_${normalizedSlug}_description`
  const jsonTranslated = t(jsonKey, { defaultValue: null })
  if (jsonTranslated && jsonTranslated !== jsonKey) {
    return jsonTranslated
  }
  
  // 2. Если нет в JSON - проверяем переводы из API
  if (translations && translations.length > 0) {
    const apiTranslation = translations.find(tr => tr.locale === locale || tr.locale === locale.split('-')[0])
    if (apiTranslation && apiTranslation.description) {
      return apiTranslation.description
    }
  }
  
  // 3. Fallback на описание с бэкенда
  return fallbackDescription
}

/**
 * Нормализует slug бренда для использования в ключах локализации
 * Заменяет подчеркивания на дефисы и приводит к нижнему регистру
 */
export function normalizeBrandSlug(slug: string): string {
  return (slug || '').trim().toLowerCase().replace(/_/g, '-')
}

/**
 * Получает локализованное название бренда
 * Приоритет: 1) JSON файлы, 2) API переводы, 3) fallback (название с бэкенда)
 * 
 * @param slug - slug бренда
 * @param fallbackName - название с бэкенда (используется если перевода нет)
 * @param t - функция перевода из next-i18next
 * @param translations - переводы из API (опционально)
 * @param currentLocale - текущий язык (опционально, по умолчанию из t)
 * @returns локализованное название или fallback
 */
export function getLocalizedBrandName(
  slug: string,
  fallbackName: string,
  t: TFunction,
  translations?: BrandTranslation[],
  currentLocale?: string
): string {
  const normalizedSlug = normalizeBrandSlug(slug)
  // Получаем текущий язык из роутера или из пути
  let locale = currentLocale
  if (!locale && typeof window !== 'undefined') {
    const pathLocale = window.location.pathname.split('/')[1]
    locale = (pathLocale === 'ru' || pathLocale === 'en') ? pathLocale : 'ru'
  }
  locale = locale || 'ru'
  
  // 1. Сначала проверяем JSON файлы (быстро, кешируется)
  const jsonKey = `brand_${normalizedSlug}_name`
  const jsonTranslated = t(jsonKey, { defaultValue: null })
  if (jsonTranslated && jsonTranslated !== jsonKey) {
    return jsonTranslated
  }
  
  // 2. Если нет в JSON - проверяем переводы из API
  if (translations && translations.length > 0) {
    const apiTranslation = translations.find(tr => tr.locale === locale || tr.locale === locale.split('-')[0])
    if (apiTranslation && apiTranslation.name) {
      return apiTranslation.name
    }
  }
  
  // 3. Fallback на название с бэкенда
  return fallbackName
}

/**
 * Получает локализованное описание бренда
 * Приоритет: 1) JSON файлы, 2) API переводы, 3) fallback (описание с бэкенда)
 * 
 * @param slug - slug бренда
 * @param fallbackDescription - описание с бэкенда (используется если перевода нет)
 * @param t - функция перевода из next-i18next
 * @param translations - переводы из API (опционально)
 * @param currentLocale - текущий язык (опционально, по умолчанию из t)
 * @returns локализованное описание или fallback
 */
export function getLocalizedBrandDescription(
  slug: string,
  fallbackDescription: string | null | undefined,
  t: TFunction,
  translations?: BrandTranslation[],
  currentLocale?: string
): string | null {
  if (!fallbackDescription) return null
  
  const normalizedSlug = normalizeBrandSlug(slug)
  // Получаем текущий язык из роутера или из пути
  let locale = currentLocale
  if (!locale && typeof window !== 'undefined') {
    const pathLocale = window.location.pathname.split('/')[1]
    locale = (pathLocale === 'ru' || pathLocale === 'en') ? pathLocale : 'ru'
  }
  locale = locale || 'ru'
  
  // 1. Сначала проверяем JSON файлы (быстро, кешируется)
  const jsonKey = `brand_${normalizedSlug}_description`
  const jsonTranslated = t(jsonKey, { defaultValue: null })
  if (jsonTranslated && jsonTranslated !== jsonKey) {
    return jsonTranslated
  }
  
  // 2. Если нет в JSON - проверяем переводы из API
  if (translations && translations.length > 0) {
    const apiTranslation = translations.find(tr => tr.locale === locale || tr.locale === locale.split('-')[0])
    if (apiTranslation && apiTranslation.description) {
      return apiTranslation.description
    }
  }
  
  // 3. Fallback на описание с бэкенда
  return fallbackDescription
}

/**
 * Нормализует название цвета для использования в ключах локализации
 * Приводит к нижнему регистру, заменяет пробелы и спецсимволы на подчеркивания
 */
export function normalizeColorName(color: string): string {
  return (color || '')
    .toLowerCase()
    .trim()
    .replace(/\s+/g, '_')
    .replace(/[^\wа-яё]/gi, '')
}

/**
 * Получает локализованное название цвета
 * Приоритет: 1) JSON файлы, 2) fallback (оригинальное название)
 * 
 * @param color - название цвета с бэкенда
 * @param t - функция перевода из next-i18next
 * @returns локализованное название или оригинальное
 */
export function getLocalizedColor(color: string, t: TFunction): string {
  if (!color) return color
  
  const normalizedColor = normalizeColorName(color)
  const jsonKey = `color_${normalizedColor}`
  const translated = t(jsonKey, { defaultValue: null })
  
  // Если перевод найден и отличается от ключа, возвращаем его
  if (translated && translated !== jsonKey) {
    return translated
  }
  
  // Иначе возвращаем оригинальное название
  return color
}

/**
 * Получает локализованное описание товара
 * Приоритет: 1) API переводы, 2) fallback (описание с бэкенда)
 * 
 * @param fallbackDescription - описание с бэкенда (используется если перевода нет)
 * @param t - функция перевода из next-i18next
 * @param translations - переводы из API (опционально)
 * @param currentLocale - текущий язык (опционально, по умолчанию из t)
 * @returns локализованное описание или fallback
 */
export function getLocalizedProductDescription(
  fallbackDescription: string | null | undefined,
  t: TFunction,
  translations?: ProductTranslation[],
  currentLocale?: string
): string {
  if (!fallbackDescription) return ''
  
  // Получаем текущий язык из роутера или из пути
  let locale = currentLocale
  if (!locale && typeof window !== 'undefined') {
    const pathLocale = window.location.pathname.split('/')[1]
    locale = (pathLocale === 'ru' || pathLocale === 'en') ? pathLocale : 'ru'
  }
  locale = locale || 'ru'
  
  // Проверяем переводы из API
  if (translations && translations.length > 0) {
    const apiTranslation = translations.find(tr => tr.locale === locale || tr.locale === locale.split('-')[0])
    if (apiTranslation && apiTranslation.description) {
      return apiTranslation.description
    }
  }
  
  // Fallback на описание с бэкенда
  return fallbackDescription
}
