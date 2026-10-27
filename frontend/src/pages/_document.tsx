import Document, { Html, Head, Main, NextScript, DocumentContext, DocumentInitialProps } from 'next/document'

const rawGa4Id = process.env.NEXT_PUBLIC_GA4_ID || ''
const GA4_ID = /^G-[A-Z0-9]+$/i.test(rawGa4Id) ? rawGa4Id : ''

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

          {/* Основной шрифт: без предзагрузки он приходил после первой отрисовки, и
              подмена системного шрифта сдвигала вёрстку (CLS 0,13–0,31 на разделах
              и карточках). Путь совпадает с @font-face в globals.css. */}
          <link rel="preload" href="/fonts/InkVerse.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />

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
               Должно стоять ДО gtag.js (грузится в _app после согласия);
               при сохранённом согласии сразу granted.
               GTM-контейнер пуст, поэтому gtm.js (116 КБ) не грузим: GA4 подключён
               напрямую, события дублируются в gtag (lib/gtm.ts) ──── */}
          {GA4_ID && (
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
        </Head>
        <body>
          <Main />
          <NextScript />
        </body>
      </Html>
    )
  }
}

export default MyDocument
