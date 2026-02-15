import axios, { type AxiosRequestHeaders } from 'axios'
import Cookies from 'js-cookie'
import { getClientApiBase } from './urls'

// Создаем axios instance с базовым URL
// На клиенте URL определяется динамически через interceptor (getClientApiBase)
const api = axios.create({
  baseURL: typeof window !== 'undefined' ? getClientApiBase() : '/api',
  withCredentials: false,
})

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
      ;(config.headers as AxiosRequestHeaders)['ngrok-skip-browser-warning'] = '1'
    }
    // Диагностика: раскомментировать при проблемах с API на мобильных/ngrok
    // console.log('[API Request]', { url: config.url, baseURL: config.baseURL, origin: window.location.origin })
  }
  
  const access = Cookies.get('access')
  if (!config.headers) config.headers = {} as AxiosRequestHeaders
  
  if (access) {
    ;(config.headers as AxiosRequestHeaders)['Authorization'] = `Bearer ${access}`
    if (process.env.NODE_ENV === 'development') {
      console.log('API: adding auth header for', config.url)
    }
    
    // Для авторизованных пользователей отправляем cart_session для возможного переноса корзины/избранного
    // но только если это запрос к корзине или избранному
    if (config.url?.includes('/orders/cart') || config.url?.includes('/catalog/favorites')) {
      const cartSid = Cookies.get('cart_session')
      if (cartSid) {
        ;(config.headers as AxiosRequestHeaders)['X-Cart-Session'] = cartSid
        if (process.env.NODE_ENV === 'development') {
          console.log('API: sending cart session for transfer:', cartSid)
        }
      }
    }
  } else {
    if (process.env.NODE_ENV === 'development') {
      console.log('API: no auth token for', config.url)
    }
    // Прокидываем X-Cart-Session для анонимных пользователей
    const cartSid = ensureCartSession()
    ;(config.headers as AxiosRequestHeaders)['X-Cart-Session'] = cartSid
  }
  
  // Прокидываем язык для локализации ответов DRF/Django
  const locale = Cookies.get('NEXT_LOCALE') || (typeof navigator !== 'undefined' ? (navigator.language?.split('-')[0] || 'en') : 'en')
  ;(config.headers as AxiosRequestHeaders)['Accept-Language'] = locale

  const storedCurrency = Cookies.get('currency')
  const resolvedCurrency = storedCurrency || preferredCurrency || (!access ? 'RUB' : null)
  if (process.env.NODE_ENV === 'development') {
    console.log('[API Currency]', { storedCurrency, preferredCurrency, resolvedCurrency, url: config.url })
  }
  if (resolvedCurrency) {
    ;(config.headers as AxiosRequestHeaders)['X-Currency'] = resolvedCurrency
  }
  return config
})

let isRefreshing = false
let queue: Array<() => void> = []

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    // ВСЕГДА логируем ошибки для диагностики на мобильных устройствах (даже в production)
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
      userAgent: typeof window !== 'undefined' ? navigator.userAgent : 'server'
    })
    
    const original = error.config
    if (error?.response?.status === 401 && !original._retry) {
      original._retry = true
      if (isRefreshing) {
        await new Promise<void>((resolve) => queue.push(resolve))
      } else {
        isRefreshing = true
        try {
          const refresh = Cookies.get('refresh')
          if (refresh) {
            const resp = await api.post('/auth/jwt/refresh/', { refresh })
            const newAccess = resp.data?.access
            if (newAccess) Cookies.set('access', newAccess, { sameSite: 'Lax', path: '/' })
            const newRefresh = resp.data?.refresh
            if (newRefresh) Cookies.set('refresh', newRefresh, { sameSite: 'Lax', path: '/' })
          }
        } finally {
          isRefreshing = false
          queue.forEach((fn) => fn())
          queue = []
        }
      }
      const access = Cookies.get('access')
      if (access) {
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

// Ювелирные изделия
export const jewelryApi = {
  getCategories: (params?: any) => api.get('/catalog/categories', { params }),
  getProducts: (params?: any) => api.get('/catalog/jewelry/products', { params }),
  getProduct: (slug: string) => api.get(`/catalog/jewelry/products/${slug}`),
  getFeatured: () => api.get('/catalog/jewelry/products/featured'),
}

// Универсальная функция для получения API в зависимости от типа товаров
export function getApiForCategory(
  categoryType: string
) {
  switch (categoryType) {
    case 'clothing':
      return clothingApi
    case 'shoes':
      return shoesApi
    case 'electronics':
      return electronicsApi
    case 'jewelry':
      return jewelryApi
    default:
      return medicinesApi
  }
}

export default api
