interface BadgeProps {
  children: React.ReactNode
  color?: 'red' | 'blue' | 'green' | 'yellow' | 'gray'
}

export default function Badge({ children, color = 'red' }: BadgeProps) {
  const colors: Record<string, string> = {
    red: 'bg-red-50 text-red-700 ring-red-200',
    blue: 'bg-blue-50 text-blue-700 ring-blue-200',
    green: 'bg-green-50 text-green-700 ring-green-200',
    yellow: 'bg-yellow-50 text-yellow-700 ring-yellow-200',
    gray: 'bg-gray-100 text-gray-700 ring-gray-200',
  }
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs ring-1 ${colors[color]}`}>{children}</span>
  )
}


