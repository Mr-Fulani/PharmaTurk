import Document, { Html, Head, Main, NextScript, DocumentContext, DocumentInitialProps } from 'next/document'

const rawGtmId = process.env.NEXT_PUBLIC_GTM_ID || ''
const GTM_ID = /^GTM-[A-Z0-9]+$/i.test(rawGtmId) ? rawGtmId : ''

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

          {/* Базовые мета-теги. og:url/og:type/canonical/hreflang задаются постранично — здесь не дублировать */}
          <meta httpEquiv="Content-Language" content={locale} />
          <meta name="theme-color" content="#4c1d95" />
          <meta name="application-name" content={siteName} />
          <meta property="og:site_name" content={siteName} />
          <meta name="twitter:card" content="summary_large_image" />

          {/* ─── Yandex Webmaster (подтверждение прав) ────────────────────────── */}
          {process.env.NEXT_PUBLIC_YANDEX_VERIFICATION && (
            <meta name="yandex-verification" content={process.env.NEXT_PUBLIC_YANDEX_VERIFICATION} />
          )}

          {/* ─── Consent Mode: до ответа на cookie-баннер аналитика и реклама запрещены.
               Должно стоять ДО GTM; при сохранённом согласии сразу granted ──── */}
          {GTM_ID && (
            <script
              id="gtm-consent-default"
              dangerouslySetInnerHTML={{
                __html: `
(function(w,d){
  w.dataLayer=w.dataLayer||[];
  function gtag(){w.dataLayer.push(arguments);}
  var s=/(?:^|; )pharma_cookie_consent=accepted(?:;|$)/.test(d.cookie)?'granted':'denied';
  gtag('consent','default',{analytics_storage:s,ad_storage:s,ad_user_data:s,ad_personalization:s});
})(window,document);
`.trim(),
              }}
            />
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
