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

// Хвостовые служебные слова, на которых нельзя обрывать укороченное описание
const DANGLING_WORDS = new Set(['и', 'в', 'во', 'на', 'с', 'со', 'для', 'из', 'от', 'до', 'по', 'к', 'о', 'об', 'у', 'за', 'без', 'and', 'for', 'with', 'of', 'the', 'a', 'an', 'in', 'on', 'to', 'from', 'by'])

// Предлог, союз, знак препинания или притяжательное «Men's» — после них нужно слово
const isDanglingWord = (word) =>
  DANGLING_WORDS.has(word.toLowerCase()) || /^[,;:.–—-]+$/.test(word) || /['’]s$/i.test(word)

/**
 * Единый title карточки товара (ТЗ «SEO и видимость в ИИ-поиске», задача 6):
 * «… из Турции | Mudaroba» / «… from Turkey | Mudaroba».
 * - title с названием сайта не меняется (шаблон «Название | Категория | Mudaroba»);
 * - «из Турции» не дописывается, если Турция уже упомянута;
 * - слова из title не убираются, пока всё укладывается в max (80, DEVELOPMENT_RULES §1.10):
 *   у большинства карточек уже «— купить с доставкой из Турции», и срезать их до ~65 символов
 *   значило бы терять запросы; длиннее — укорачивается описательная часть после « - » / « — »,
 *   а не название, затем title без «из Турции», и только потом limitTitle.
 */
export function withProductTitleSuffix(title, { fromTurkey, siteName, max = 80 }) {
  const clean = String(title || '').replace(/\s+/g, ' ').trim()
  if (!clean || clean.toLowerCase().includes(String(siteName).toLowerCase())) return clean
  const brand = `${TITLE_SEPARATOR}${siteName}`
  const build = (text, withTurkey = true) =>
    `${text}${withTurkey && !/турц|turk|türk/i.test(text) ? ` ${fromTurkey}` : ''}${brand}`
  if (build(clean).length <= max) return build(clean)

  const parts = clean.match(/^(.+?)(\s[-–—]\s)(.+)$/)
  if (parts) {
    const [, name, separator, description] = parts
    const words = description.split(' ')
    while (words.length > 0) {
      words.pop()
      while (words.length > 0 && isDanglingWord(words[words.length - 1])) words.pop()
      // Одно оставшееся слово («Stylish», «купить») смысла не несёт — описание убираем целиком
      const shortened = words.length > 1 ? `${name}${separator}${words.join(' ').replace(/[\s,;:]+$/, '')}` : name
      if (build(shortened).length <= max) return build(shortened)
    }
  }
  if (build(clean, false).length <= max) return build(clean, false)
  return `${limitTitle(clean, max - brand.length)}${brand}`
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
 * alt фото товара: название на языке страницы, со второго кадра — «фото N».
 * Сохранённый alt_text собран при загрузке из исходного (турецкого) названия —
 * только запасной вариант, когда названия нет.
 */
export function productImageAlt({ name, storedAlt, index = 0, photoLabel = 'фото' }) {
  const base = String(name || '').trim()
  if (!base) return String(storedAlt || '').trim()
  return index > 0 ? `${base} — ${photoLabel} ${index + 1}` : base
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
