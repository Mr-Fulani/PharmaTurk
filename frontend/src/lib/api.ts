import axios, {
  type AxiosRequestConfig,
  type AxiosRequestHeaders,
  type AxiosResponse,
} from 'axios'
import Cookies from 'js-cookie'
import { getClientApiBase } from './urls'
import { defaultCurrencyForLocale, resolveRequestCurrency } from './requestCurrency'

// Создаем axios instance с базовым URL
// На клиенте URL определяется динамически через interceptor (getClientApiBase)
// withCredentials: HttpOnly cookie refresh_token (TD-018) ставит и читает backend;
// в проде API на том же домене, флаг нужен для dev (:3001 → :8000).
const api = axios.create({
  baseURL: typeof window !== 'undefined' ? getClientApiBase() : '/api',
  withCredentials: true,
})

const inFlightGetRequests = new Map<string, Promise<AxiosResponse<unknown>>>()

function stableRequestKey(value: unknown): string {
  if (typeof value === 'undefined') {
    return 'undefined'
  }
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value) as string
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableRequestKey).join(',')}]`
  }
  return `{${Object.keys(value as Record<string, unknown>)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableRequestKey((value as Record<string, unknown>)[key])}`)
    .join(',')}}`
}

function requestScopeFingerprint(value: string | undefined): string {
  if (!value) return ''
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(36)
}

/**
 * Объединяет только одновременно выполняющиеся одинаковые GET-запросы в браузере.
 * Результат не кэшируется: после завершения следующий вызов снова обращается к API.
 * Это сохраняет актуальность корзины/профиля и устраняет двойные эффекты React Strict Mode.
 */
/**
 * Язык открытой страницы — по URL (ru без префикса, en на /en). Cookie NEXT_LOCALE не
 * годится: она остаётся от прошлого переключения, и русская страница получала английские
 * данные (отзывы, названия). На сервере — ru: SSR передаёт язык явно.
 */
function pageLocale(): string {
  if (typeof window === 'undefined') return 'ru'
  const path = window.location.pathname
  return path === '/en' || path.startsWith('/en/') ? 'en' : 'ru'
}

export function getSingleFlight<T = any>(
  url: string,
  config?: AxiosRequestConfig
): Promise<AxiosResponse<T>> {
  if (typeof window === 'undefined' || config?.signal || config?.cancelToken) {
    return api.get<T>(url, config)
  }

  const key = stableRequestKey({
    url,
    params: config?.params || null,
    // Заголовки могут содержать переданный вручную Authorization. Для ключа
    // достаточно отпечатка: сырой токен не должен даже временно жить в Map.
    headers: requestScopeFingerprint(stableRequestKey(config?.headers || null)),
    responseType: config?.responseType || 'json',
    language: pageLocale(),
    currency: Cookies.get('currency') || preferredCurrency || defaultCurrencyForLocale(pageLocale()),
    // Интерцептор в любом случае создаёт cookie для анонимного запроса.
    // Делаем это до построения ключа, чтобы два самых первых GET тоже совпали.
    cartSession: requestScopeFingerprint(Cookies.get('cart_session') || ensureCartSession()),
    access: requestScopeFingerprint(Cookies.get('access')),
  })
  const existing = inFlightGetRequests.get(key)
  if (existing) {
    return existing as Promise<AxiosResponse<T>>
  }

  const request = api.get<T>(url, config)
  inFlightGetRequests.set(key, request as Promise<AxiosResponse<unknown>>)
  const clear = () => {
    if (inFlightGetRequests.get(key) === request) {
      inFlightGetRequests.delete(key)
    }
  }
  request.then(clear, clear)
  return request
}

// Проставляем идентификатор корзины (сохраняем в cookie)
// Инициализация/получение идентификатора сессии корзины в cookie (доступен на всем сайте)
function ensureCartSession() {
  let sid = Cookies.get('cart_session')
  if (!sid) {
    sid = cryptoRandom()
    Cookies.set('cart_session', sid, { sameSite: 'Lax', path: '/' })
  }
  return sid
}

// Публичная функция для явной инициализации cookie до первых запросов
export function initCartSession(): string {
  return ensureCartSession()
}

