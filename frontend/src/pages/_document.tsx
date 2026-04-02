import Document, { Html, Head, Main, NextScript, DocumentContext, DocumentInitialProps } from 'next/document'

const GTM_ID = process.env.NEXT_PUBLIC_GTM_ID
const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || 'https://mudaroba.com').replace(/\/$/, '')

interface MyDocumentProps extends DocumentInitialProps {
  locale?: string
  path?: string
}

class MyDocument extends Document<MyDocumentProps> {
  static async getInitialProps(ctx: DocumentContext): Promise<MyDocumentProps> {
    const initialProps = await Document.getInitialProps(ctx)
    const locale = ctx.locale || 'en'
    // Получаем путь без локального префикса для hreflang
    const rawPath = ctx.asPath || '/'
    // Убираем query-string для canonical
    const path = rawPath.split('?')[0]
    return { ...initialProps, locale, path }
  }

  render() {
    const siteName = process.env.NEXT_PUBLIC_SITE_NAME || 'Mudaroba'
    const { locale = 'en', path = '/' } = this.props

    // Строим hreflang URL
    // ru-вариант всегда /ru/... , en-вариант — без префикса
    const cleanPath = path.replace(/^\/(ru|en)/, '') || '/'
    const ruUrl = `${SITE_URL}/ru${cleanPath === '/' ? '' : cleanPath}`
    const enUrl = `${SITE_URL}${cleanPath === '/' ? '' : cleanPath}`

    return (
      <Html lang={locale}>
        <Head>
          <meta charSet="utf-8" />

          {/* Preconnect для критических ресурсов */}
          <link rel="preconnect" href="https://fonts.googleapis.com" />
          <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
          <link rel="preconnect" href="https://img.youtube.com" />
          {/* DNS prefetch для некритических ресурсов */}
          <link rel="dns-prefetch" href="https://i.pinimg.com" />
          <link rel="dns-prefetch" href="https://www.youtube-nocookie.com" />
          {/* Monoton шрифт: загрузка без блокировки рендера */}
          <link
            rel="preload"
            as="style"
            href="https://fonts.googleapis.com/css2?family=Monoton&display=swap"
            // @ts-ignore
            onLoad="this.onload=null;this.rel='stylesheet'"
          />
          <noscript>
            <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Monoton&display=swap" />
          </noscript>

          {/* Базовые мета-теги */}
          <meta name="theme-color" content="#4c1d95" />
          <meta name="application-name" content={siteName} />
          <meta property="og:site_name" content={siteName} />
          <meta property="og:type" content="website" />
          <meta property="og:url" content={locale === 'ru' ? ruUrl : enUrl} />
          <meta property="twitter:card" content="summary_large_image" />

          {/* ─── SEO: hreflang (мультиязычность) ─────────────────────────── */}
          <link rel="alternate" hrefLang="ru" href={ruUrl} />
          <link rel="alternate" hrefLang="en" href={enUrl} />
          {/* x-default указывает на основной язык (en без префикса) */}
          <link rel="alternate" hrefLang="x-default" href={enUrl} />

          {/* ─── Google Tag Manager (загружается только при наличии ID) ──── */}
          {GTM_ID && (
            <script
              id="gtm-init"
              dangerouslySetInnerHTML={{
                __html: `
(function(w,d,s,l,i){
  w[l]=w[l]||[];
  w[l].push({'gtm.start': new Date().getTime(), event:'gtm.js'});
  var f=d.getElementsByTagName(s)[0],
      j=d.createElement(s),
      dl=l!='dataLayer'?'&l='+l:'';
  j.async=true;
  j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;
  f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','${GTM_ID}');
`.trim(),
              }}
            />
          )}
        </Head>
        <body>
          {/* GTM noscript — фоллбэк для браузеров без JS */}
          {GTM_ID && (
            <noscript>
              <iframe
                src={`https://www.googletagmanager.com/ns.html?id=${GTM_ID}`}
                height="0"
                width="0"
                style={{ display: 'none', visibility: 'hidden' }}
                title="GTM noscript"
              />
            </noscript>
          )}
          <Main />
          <NextScript />
        </body>
      </Html>
    )
  }
}

export default MyDocument
