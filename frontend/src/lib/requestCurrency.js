// Валюта запроса (X-Currency). Явно переданная в запросе валюта не перезаписывается:
// checkout отправляет заявку в той валюте, в которой показывал суммы клиенту, даже если
// cookie валюты успела смениться в фоне (например, после загрузки профиля).
export function resolveRequestCurrency({ explicit, stored, preferred }) {
  return explicit || stored || preferred || 'RUB'
}
