import Link from 'next/link'
import { useTranslation } from 'next-i18next'

type Part = string | { href: string; text: string }
type Block =
  | { type: 'p'; parts: Part[] }
  | { type: 'ul'; items: Part[][] }
  | { type: 'table'; head: string[]; rows: Part[][][] }

export interface BlogArticle {
  slug: string
  publishedAt: string
  updatedAt: string
  title: string
  metaTitle: string
  description: string
  lead: string
  sections: Array<{ heading: string; blocks: Block[] }>
  faq: Array<{ q: string; a: string }>
  sources: Array<{ label: string; url: string }>
}

const linkClass = 'font-medium text-[var(--accent)] underline-offset-2 hover:underline'

function Parts({ parts }: { parts: Part[] }) {
  return (
    <>
      {parts.map((part, index) =>
        typeof part === 'string' ? (
          <span key={index}>{part}</span>
        ) : (
          <Link key={index} href={part.href} className={linkClass}>
            {part.text}
          </Link>
        )
      )}
    </>
  )
}

function ArticleBlock({ block }: { block: Block }) {
  if (block.type === 'p') {
    return (
      <p className="mb-4 leading-relaxed text-main last:mb-0">
        <Parts parts={block.parts} />
      </p>
    )
  }
  if (block.type === 'ul') {
    return (
      <ul className="mb-4 list-disc space-y-2 pl-5 leading-relaxed text-main last:mb-0">
        {block.items.map((item, index) => (
          <li key={index}>
            <Parts parts={item} />
          </li>
        ))}
      </ul>
    )
  }
  return (
    <div className="mb-4 overflow-x-auto rounded-xl border border-[var(--border)] last:mb-0">
      <table className="w-full min-w-[520px] border-collapse text-left text-sm">
        <thead className="bg-[var(--bg)]">
          <tr>
            {block.head.map((cell) => (
              <th key={cell} scope="col" className="px-3 py-2 font-semibold text-main">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-t border-[var(--border)]">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-3 py-2 align-top text-main">
                  <Parts parts={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Вопросы и ответы — те же, что в FAQPage страницы. */
export function FaqList({ title, faq }: { title: string; faq: Array<{ q: string; a: string }> }) {
  if (!faq.length) return null
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 sm:p-6">
      <h2 className="mb-4 text-xl font-semibold text-main">{title}</h2>
      <div className="space-y-3">
        {faq.map((item) => (
          <details key={item.q} className="group rounded-xl border border-[var(--border)] bg-[var(--bg)] px-4 py-3" open>
            <summary className="cursor-pointer list-none font-medium text-main">{item.q}</summary>
            <p className="mt-2 leading-relaxed text-main/85">{item.a}</p>
          </details>
        ))}
      </div>
    </section>
  )
}

/** Текст статьи: вводный абзац, разделы, вопросы и ответы, источники. */
export default function BlogArticleBody({ article }: { article: BlogArticle }) {
  const { t } = useTranslation('common')
  return (
    <div className="space-y-6">
      <p className="text-lg leading-relaxed text-main/85">{article.lead}</p>
      {article.sections.map((section) => (
        <section key={section.heading} className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 sm:p-6">
          <h2 className="mb-4 text-xl font-semibold text-main">{section.heading}</h2>
          {section.blocks.map((block, index) => (
            <ArticleBlock key={index} block={block} />
          ))}
        </section>
      ))}
      <FaqList title={t('blog_faq_title', 'Вопросы и ответы')} faq={article.faq} />
      {article.sources.length > 0 && (
        <section className="text-sm text-main/70">
          <h2 className="mb-2 font-semibold text-main">{t('blog_sources_title', 'Источники')}</h2>
          <ul className="list-disc space-y-1 pl-5">
            {article.sources.map((source) => (
              <li key={source.label}>
                <a href={source.url} target="_blank" rel="noopener noreferrer" className="underline-offset-2 hover:underline">
                  {source.label}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
