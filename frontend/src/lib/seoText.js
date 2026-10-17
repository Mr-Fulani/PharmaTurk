// Обрезка мета-текстов по границе слова: .slice(0, N) резал слово пополам.

const ELLIPSIS = '…'
const TITLE_SEPARATOR = ' | '

/** Сжимает пробелы и обрезает текст до maxLength символов (с «…») по последнему целому слову. */
export function truncateAtWord(text, maxLength) {
  const clean = String(text || '').replace(/\s+/g, ' ').trim()
  if (clean.length <= maxLength) return clean
  const limit = maxLength - ELLIPSIS.length
  // +1: если сразу за лимитом пробел, последнее слово целое
  const candidate = clean.slice(0, limit + 1)
  const lastSpace = candidate.lastIndexOf(' ')
  // Слово длиннее половины лимита (ссылка, склеенный текст) — режем жёстко
  const cut = lastSpace > limit / 2 ? candidate.slice(0, lastSpace) : clean.slice(0, limit)
  return `${cut.replace(/[\s.,;:!?\-–—|]+$/, '')}${ELLIPSIS}`
}

/**
 * Ограничивает title вида «Название | Категория | Сайт»: укорачивается только
 * первая часть (название), хвост с категорией и сайтом сохраняется.
 */
export function limitTitle(title, maxLength) {
  const clean = String(title || '').replace(/\s+/g, ' ').trim()
  if (clean.length <= maxLength) return clean
  const [head, ...tail] = clean.split(TITLE_SEPARATOR)
  const suffix = tail.length ? `${TITLE_SEPARATOR}${tail.join(TITLE_SEPARATOR)}` : ''
  if (maxLength - suffix.length < maxLength / 3) return truncateAtWord(clean, maxLength)
  return `${truncateAtWord(head, maxLength - suffix.length)}${suffix}`
}

/** Короткое описание (< minLength) дополняет шаблонной фразой отдельным предложением. */
export function appendSentenceIfShort(text, sentence, minLength = 70) {
  const clean = String(text || '').replace(/\s+/g, ' ').trim()
  if (clean.length >= minLength) return clean
  if (!clean) return sentence
  return `${clean.replace(/[\s.!?…]+$/, '')}. ${sentence}`
}