let preferredCurrency: string | null = null

export function setPreferredCurrency(currency: string | null) {
  preferredCurrency = currency
}

function cryptoRandom() {
  try {
    const arr = new Uint8Array(16)
    if (typeof window !== 'undefined' && window.crypto) {
      window.crypto.getRandomValues(arr)
    } else {
      for (let i = 0; i < arr.length; i++) arr[i] = Math.floor(Math.random() * 256)
    }
    return Array.from(arr).map((b) => b.toString(16).padStart(2, '0')).join('')
  } catch {
    return String(Date.now())
  }
}

api.interceptors.request.use((config) => {
  // Обновляем baseURL на клиенте при каждом запросе (для работы на мобильных устройствах)
  if (typeof window !== 'undefined') {
    const apiBase = getClientApiBase()
    if (apiBase && config.baseURL !== apiBase) {
      config.baseURL = apiBase
    }
    // ngrok free tier: без этого заголовка возвращает HTML-страницу предупреждения вместо API-ответа
    if (window.location.origin.includes('ngrok-free.dev') || window.location.origin.includes('ngrok.io')) {
      if (!config.headers) config.headers = {} as AxiosRequestHeaders
        ; (config.headers as AxiosRequestHeaders)['ngrok-skip-browser-warning'] = '1'
    }
    // Диагностика: раскомментировать при проблемах с API на мобильных/ngrok
    // console.log('[API Request]', { url: config.url, baseURL: config.baseURL, origin: window.location.origin })
  }

  const access = Cookies.get('access')
  if (!config.headers) config.headers = {} as AxiosRequestHeaders

  if (access) {
    ; (config.headers as AxiosRequestHeaders)['Authorization'] = `Bearer ${access}`
    if (process.env.NODE_ENV === 'development') {
      console.log('API: adding auth header for', config.url)
    }

    // Для авторизованных пользователей отправляем cart_session для возможного переноса корзины/избранного
    // но только если это запрос к корзине или избранному
    if (config.url?.includes('/orders/cart') || config.url?.includes('/catalog/favorites')) {
      const cartSid = Cookies.get('cart_session')
      if (cartSid) {
        ; (config.headers as AxiosRequestHeaders)['X-Cart-Session'] = cartSid
      }
    }
  } else {
    if (process.env.NODE_ENV === 'development') {
      console.log('API: no auth token for', config.url)
    }
    // Прокидываем X-Cart-Session для анонимных пользователей
    const cartSid = ensureCartSession()
      ; (config.headers as AxiosRequestHeaders)['X-Cart-Session'] = cartSid
  }

  // Прокидываем язык для локализации ответов DRF/Django — язык открытой страницы
  const locale = pageLocale()
    ; (config.headers as AxiosRequestHeaders)['Accept-Language'] = locale
    ; (config.headers as AxiosRequestHeaders)['X-Language'] = locale

  const storedCurrency = Cookies.get('currency')
  // явный X-Currency запроса -> cookie -> preferredCurrency -> валюта языка страницы (lang = локаль из URL)
  const resolvedCurrency = resolveRequestCurrency({
    explicit: (config.headers as AxiosRequestHeaders)['X-Currency'],
    stored: storedCurrency,
    preferred: preferredCurrency,
    locale,
  })
  if (process.env.NODE_ENV === 'development') {
    console.log('[API Currency]', { storedCurrency, preferredCurrency, resolvedCurrency, url: config.url })
  }
  if (resolvedCurrency) {
    ; (config.headers as AxiosRequestHeaders)['X-Currency'] = resolvedCurrency
  }
  return config
})

let refreshPromise: Promise<string | null> | null = null

// До TD-018 фронт хранил refresh в обычной cookie `refresh`. Её читаем только чтобы
// один раз отдать backend: он перекладывает сессию в HttpOnly cookie, а эту мы удаляем.
const LEGACY_REFRESH_COOKIE = 'refresh'

