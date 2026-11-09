/**
 * Картинка-превью сайта по умолчанию (og:image, 1200×630, JPEG): русская — для ru, английская — для en.
 * Исходник и пересборка — docs/images/og-default/README.md.
 */
export function defaultOgImagePath(locale) {
  return locale === 'en' ? '/og-default-en.jpg' : '/og-default.jpg'
}

export function defaultOgImageAlt(locale) {
  return locale === 'en'
    ? 'Mudaroba: medicines, supplements and goods from Turkey delivered to Russia, the CIS and worldwide'
    : 'Mudaroba: лекарства, БАДы и товары из Турции с доставкой в Россию, СНГ и по всему миру'
}
