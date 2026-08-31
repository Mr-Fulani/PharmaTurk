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

// Server-only consumers import this module from getServerSideProps. Stable public
// dictionaries are shared between warm SSR requests; product prices and stock are
// intentionally never stored here.
export const publicServerCache = createPromiseTtlCache()
