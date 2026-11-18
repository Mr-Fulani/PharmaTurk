import { useEffect, useRef, type KeyboardEvent } from 'react'
import { useRouter } from 'next/router'
import { useStore } from 'zustand'
import { confirmDialogStore } from '../lib/confirmDialog'
import styles from './ConfirmDialog.module.css'

interface ConfirmRequest {
  title: string
  lines?: string[]
  acceptLabel: string
  declineLabel: string
}

/**
 * Окно подтверждения в стиле сайта вместо системного confirm(): одно на всё приложение (_app.tsx),
 * вызывается через askConfirm() из lib/confirmDialog. Esc, клик по фону и уход со страницы — отказ.
 */
export default function ConfirmDialog() {
  const router = useRouter()
  const request: ConfirmRequest | null = useStore(confirmDialogStore, (state) => state.request)
  const answer = useStore(confirmDialogStore, (state) => state.answer)
  const panelRef = useRef<HTMLDivElement>(null)
  const returnFocusRef = useRef<HTMLElement | null>(null)

  // Фокус — в окно; после ответа — обратно на элемент, с которого спросили
  useEffect(() => {
    if (!request) return
    returnFocusRef.current = document.activeElement as HTMLElement | null
    panelRef.current?.focus({ preventScroll: true })
    return () => {
      const target = returnFocusRef.current
      // Кнопка «В заявку» на время запроса выключена — фокус возвращаем, когда она включится
      setTimeout(() => {
        if (document.activeElement === document.body) target?.focus?.({ preventScroll: true })
      }, 50)
    }
  }, [request])

  useEffect(() => {
    const decline = () => answer(false)
    router.events.on('routeChangeStart', decline)
    return () => router.events.off('routeChangeStart', decline)
  }, [router.events, answer])

  if (!request) return null

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      answer(false)
      return
    }
    if (event.key !== 'Tab') return
    const buttons = panelRef.current?.querySelectorAll<HTMLElement>('button')
    if (!buttons?.length) return
    const first = buttons[0]
    const last = buttons[buttons.length - 1]
    const active = document.activeElement
    if (event.shiftKey && (active === first || active === panelRef.current)) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && active === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div className={styles.root}>
      <div className={styles.backdrop} onClick={() => answer(false)} />
      <div
        ref={panelRef}
        className={styles.panel}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby={request.lines?.length ? 'confirm-dialog-text' : undefined}
        tabIndex={-1}
        onKeyDown={onKeyDown}
      >
        <h2 id="confirm-dialog-title" className={styles.title}>{request.title}</h2>
        {request.lines?.length ? (
          <div id="confirm-dialog-text">
            {request.lines.map((line) => <p key={line} className={styles.line}>{line}</p>)}
          </div>
        ) : null}
        <div className={styles.actions}>
          <button type="button" className={styles.accept} onClick={() => answer(true)}>
            {request.acceptLabel}
          </button>
          <button type="button" className={styles.decline} onClick={() => answer(false)}>
            {request.declineLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