async function refreshAccessToken(baseURL?: string): Promise<string | null> {
  const legacyRefresh = Cookies.get(LEGACY_REFRESH_COOKIE)
  // Без access сессии нет (cookie ставятся и живут вместе) — не дёргаем refresh
  // на каждый 401 анонима: эндпоинт ограничен по IP.
  if (!legacyRefresh && !Cookies.get('access')) return null

  // Use the global axios client deliberately. Sending refresh through `api`
  // would run this response interceptor again and can deadlock on an invalid
  // refresh token while waiting for its own in-flight refresh operation.
  const response = await axios.post(
    '/auth/jwt/refresh/',
    legacyRefresh ? { refresh: legacyRefresh } : {},
    {
      baseURL: baseURL || (typeof window !== 'undefined' ? getClientApiBase() : '/api'),
      withCredentials: true,
    },
  )
  if (legacyRefresh) Cookies.remove(LEGACY_REFRESH_COOKIE, { path: '/' })
  const newAccess = response.data?.access
  if (!newAccess) return null

  Cookies.set('access', newAccess, {
    sameSite: 'Lax' as const,
    path: '/',
    secure: process.env.NODE_ENV === 'production',
  })
  return newAccess
}

function refreshAccessTokenOnce(baseURL?: string): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = refreshAccessToken(baseURL).finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

/** Переносит сессию со старой JS-cookie refresh в HttpOnly; без неё ничего не делает. */
export async function migrateLegacyRefreshCookie(): Promise<void> {
  if (typeof window === 'undefined' || !Cookies.get(LEGACY_REFRESH_COOKIE)) return
  try {
    await refreshAccessTokenOnce()
  } catch {
    // Старый refresh просрочен: профиль ответит 401 и интерцептор мягко разлогинит.
    Cookies.remove(LEGACY_REFRESH_COOKIE, { path: '/' })
  }
}

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    // Production responses may contain validation details or personal data.
    // Keep full diagnostics local to development and log only operational
    // metadata in production.
    if (process.env.NODE_ENV === 'development') {
      console.error('[API Error]', {
        url: error.config?.url,
        baseURL: error.config?.baseURL,
        fullUrl: error.config ? `${error.config.baseURL}${error.config.url}` : 'unknown',
        status: error.response?.status,
        statusText: error.response?.statusText,
        message: error.message,
        code: error.code,
        responseData: error.response?.data,
        origin: typeof window !== 'undefined' ? window.location.origin : 'server',
        userAgent: typeof window !== 'undefined' ? navigator.userAgent : 'server',
      })
    } else {
      console.error('[API Error]', {
        url: error.config?.url,
        status: error.response?.status,
        code: error.code,
      })
    }

    const original = error.config
    const isRefreshRequest = original?.url?.includes('/auth/jwt/refresh/')
    if (error?.response?.status === 401 && original && !original._retry && !isRefreshRequest) {
      original._retry = true
      let access: string | null
      try {
        access = await refreshAccessTokenOnce(original.baseURL)
      } catch {
        access = null
      }
      if (!access) {
        Cookies.remove('access', { path: '/' })
        Cookies.remove(LEGACY_REFRESH_COOKIE, { path: '/' })
        return Promise.reject(error)
      }
      if (access) {
        if (!original.headers) original.headers = {} as AxiosRequestHeaders
        original.headers['Authorization'] = `Bearer ${access}`
      }
      return api(original)
    }
    return Promise.reject(error)
  }
)

// ============================================================================
// API ФУНКЦИИ ДЛЯ РАЗНЫХ КАТЕГОРИЙ ТОВАРОВ
// ============================================================================

