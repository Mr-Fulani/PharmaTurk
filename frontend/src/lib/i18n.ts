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
  name?: string
  description?: string
  meta_title?: string
  meta_description?: string
  meta_keywords?: string
  og_title?: string
  og_description?: string
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
 */
export function getLocalizedCategoryName(
  slug: string,
  fallbackName: string,
  t: TFunction,
  translations?: CategoryTranslation[],
  currentLocale?: string
): string {
  const normalizedSlug = normalizeCategorySlug(slug)
  const locale = currentLocale || 'ru'

  // 1. Сначала проверяем переводы из API
  if (translations && translations.length > 0) {
    const apiTranslation = translations.find(tr => tr.locale === locale || tr.locale === locale.split('-')[0])
    if (apiTranslation && apiTranslation.name) {
      return apiTranslation.name
    }
  }

  // 2. Затем проверяем JSON файлы (специфичные для категорий)
  const jsonKey = `category_${normalizedSlug}_name`
  const jsonTranslated = t(jsonKey)
  if (jsonTranslated && jsonTranslated !== jsonKey) {
    return jsonTranslated
  }

  // 3. Fallback к фильтрам (часто они дублируют названия категорий)
  const filterKey = `filter_${normalizedSlug}`
  const filterTranslated = t(filterKey)
  if (filterTranslated && filterTranslated !== filterKey) {
    return filterTranslated
  }

  // 4. Fallback к значениям атрибутов (иногда слаги приходят на русском или совпадают с атрибутами)
  const attrKey = `attr_val_${normalizedSlug}`
  const attrTranslated = t(attrKey)
  if (attrTranslated && attrTranslated !== attrKey) {
    return attrTranslated
  }

  return fallbackName
}

/**
 * Получает локализованное описание категории
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
  const locale = currentLocale || 'ru'

  if (translations && translations.length > 0) {
    const apiTranslation = translations.find(tr => tr.locale === locale || tr.locale === locale.split('-')[0])
    if (apiTranslation && apiTranslation.description) {
      return apiTranslation.description
    }
  }

  const jsonKey = `category_${normalizedSlug}_description`
  const jsonTranslated = t(jsonKey)
  if (jsonTranslated && jsonTranslated !== jsonKey) {
    return jsonTranslated
  }

  return fallbackDescription
}

/**
 * Нормализует slug бренда для использования в ключах локализации
 */
export function normalizeBrandSlug(slug: string): string {
  return (slug || '').trim().toLowerCase().replace(/_/g, '-')
}

/**
 * Получает локализованное название бренда
 */
export function getLocalizedBrandName(
  slug: string,
  fallbackName: string,
  t: TFunction,
  translations?: BrandTranslation[],
  currentLocale?: string
): string {
  const normalizedSlug = normalizeBrandSlug(slug)
  const locale = currentLocale || 'ru'

  if (translations && translations.length > 0) {
    const apiTranslation = translations.find(tr => tr.locale === locale || tr.locale === locale.split('-')[0])
    if (apiTranslation && apiTranslation.name) {
      return apiTranslation.name
    }
  }

  const jsonKey = `brand_${normalizedSlug}_name`
  const jsonTranslated = t(jsonKey)
  if (jsonTranslated && jsonTranslated !== jsonKey) {
    return jsonTranslated
  }

  return fallbackName
}

/**
 * Получает локализованное описание бренда
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
  const locale = currentLocale || 'ru'

  if (translations && translations.length > 0) {
    const apiTranslation = translations.find(tr => tr.locale === locale || tr.locale === locale.split('-')[0])
    if (apiTranslation && apiTranslation.description) {
      return apiTranslation.description
    }
  }

  const jsonKey = `brand_${normalizedSlug}_description`
  const jsonTranslated = t(jsonKey)
  if (jsonTranslated && jsonTranslated !== jsonKey) {
    return jsonTranslated
  }

  return fallbackDescription
}

/**
 * Нормализует название цвета для использования в ключах локализации
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
 */
export function getLocalizedColor(color: string, t: TFunction): string {
  if (!color) return color

  const normalizedColor = normalizeColorName(color)
  const jsonKey = `color_${normalizedColor}`
  const translated = t(jsonKey)

  if (translated && translated !== jsonKey) {
    return translated
  }

  return color
}

/**
 * Нормализует значение обложки/формата для ключа локализации
 */
export function normalizeBookAttributeValue(value: string): string {
  return (value || '')
    .toLowerCase()
    .trim()
    .replace(/\s+/g, '_')
    .replace(/[^\wа-яёa-z0-9]/gi, '')
}

/**
 * Возвращает локализованное значение типа обложки (ru/en).
 */
export function getLocalizedCoverType(coverType: string | null | undefined, t: TFunction): string {
  if (!coverType) return ''
  const key = `cover_type_${normalizeBookAttributeValue(coverType)}`
  const translated = t(key)
  if (translated && translated !== key) return translated
  return coverType
}

export function getLocalizedProductName(
  fallbackName: string,
  t: TFunction,
  translations?: ProductTranslation[],
  currentLocale?: string
): string {
  if (!fallbackName) return ''
  const locale = currentLocale || 'ru'

  if (translations && translations.length > 0) {
    const apiTranslation = translations.find(tr => tr.locale === locale || tr.locale === locale.split('-')[0])
    if (apiTranslation && apiTranslation.name) {
      return apiTranslation.name
    }
  }

  return fallbackName
}

/**
 * Получает локализованное описание товара
 */
export function getLocalizedProductDescription(
  fallbackDescription: string | null | undefined,
  t: TFunction,
  translations?: ProductTranslation[],
  currentLocale?: string,
  fieldName: string = 'description'
): string {
  if (!fallbackDescription && !translations) return ''
  const locale = currentLocale || 'ru'

  if (translations && translations.length > 0) {
    const apiTranslation = translations.find(tr => tr.locale === locale || tr.locale === locale.split('-')[0])
    if (apiTranslation) {
      const val = (apiTranslation as any)[fieldName]
      if (val) return val
    }
  }

  return fallbackDescription || ''
}

/**
 * Удаляет HTML-теги из строки.
 * Полезно для подготовки текстов для SEO meta-тегов.
 */
export function stripHtml(html: string | null | undefined): string {
  if (!html) return ''
  return String(html)
    .replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}
