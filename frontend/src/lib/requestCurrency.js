// Валюта запроса (X-Currency). Явно переданная в запросе валюта не перезаписывается:
// checkout отправляет заявку в той валюте, в которой показывал суммы клиенту, даже если
// cookie валюты успела смениться в фоне (например, после загрузки профиля).
export function resolveRequestCurrency({ explicit, stored, preferred, locale }) {
  return explicit || stored || preferred || defaultCurrencyForLocale(locale)
}

// Валюта, пока посетитель её не выбрал: английская версия — для зарубежных клиентов
// (Google относит /en к США, правила доставки Merchant Center заданы в USD), русская — в рублях.
export function defaultCurrencyForLocale(locale) {
  return locale === 'en' ? 'USD' : 'RUB'
}
