const stableValue = (value) => {
  if (value === undefined) return 'undefined'
  if (value === null || typeof value !== 'object') return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(stableValue).join(',')}]`
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableValue(value[key])}`)
    .join(',')}}`
}

export function stablePublicCacheKey(namespace, value) {
  return `${namespace}:${stableValue(value)}`
}

export function createPromiseTtlCache({ maxEntries = 300, now = () => Date.now() } = {}) {
  const entries = new Map()

  const evictExpired = (timestamp) => {
    for (const [key, entry] of entries) {
      if (entry.expiresAt <= timestamp) entries.delete(key)
    }
  }

  return {
    async get(key, loader, ttlMs = 300_000) {
      const timestamp = now()
      const cached = entries.get(key)
      if (cached && cached.expiresAt > timestamp) return cached.promise
      if (cached) entries.delete(key)

      evictExpired(timestamp)
      while (entries.size >= maxEntries) {
        const oldestKey = entries.keys().next().value
        if (oldestKey === undefined) break
        entries.delete(oldestKey)
      }

      const promise = Promise.resolve().then(loader)
      const entry = {
        promise,
        expiresAt: timestamp + Math.max(0, Number(ttlMs) || 0),
      }
      entries.set(key, entry)
      try {
        return await promise
      } catch (error) {
        // A transient backend error must never poison the cache for the full TTL.
        if (entries.get(key) === entry) entries.delete(key)
        throw error
      }
    },
    clear() {
      entries.clear()
    },
  }
}

// Ждёт promise не дольше timeoutMs, затем отдаёт fallback. Сам promise не
// отменяется: если он лежит в publicServerCache, результат достанется следующему SSR.
export function settleWithin(promise, timeoutMs, fallback) {
  let timer
  const timeout = new Promise((resolve) => {
    timer = setTimeout(() => resolve(fallback), timeoutMs)
  })
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer))
}

// Кэш «отдай старое, обнови в фоне»: после первой сборки запрос никогда не ждёт
// загрузчик. Значения, отклонённые shouldStore (например, пустые), не сохраняются.
/** @param {{ freshMs: number, now?: () => number, shouldStore?: (value: any) => boolean }} options */
export function createStaleWhileRevalidateCache({ freshMs, now = () => Date.now(), shouldStore = (_value) => true }) {
  const entries = new Map()
  const inflight = new Map()

  const refresh = (key, loader) => {
    if (inflight.has(key)) return inflight.get(key)
    const promise = Promise.resolve()
      .then(loader)
      .then((value) => {
        if (shouldStore(value)) entries.set(key, { value, builtAt: now() })
        return value
      })
      .finally(() => inflight.delete(key))
    inflight.set(key, promise)
    return promise
  }

  return {
    async get(key, loader) {
      const entry = entries.get(key)
      if (!entry) return refresh(key, loader)
      if (now() - entry.builtAt >= freshMs) {
        refresh(key, loader).catch((error) => console.error(`Background refresh failed: ${key}`, error))
      }
      return entry.value
    },
  }
}

// Server-only consumers import this module from getServerSideProps. Stable public
// dictionaries are shared between warm SSR requests; product prices and stock are
// intentionally never stored here.
export const publicServerCache = createPromiseTtlCache()
