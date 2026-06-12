import Document, { Html, Head, Main, NextScript, DocumentContext, DocumentInitialProps } from 'next/document'

const GTM_ID = process.env.NEXT_PUBLIC_GTM_ID

interface MyDocumentProps extends DocumentInitialProps {
  locale?: string
}

class MyDocument extends Document<MyDocumentProps> {
  static async getInitialProps(ctx: DocumentContext): Promise<MyDocumentProps> {
    const initialProps = await Document.getInitialProps(ctx)
    const locale = ctx.locale || 'ru'
    return { ...initialProps, locale }
  }

  render() {
    const siteName = process.env.NEXT_PUBLIC_SITE_NAME || 'Mudaroba'
    const { locale = 'ru' } = this.props

    return (
      <Html lang={locale}>
        <Head>
          <meta charSet="utf-8" />

          {/* DNS prefetch — дешёвый (только DNS, без TCP/TLS) */}
          <link rel="dns-prefetch" href="https://cdn.mudaroba.com" />
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

          {/* Базовые мета-теги. og:url/og:type/canonical/hreflang задаются постранично — здесь не дублировать */}
          <meta httpEquiv="Content-Language" content={locale} />
          <meta name="theme-color" content="#4c1d95" />
          <meta name="application-name" content={siteName} />
          <meta property="og:site_name" content={siteName} />
          <meta property="twitter:card" content="summary_large_image" />

          {/* ─── Yandex Webmaster (подтверждение прав) ────────────────────────── */}
          {process.env.NEXT_PUBLIC_YANDEX_VERIFICATION && (
            <meta name="yandex-verification" content={process.env.NEXT_PUBLIC_YANDEX_VERIFICATION} />
          )}

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
