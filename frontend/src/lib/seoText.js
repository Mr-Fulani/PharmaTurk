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

const stripSentence = (value) => String(value || '').replace(/\s+/g, ' ').trim().replace(/[\s.!?…]+$/, '')

/**
 * Описание категории для поиска и превью: «{lead} — {count}: {подкатегории}. {base}. {tail}.»
 * Исходные описания категорий короткие («Кроссовки») и ничего не говорят — добавляем конкретику.
 * Развёрнутое ручное описание (от 120 символов) оставляем как есть; base, из-за которого
 * текст не влезает в maxLength, опускаем; итог обрезаем по слову.
 */
export function buildCategoryDescription({ base, lead, countText, subcategories = [], tail, maxLength = 160 }) {
  const cleanBase = stripSentence(base)
  if (cleanBase.length >= 120) return truncateAtWord(`${cleanBase}.`, maxLength)
  const subs = subcategories.map(stripSentence).filter(Boolean).slice(0, 3)
  const details = countText ? `${countText}${subs.length ? `: ${subs.join(', ')}` : ''}` : subs.join(', ')
  const head = [stripSentence(lead), details].filter(Boolean).join(' — ')
  const compose = (withBase) => [head, withBase ? cleanBase : '', stripSentence(tail)]
    .filter(Boolean)
    .map((sentence) => `${sentence}.`)
    .join(' ')
  const full = compose(true)
  return truncateAtWord(full.length <= maxLength ? full : compose(false), maxLength)
}

/**
 * SEO-текст посадочной страницы (поле seo_text из API) → блоки для вывода:
 * абзацы разделены пустой строкой, строка «## …» — подзаголовок. Текст обычный,
 * без HTML: React выводит его как текст, разметку из админки не исполняет.
 */
export function splitSeoText(text) {
  const blocks = []
  const chunks = String(text || '').replace(/\r\n?/g, '\n').split(/\n\s*\n/)
  for (const chunk of chunks) {
    let paragraph = []
    const flush = () => {
      if (paragraph.length) blocks.push({ kind: 'paragraph', text: paragraph.join(' ') })
      paragraph = []
    }
    for (const line of chunk.split('\n').map((value) => value.trim()).filter(Boolean)) {
      if (/^##(\s|$)/.test(line)) {
        flush()
        const heading = line.slice(2).trim()
        if (heading) blocks.push({ kind: 'heading', text: heading })
      } else {
        paragraph.push(line)
      }
    }
    flush()
  }
  return blocks
}
