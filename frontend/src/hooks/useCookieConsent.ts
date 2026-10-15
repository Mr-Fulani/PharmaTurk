import { useSyncExternalStore, useCallback } from 'react'
import { initDataLayer, gtmConsentGranted } from '../lib/gtm'
import { YM_ID } from '../lib/ym'

/**
 * Состояние cookie-согласия пользователя.
 * - null      : пользователь ещё не дал ответ (показывать баннер)
 * - 'accepted': согласие дано, аналитика включена
 * - 'rejected': только необходимые cookie, аналитика отключена
 */
export type ConsentStatus = 'accepted' | 'rejected' | null

const COOKIE_NAME = 'pharma_cookie_consent'
const ACCEPT_EXPIRES_DAYS = 365
const REJECT_EXPIRES_DAYS = 30

function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'))
  return match ? decodeURIComponent(match[1]) : null
}

function setCookie(name: string, value: string, days: number): void {
  if (typeof document === 'undefined') return
  const expires = new Date(Date.now() + days * 864e5).toUTCString()
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`
}

function deleteCookie(name: string): void {
  if (typeof document === 'undefined') return
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`
}

/**
 * Запускает GTM dataLayer и загружает скрипт Яндекс.Метрики.
 * Вызывается только при явном согласии.
 */
function activateAnalytics(): void {
  // Инициализируем GTM dataLayer
  initDataLayer()

  // Обновляем Consent Mode и пушим событие согласия для триггеров GTM
  gtmConsentGranted()
}

/**
 * Общее для всех компонентов состояние согласия: _app (загрузка счётчиков)
 * и CookieBanner должны видеть один и тот же статус, иначе после «Принять»
 * аналитика не стартует до перезагрузки страницы.
 */
type ConsentSnapshot = { consent: ConsentStatus; isLoaded: boolean }

const SERVER_SNAPSHOT: ConsentSnapshot = { consent: null, isLoaded: false }
let snapshot: ConsentSnapshot | null = null
const listeners = new Set<() => void>()

function getSnapshot(): ConsentSnapshot {
  if (snapshot === null) {
    const saved = getCookie(COOKIE_NAME)
    const consent: ConsentStatus = saved === 'accepted' || saved === 'rejected' ? saved : null
    snapshot = { consent, isLoaded: true }
    if (consent === 'accepted') {
      activateAnalytics()
    }
  }
  return snapshot
}

function getServerSnapshot(): ConsentSnapshot {
  return SERVER_SNAPSHOT
}

function setConsent(consent: ConsentStatus): void {
  snapshot = { consent, isLoaded: true }
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/**
 * Хук управления cookie-согласием.
 *
 * Возвращает:
 * - consent: текущий статус
 * - accept(): принять все cookie (аналитика включается)
 * - reject(): только необходимые cookie
 * - reset(): сбросить выбор (для страницы настроек)
 */
export function useCookieConsent() {
  const { consent, isLoaded } = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)

  const accept = useCallback(() => {
    setCookie(COOKIE_NAME, 'accepted', ACCEPT_EXPIRES_DAYS)
    setConsent('accepted')
    activateAnalytics()

    // Логируем согласие на бэкенде (GDPR аудит, fire-and-forget)
    fetch('/api/marketing/cookie-consent/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ consent: true }),
    }).catch(() => undefined)
  }, [])

  const reject = useCallback(() => {
    setCookie(COOKIE_NAME, 'rejected', REJECT_EXPIRES_DAYS)
    setConsent('rejected')

    // Логируем отказ на бэкенде (GDPR аудит, fire-and-forget)
    fetch('/api/marketing/cookie-consent/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ consent: false }),
    }).catch(() => undefined)
  }, [])

  const reset = useCallback(() => {
    deleteCookie(COOKIE_NAME)
    setConsent(null)
  }, [])

  return { consent, accept, reject, reset, isLoaded }
}
