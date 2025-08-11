import axios, { type AxiosRequestHeaders } from 'axios'
import Cookies from 'js-cookie'

// Базовый URL берём из NEXT_PUBLIC_API_BASE, иначе падаем на '/api' (чтоб работали старые бандлы)
const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE || '/api',
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
  const access = Cookies.get('access')
  if (access) {
    if (!config.headers) config.headers = {} as AxiosRequestHeaders
    ;(config.headers as AxiosRequestHeaders)['Authorization'] = `Bearer ${access}`
    console.log('API: adding auth header for', config.url)
  } else {
    console.log('API: no auth token for', config.url)
  }
  // Прокидываем X-Cart-Session для анонимной корзины
  const cartSid = ensureCartSession()
  if (!config.headers) config.headers = {} as AxiosRequestHeaders
  ;(config.headers as AxiosRequestHeaders)['X-Cart-Session'] = cartSid
  return config
})

let isRefreshing = false
let queue: Array<() => void> = []

api.interceptors.response.use(
  (r) => r,
  async (error) => {
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
            const resp = await axios.post((process.env.NEXT_PUBLIC_API_BASE || '/api') + '/auth/jwt/refresh/', { refresh })
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

export default api
