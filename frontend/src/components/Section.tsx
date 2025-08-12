interface SectionProps {
  title: string
  children: React.ReactNode
  action?: React.ReactNode
}

export default function Section({ title, children, action }: SectionProps) {
  return (
    <section className="mx-auto max-w-6xl px-6 py-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-bold text-gray-900">{title}</h2>
        {action ? <div>{action}</div> : null}
      </div>
      {children}
    </section>
  )
}