// Основные товары (медикаменты)
export const medicinesApi = {
  getCategories: () => api.get('/catalog/categories'),
  getProducts: (params?: any) => api.get('/catalog/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/products/${slug}`),
  getBrands: () => api.get('/catalog/brands'),
}

// Одежда
export const clothingApi = {
  getCategories: (params?: any) => api.get('/catalog/clothing/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/clothing/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/clothing/products/${slug}`),
  getFeatured: () => api.get('/catalog/clothing/products/featured'),
}

// Обувь
export const shoesApi = {
  getCategories: (params?: any) => api.get('/catalog/shoes/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/shoes/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/shoes/products/${slug}`),
  getFeatured: () => api.get('/catalog/shoes/products/featured'),
}

// Электроника
export const electronicsApi = {
  getCategories: (params?: any) => api.get('/catalog/electronics/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/electronics/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/electronics/products/${slug}`),
  getFeatured: () => api.get('/catalog/electronics/products/featured'),
}

// Мебель
export const furnitureApi = {
  getCategories: (params?: any) => api.get('/catalog/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/furniture/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/furniture/products/${slug}`),
  getFeatured: () => api.get('/catalog/furniture/products/featured'),
}

// Ювелирные изделия
export const jewelryApi = {
  getCategories: (params?: any) => api.get('/catalog/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/jewelry/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/jewelry/products/${slug}`),
  getFeatured: () => api.get('/catalog/jewelry/products/featured'),
}

// Книги
export const booksApi = {
  getCategories: (params?: any) => api.get('/catalog/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/books/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/books/products/${slug}`),
  getFeatured: () => api.get('/catalog/books/products/featured'),
}

// Парфюмерия
export const perfumeryApi = {
  getCategories: (params?: any) => api.get('/catalog/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/perfumery/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/perfumery/products/${slug}`),
  getFeatured: () => api.get('/catalog/perfumery/products/featured'),
}

// Медикаменты (домен)
export const medicinesDomainApi = {
  getCategories: (params?: any) => api.get('/catalog/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/medicines/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/medicines/products/${slug}`),
  getFeatured: () => api.get('/catalog/medicines/products/featured'),
}

// БАДы
export const supplementsApi = {
  getCategories: (params?: any) => api.get('/catalog/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/supplements/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/supplements/products/${slug}`),
  getFeatured: () => api.get('/catalog/supplements/products/featured'),
}

// Медтехника
export const medicalEquipmentApi = {
  getCategories: (params?: any) => api.get('/catalog/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/medical-equipment/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/medical-equipment/products/${slug}`),
  getFeatured: () => api.get('/catalog/medical-equipment/products/featured'),
}

// Посуда
export const tablewareApi = {
  getCategories: (params?: any) => api.get('/catalog/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/tableware/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/tableware/products/${slug}`),
  getFeatured: () => api.get('/catalog/tableware/products/featured'),
}

// Аксессуары
export const accessoriesApi = {
  getCategories: (params?: any) => api.get('/catalog/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/accessories/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/accessories/products/${slug}`),
  getFeatured: () => api.get('/catalog/accessories/products/featured'),
}

// Благовония
export const incenseApi = {
  getCategories: (params?: any) => api.get('/catalog/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/incense/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/incense/products/${slug}`),
  getFeatured: () => api.get('/catalog/incense/products/featured'),
}

// Спорттовары
export const sportsApi = {
  getCategories: (params?: any) => api.get('/catalog/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/sports/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/sports/products/${slug}`),
  getFeatured: () => api.get('/catalog/sports/products/featured'),
}

// Автозапчасти
export const autoPartsApi = {
  getCategories: (params?: any) => api.get('/catalog/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/auto-parts/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/auto-parts/products/${slug}`),
  getFeatured: () => api.get('/catalog/auto-parts/products/featured'),
}

// Универсальная функция для получения API в зависимости от типа товаров.
// categoryType всегда приходит с дефисами (categoryTypeFromApi делает replace(/_/g, '-')).
export function getApiForCategory(
  categoryType: string
) {
  switch (categoryType) {
    case 'clothing': return clothingApi
    case 'shoes': return shoesApi
    case 'electronics': return electronicsApi
    case 'furniture': return furnitureApi
    case 'jewelry': return jewelryApi
    case 'books': return booksApi
    case 'perfumery': return perfumeryApi
    case 'medicines':
    case 'medicines-domain': return medicinesDomainApi
    case 'supplements': return supplementsApi
    case 'medical-equipment': return medicalEquipmentApi
    case 'tableware': return tablewareApi
    case 'accessories': return accessoriesApi
    case 'incense': return incenseApi
    case 'sports': return sportsApi
    case 'auto-parts': return autoPartsApi
    default: return medicinesApi
  }
}

export default api
