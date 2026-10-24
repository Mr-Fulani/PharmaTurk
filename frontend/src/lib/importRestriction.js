// Препараты, ввоз которых запрещён или ограничен (TD-024, docs/CONTROLLED_SUBSTANCES.md).
// API отдаёт коды стран (import_restricted_countries / product_import_restricted_countries).
const COUNTRY_ORDER = ['RU', 'KZ', 'UZ']
const COUNTRY_FALLBACK = { RU: 'Россию', KZ: 'Казахстан', UZ: 'Узбекистан' }

/** «Россию, Казахстан и Узбекистан» для «Ввоз в … ограничен»; '' — ограничений нет. */
export function formatRestrictedCountries(codes, t) {
  const names = COUNTRY_ORDER
    .filter((code) => Array.isArray(codes) && codes.includes(code))
    .map((code) => t(`import_restricted_country_${code}`, COUNTRY_FALLBACK[code]))
  if (names.length < 2) return names[0] || ''
  return `${names.slice(0, -1).join(', ')} ${t('and', 'и')} ${names[names.length - 1]}`
}
