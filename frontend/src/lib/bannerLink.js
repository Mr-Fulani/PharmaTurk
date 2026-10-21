/**
 * Ссылка кнопки баннера. В админке ссылка — полный URL (URLField), поэтому адрес
 * своего сайта превращаем во внутренний путь без префикса локали: роутер Next
 * откроет его в текущей языковой версии. Чужие домены остаются внешними.
 */
export function resolveBannerLink(url, siteHosts = []) {
  if (!/^https?:\/\//i.test(url)) return { internal: url }
  let parsed
  try {
    parsed = new URL(url)
  } catch {
    return { external: url }
  }
  const bare = (host) => String(host || '').toLowerCase().replace(/^www\./, '')
  if (!siteHosts.some((host) => host && bare(host) === bare(parsed.hostname))) return { external: url }
  const path = parsed.pathname.replace(/^\/(ru|en)(?=\/|$)/, '') || '/'
  return { internal: `${path}${parsed.search}${parsed.hash}` }
}
