import styles from './ThemeToggle.module.css'

type ThemeToggleProps = {
  isDark: boolean
  onToggle: () => void
  lightLabel: string
  darkLabel: string
}

export default function ThemeToggle({
  isDark,
  onToggle,
  lightLabel,
  darkLabel,
}: ThemeToggleProps) {
  const nextThemeLabel = isDark ? lightLabel : darkLabel

  return (
    <button
      type="button"
      className={styles.switch}
      data-theme={isDark ? 'dark' : 'light'}
      onClick={onToggle}
      aria-label={nextThemeLabel}
      aria-pressed={isDark}
      title={nextThemeLabel}
    >
      <span className={styles.track} aria-hidden="true">
        <span className={styles.stars}>
          {Array.from({ length: 5 }, (_, index) => (
            <span key={index} className={styles.star} />
          ))}
        </span>

        <span className={styles.cloudShadow}>
          {Array.from({ length: 3 }, (_, index) => (
            <span key={index} className={styles.cloudBubble} />
          ))}
        </span>

        <span className={styles.clouds}>
          {Array.from({ length: 6 }, (_, index) => (
            <span key={index} className={styles.cloudBubble} />
          ))}
        </span>

        <span className={styles.thumb}>
          <span className={styles.crater} />
          <span className={styles.crater} />
          <span className={styles.crater} />
        </span>
      </span>
    </button>
  )
}
