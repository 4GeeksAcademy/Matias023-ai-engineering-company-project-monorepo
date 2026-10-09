import type { ReactNode } from 'react'

export default function LoadingFallback({ label }: { label?: string }): ReactNode {
  return (
    <main className="page">
      <section className="state-card" role="status" aria-live="polite">
        {label ?? 'Loading…'}
      </section>
    </main>
  )
}