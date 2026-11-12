/**
 * Тема оформления и блоки главной для SSR (_document и главная).
 * Настройка читается не чаще раза в минуту на процесс; при сбое бэкенда остаётся
 * последнее удачное значение — тема не «мигает» кремовой в закэшированных страницах.
 */
import axios from 'axios'
import { getInternalApiUrl } from './urls'
import { createStaleWhileRevalidateCache } from './serverPublicCache'
import { fallbackAppearance, normalizeAppearance } from './siteAppearance'
import type { SiteAppearance } from './siteAppearance'

const FRESH_MS = 60_000
const cache = createStaleWhileRevalidateCache({ freshMs: FRESH_MS })

async function loadSiteAppearance(): Promise<SiteAppearance> {
  const res = await axios.get(getInternalApiUrl('settings/appearance'), { timeout: 3000 })
  return normalizeAppearance(res.data)
}

export async function fetchSiteAppearance(): Promise<SiteAppearance> {
  try {
    return await cache.get('site-appearance', loadSiteAppearance)
  } catch {
    return fallbackAppearance()
  }
}
