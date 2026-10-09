import type { ReactNode } from 'react'

type PageHeaderProps = {
  title: string
  subtitle: string
  children: ReactNode
}

export default function PageHeader({ title, subtitle, children }: PageHeaderProps) {
  return (
    <section className="header">
      <div>
        <p className="eyebrow">TrackFlow Operations</p>
        <h1>{title}</h1>
        <p className="subtitle">{subtitle}</p>
      </div>

      <div className="header-actions">{children}</div>
    </section>
  )
}