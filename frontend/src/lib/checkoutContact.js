// Имя и фамилия получателя и строка адреса для заявки (страница /checkout).
// Служба доставки оформляет отправление на имя и фамилию отдельно, поэтому в форме два поля;
// в сохранённых адресах профиля получатель записан одной строкой «Имя Фамилия».

export function splitFullName(fullName) {
  const words = String(fullName || '').trim().split(/\s+/).filter(Boolean)
  return { firstName: words[0] || '', lastName: words.slice(1).join(' ') }
}

// Полный адрес одной строкой — её видит менеджер в заявке и в уведомлении Telegram
export function formatAddressLine(address) {
  const a = address || {}
  const part = (value) => String(value || '').trim()
  return [
    part(a.country),
    part(a.region),
    part(a.postal_code),
    part(a.city),
    `${part(a.street)} ${part(a.house)}`.trim(),
    part(a.apartment) && `кв. ${part(a.apartment)}`,
    part(a.entrance) && `подъезд ${part(a.entrance)}`,
    part(a.floor) && `этаж ${part(a.floor)}`,
    part(a.intercom) && `домофон ${part(a.intercom)}`,
  ].filter(Boolean).join(', ')
}
