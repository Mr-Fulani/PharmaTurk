import axios from 'axios'
import Cookies from 'js-cookie'

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE || '/api',
  withCredentials: false,
})

api.interceptors.request.use((config) => {
  const access = Cookies.get('access')
  if (access) {
    config.headers = config.headers || {}
    config.headers['Authorization'] = `Bearer ${access}`
  }
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
            if (newAccess) Cookies.set('access', newAccess, { sameSite: 'Lax' })
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
