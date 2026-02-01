import Document, { Html, Head, Main, NextScript, DocumentContext } from 'next/document'

class MyDocument extends Document {
  static async getInitialProps(ctx: DocumentContext) {
    const initialProps = await Document.getInitialProps(ctx)
    return { ...initialProps }
  }

  render() {
    const siteName = process.env.NEXT_PUBLIC_SITE_NAME || 'PharmaTurk'
    const siteUrl = (process.env.NEXT_PUBLIC_SITE_URL || 'https://pharmaturk.ru').replace(/\/$/, '')
    return (
      <Html lang="ru">
        <Head>
          <meta charSet="utf-8" />
          <link rel="preconnect" href="https://fonts.googleapis.com" />
          <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
          <meta name="theme-color" content="#4c1d95" />
          <meta name="application-name" content={siteName} />
          <meta property="og:site_name" content={siteName} />
          <meta property="og:type" content="website" />
          <meta property="og:url" content={siteUrl} />
          <meta property="twitter:card" content="summary_large_image" />
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
