import styles from './AnimatedOrderButton.module.css'

export type OrderButtonState = 'idle' | 'processing' | 'success'

interface AnimatedOrderButtonProps {
  state: OrderButtonState
  defaultLabel: string
  processingLabel: string
  successLabel: string
  disabled?: boolean
}

export default function AnimatedOrderButton({
  state,
  defaultLabel,
  processingLabel,
  successLabel,
  disabled = false,
}: AnimatedOrderButtonProps) {
  const accessibleLabel = state === 'success'
    ? successLabel
    : state === 'processing'
      ? processingLabel
      : defaultLabel

  return (
    <button
      type="submit"
      className={styles.order}
      data-state={state}
      disabled={disabled || state !== 'idle'}
      aria-busy={state === 'processing'}
      aria-label={accessibleLabel}
    >
      <span className={styles.default}>{defaultLabel}</span>
      <span className={styles.processing}>{processingLabel}</span>
      <span className={styles.success}>
        {successLabel}
        <svg viewBox="0 0 12 10" aria-hidden="true">
          <polyline points="1.5 6 4.5 9 10.5 1" />
        </svg>
      </span>

      <span className={styles.box} aria-hidden="true" />
      <span className={styles.truck} aria-hidden="true">
        <span className={styles.back} />
        <span className={styles.front}>
          <span className={styles.window} />
        </span>
        <span className={`${styles.light} ${styles.lightTop}`} />
        <span className={`${styles.light} ${styles.lightBottom}`} />
      </span>
      <span className={styles.lines} aria-hidden="true" />
    </button>
  )
}
