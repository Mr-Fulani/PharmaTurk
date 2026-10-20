import type { NextPageContext } from 'next'
import NextError, { type ErrorProps } from 'next/error'

// Свой _error только ради заголовка. gSSP ставит public, s-maxage=... до запросов
// к API; если затем gSSP бросает или падает рендер, Next отдаёт 500 с тем же
// заголовком, и Cloudflare кэширует ошибку. Ответ-ошибку в общий кэш не пускаем.
// notFound сюда не попадает (его рендерит 404.tsx) и сохраняет кэш страницы.
function ErrorPage(props: ErrorProps) {
  return <NextError {...props} />
}

ErrorPage.getInitialProps = (ctx: NextPageContext) => {
  ctx.res?.setHeader('Cache-Control', 'private, no-store')
  return NextError.getInitialProps(ctx)
}

export default ErrorPage
