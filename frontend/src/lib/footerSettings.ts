/**
 * Хелпер для загрузки настроек футера на сервере (SSR).
 * Используется в getServerSideProps — обходит CORS и работает локально и на продакшене.
 */
import axios from 'axios'
import { getInternalApiUrl } from './urls'

export interface FooterSettingsData {
  phone?: string
  email?: string
  location?: string
  telegram_url?: string
  whatsapp_url?: string
  vk_url?: string
  instagram_url?: string
  crypto_payment_text?: string
}

const DEFAULT_FOOTER: FooterSettingsData = {
  phone: '',
  email: '',
  location: '',
  telegram_url: '',
  whatsapp_url: '',
  vk_url: '',
  instagram_url: '',
  crypto_payment_text: '',
}

export async function fetchFooterSettings(): Promise<FooterSettingsData> {
  try {
    const res = await axios.get(getInternalApiUrl('settings/footer-settings'))
    const data = res.data || {}
    return {
      phone: data.phone ?? DEFAULT_FOOTER.phone,
      email: data.email ?? DEFAULT_FOOTER.email,
      location: data.location ?? DEFAULT_FOOTER.location,
      telegram_url: data.telegram_url ?? DEFAULT_FOOTER.telegram_url,
      whatsapp_url: data.whatsapp_url ?? DEFAULT_FOOTER.whatsapp_url,
      vk_url: data.vk_url ?? DEFAULT_FOOTER.vk_url,
      instagram_url: data.instagram_url ?? DEFAULT_FOOTER.instagram_url,
      crypto_payment_text: data.crypto_payment_text ?? DEFAULT_FOOTER.crypto_payment_text,
    }
  } catch {
    return { ...DEFAULT_FOOTER }
  }
}
